import discord
from discord import app_commands
import requests
import os
from keep_alive import keep_alive
from datetime import datetime, timedelta
from dateutil import parser
from database import Task, TaskCreator, get_session
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import Optional, Callable, Any
import traceback
import sys
import functools
from discord.app_commands import checks
import sqlalchemy

# Import the modular systems
import dice
import intmsg
from ticket_system import (
    InteractiveMessage, MessageButton, Ticket, IntMsgCreator,
    InteractiveMessageView, ButtonSetupModal, TicketControlView
)
import dice
import intmsg

# Initialize bot with all intents
class PuddlesBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # Needed for member resolution
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.scheduler = AsyncIOScheduler()
        
    async def setup_hook(self):
        print("Syncing commands...")
        try:
            # Setup commands from modules
            dice.setup_dice_commands(self.tree)
            intmsg.setup_intmsg_commands(self.tree)
            intmsg.setup_intmsg_system(self)  # Pass client reference
            
            await self.tree.sync(guild=None)  # None means global sync
            print("Commands synced successfully!")
            print("Available commands: /task, /mytasks, /taskedit, /showtasks, /alltasks, /tcw, /quack, /diceroll, /help")
            print("Ticket system commands: /intmsg, /editintmsg, /listmessages, /ticketstats, /imw, /fixdb")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
            print("Full error:", traceback.format_exc())
        
        self.scheduler.start()
        self.scheduler.add_job(self.check_due_tasks, 'interval', hours=1)
        # Add backup job to run every 6 hours
        self.scheduler.add_job(self.backup_database, 'interval', hours=6)
        
        # Removed load_persistent_views from setup_hook - now handled in on_ready with proper timing

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')
        
        # Wait a moment for Discord.py to fully load all data
        print("⏳ Waiting for Discord.py to fully load all guilds and channels...")
        await asyncio.sleep(3)
        
        # Check if all guilds are available
        unavailable_guilds = [g for g in self.guilds if g.unavailable]
        if unavailable_guilds:
            print(f"⚠️ {len(unavailable_guilds)} guilds are unavailable, waiting longer...")
            await asyncio.sleep(5)
        
        print("🔄 Starting persistence system...")
        await self.load_persistent_views()

    async def check_due_tasks(self):
        session = get_session()
        try:
            three_days_from_now = datetime.utcnow() + timedelta(days=3)
            tasks = session.query(Task).filter(
                Task.due_date <= three_days_from_now,
                Task.due_date > datetime.utcnow(),
                Task.completed == False
            ).all()
            
            for task in tasks:
                user = await self.fetch_user(int(task.assigned_to))
                if user:
                    embed = discord.Embed(
                        title="⚠️ Task Due Soon!",
                        description=f"Task: {task.name}\nDue Date: {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}\n\nDescription:\n{task.description}",
                        color=discord.Color.yellow()
                    )
                    try:
                        await user.send(embed=embed)
                    except discord.Forbidden:
                        pass
        finally:
            session.close()

    async def on_error(self, event, *args, **kwargs):
        print(f"Error in {event}:", file=sys.stderr)
        traceback.print_exc()

    async def backup_database(self):
        """Create a backup of the database"""
        try:
            from database import create_backup
            create_backup()
            print(f"Database backup created successfully at {datetime.utcnow()}")
        except Exception as e:
            print(f"Error creating database backup: {e}")
            print(traceback.format_exc())
    
    async def load_persistent_views(self):
        """Load persistent views for interactive messages and tickets"""
        session = get_session()
        restored_messages = 0
        restored_tickets = 0
        cleaned_messages = 0
        
        print("🔄 Starting persistence restoration...")
        
        # Add debugging information about bot's access
        print(f"🤖 Bot is connected to {len(self.guilds)} guild(s):")
        for guild in self.guilds:
            print(f"   • {guild.name} (ID: {guild.id}) - {len(guild.channels)} channels")
        
        try:
            # STEP 1: Clean up deleted messages from database
            print("🧹 Cleaning up deleted messages...")
            interactive_messages = session.query(InteractiveMessage).all()
            print(f"📋 Found {len(interactive_messages)} interactive messages in database")
            
            for msg_data in interactive_messages:
                print(f"\n🔍 Checking message {msg_data.id}:")
                print(f"   Discord Message ID: {msg_data.message_id}")
                print(f"   Channel ID: {msg_data.channel_id}")
                print(f"   Server ID: {msg_data.server_id}")
                print(f"   Title: {msg_data.title}")
                print(f"   Buttons: {len(msg_data.buttons)}")
                
                # Check if bot is in the server where this message was created
                target_guild = self.get_guild(int(msg_data.server_id))
                if target_guild:
                    print(f"   ✅ Bot is in server: {target_guild.name}")
                else:
                    print(f"   ❌ Bot is NOT in server {msg_data.server_id}")
                    print(f"   🗑️ Removing message {msg_data.id} from database (bot not in server)")
                    session.delete(msg_data)
                    cleaned_messages += 1
                    continue
                
                try:
                    channel = self.get_channel(int(msg_data.channel_id))
                    if not channel:
                        print(f"   ❌ Channel {msg_data.channel_id} not found with get_channel()")
                        print(f"   🔍 Channel ID type: {type(msg_data.channel_id)}")
                        print(f"   🔍 Channel ID value: '{msg_data.channel_id}'")
                        
                        # Try converting to int explicitly
                        try:
                            channel_id_int = int(msg_data.channel_id)
                            print(f"   🔍 Converted to int: {channel_id_int}")
                        except ValueError as ve:
                            print(f"   ❌ Cannot convert channel ID to int: {ve}")
                            session.delete(msg_data)
                            cleaned_messages += 1
                            continue
                        
                        # Try different methods to get the channel
                        print(f"   🔍 Trying different channel lookup methods...")
                        
                        # Method 1: get_channel with explicit int
                        test_channel = self.get_channel(channel_id_int)
                        print(f"   • get_channel(int): {test_channel}")
                        
                        # Method 2: Look in the target guild specifically
                        guild_channel = target_guild.get_channel(channel_id_int)
                        print(f"   • guild.get_channel(): {guild_channel}")
                        
                        # Method 3: Try to fetch from Discord API
                        try:
                            print(f"   🔍 Attempting to fetch channel directly from Discord API...")
                            fetched_channel = await self.fetch_channel(channel_id_int)
                            print(f"   • fetch_channel(): {fetched_channel}")
                            if fetched_channel:
                                print(f"   ✅ Channel exists! Name: #{fetched_channel.name}")
                                print(f"   ✅ Guild: {fetched_channel.guild.name}")
                                print(f"   ⚠️ But get_channel() failed - possible caching issue")
                                channel = fetched_channel  # Use the fetched channel
                            else:
                                print(f"   ❌ fetch_channel() also returned None")
                        except discord.Forbidden as e:
                            print(f"   ❌ No permission to fetch channel: {e}")
                        except discord.NotFound as e:
                            print(f"   ❌ Channel truly doesn't exist: {e}")
                        except Exception as e:
                            print(f"   ❌ Error fetching channel: {e}")
                        
                        # If we still don't have the channel, try searching all guilds
                        if not channel:
                            print(f"   🔍 Searching all {len(self.guilds)} guilds for channel...")
                            found_in_guild = None
                            for guild in self.guilds:
                                guild_channel = guild.get_channel(channel_id_int)
                                if guild_channel:
                                    found_in_guild = guild
                                    channel = guild_channel
                                    break
                            
                            if found_in_guild:
                                print(f"   🔍 Channel found in guild: {found_in_guild.name} (ID: {found_in_guild.id})")
                                print(f"   🔍 Channel name: #{guild_channel.name}")
                                print(f"   ⚠️ But bot.get_channel() couldn't access it - cache issue?")
                            else:
                                print(f"   🔍 Channel not found in any of {len(self.guilds)} connected guilds")
                        
                        # If we STILL don't have the channel, remove from database
                        if not channel:
                            print(f"   🗑️ Removing message {msg_data.id} from database - channel truly inaccessible")
                            session.delete(msg_data)
                            cleaned_messages += 1
                            continue
                    
                    print(f"   ✅ Channel found: #{channel.name} in {channel.guild.name}")
                    
                    try:
                        message = await channel.fetch_message(int(msg_data.message_id))
                        print(f"   ✅ Discord message found and accessible")
                    except discord.NotFound:
                        print(f"   ❌ Discord message {msg_data.message_id} not found, removing from database")
                        session.delete(msg_data)
                        cleaned_messages += 1
                        continue
                    except discord.Forbidden:
                        print(f"   ⚠️ No permission to fetch message {msg_data.message_id}, skipping")
                        continue
                    
                except Exception as e:
                    print(f"   ❌ Error checking message {msg_data.id}: {e}")
                    continue
            
            # Commit cleanup changes
            if cleaned_messages > 0:
                session.commit()
                print(f"\n🗑️ Cleaned up {cleaned_messages} deleted messages from database")
            
            # STEP 2: Register views with bot (this is crucial for persistent views)
            print(f"\n📋 Registering interactive message views with bot...")
            remaining_messages = session.query(InteractiveMessage).all()
            print(f"📊 {len(remaining_messages)} messages remaining after cleanup")
            
            for msg_data in remaining_messages:
                print(f"\n🔧 Processing message {msg_data.id}:")
                print(f"   Discord Message ID: {msg_data.message_id}")
                print(f"   Channel ID: {msg_data.channel_id}")
                print(f"   Title: {msg_data.title}")
                print(f"   Button count: {len(msg_data.buttons)}")
                
                try:
                    if msg_data.buttons:
                        print(f"   📝 Button details:")
                        for i, button in enumerate(msg_data.buttons):
                            print(f"      {i+1}. {button.button_type.upper()}: '{button.label}' (ID: {button.id})")
                        
                        # Create view and register it with the bot
                        print(f"   🔄 Creating InteractiveMessageView...")
                        view = InteractiveMessageView(msg_data)
                        
                        print(f"   🔗 Registering view with bot...")
                        self.add_view(view)  # This is the key step!
                        
                        restored_messages += 1
                        print(f"   ✅ Successfully registered view for message {msg_data.message_id}")
                    else:
                        print(f"   ⏭️ No buttons found, skipping")
                        
                except Exception as e:
                    print(f"   ❌ Error registering view for message {msg_data.id}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
        except Exception as e:
            print(f"❌ Error loading interactive messages: {e}")
            import traceback
            traceback.print_exc()
        
        try:
            # STEP 3: Load ticket control views
            print("🎫 Loading ticket control views...")
            
            try:
                open_tickets = session.query(Ticket).filter_by(status="open").all()
            except Exception as db_error:
                if "no such column" in str(db_error).lower():
                    print("⚠️ Database schema outdated - some features may not work until database is updated")
                    print("💡 To fix: Run `/fixdb` command or delete data/tasks.db and restart")
                    try:
                        open_tickets = session.execute(
                            "SELECT id, ticket_id, channel_id, server_id, creator_id, button_id, status, created_at, closed_at, closed_by FROM tickets WHERE status = 'open'"
                        ).fetchall()
                        class TicketLike:
                            def __init__(self, row):
                                self.id = row[0]
                                self.channel_id = str(row[2])
                        open_tickets = [TicketLike(row) for row in open_tickets]
                    except:
                        print("❌ Cannot load tickets due to database issues")
                        open_tickets = []
                else:
                    print(f"❌ Database error loading tickets: {db_error}")
                    open_tickets = []
            
            for ticket in open_tickets:
                try:
                    channel = self.get_channel(int(ticket.channel_id))
                    if channel:
                        view = TicketControlView(ticket.id)
                        self.add_view(view)
                        restored_tickets += 1
                        print(f"✅ Registered ticket control view for ticket {ticket.id}")
                    else:
                        print(f"❌ Ticket channel {ticket.channel_id} not found for ticket {ticket.id}")
                except Exception as e:
                    print(f"❌ Error restoring ticket view {ticket.id}: {e}")
                    continue
                    
        except Exception as e:
            print(f"❌ Error loading ticket views: {e}")
        
        finally:
            session.close()
        
        print(f"🎉 Persistence restoration complete!")
        print(f"📊 Results:")
        print(f"   • Registered {restored_messages} interactive message views")
        print(f"   • Registered {restored_tickets} ticket control views") 
        print(f"   • Cleaned up {cleaned_messages} deleted messages")
        
        if restored_messages == 0 and restored_tickets == 0:
            print("ℹ️ No persistent views found to restore")
        else:
            print("✅ All buttons should now work properly!")
            
        # STEP 4: Optional - Auto-refresh problematic messages (run after a delay)
        if restored_messages > 0:
            print("⏳ Will auto-refresh messages in 5 seconds to ensure proper display...")
            await asyncio.sleep(5)
            await self._auto_refresh_messages()

    async def _auto_refresh_messages(self):
        """Auto-refresh interactive messages to ensure proper display and functionality"""
        session = get_session()
        refreshed = 0
        
        try:
            print("🔄 Auto-refreshing interactive messages...")
            interactive_messages = session.query(InteractiveMessage).all()
            print(f"🔍 Found {len(interactive_messages)} messages to potentially refresh")
            
            for msg_data in interactive_messages:
                print(f"\n🔄 Refreshing message {msg_data.id}:")
                print(f"   Discord Message ID: {msg_data.message_id}")
                print(f"   Channel ID: {msg_data.channel_id}")
                print(f"   Title: {msg_data.title}")
                
                try:
                    if not msg_data.buttons:
                        print(f"   ⏭️ No buttons, skipping refresh")
                        continue
                        
                    channel = self.get_channel(int(msg_data.channel_id))
                    if not channel:
                        print(f"   ❌ Channel not found")
                        continue
                    
                    print(f"   ✅ Channel found: #{channel.name}")
                    
                    try:
                        message = await channel.fetch_message(int(msg_data.message_id))
                        print(f"   ✅ Discord message fetched successfully")
                    except (discord.NotFound, discord.Forbidden) as e:
                        print(f"   ❌ Cannot access message: {e}")
                        continue
                    
                    # Create embed with proper format (same as Update & Refresh)
                    print(f"   🎨 Creating new embed...")
                    try:
                        color = discord.Color(int(msg_data.color, 16))
                        print(f"   🎨 Using color: {msg_data.color}")
                    except:
                        color = discord.Color.blurple()
                        print(f"   🎨 Using default color (blurple)")
                    
                    description_text = msg_data.description if msg_data.description else ""
                    if description_text:
                        updated_description = f"# {msg_data.title}\n\n{description_text}\n\n-# Message ID: {msg_data.message_id}"
                    else:
                        updated_description = f"# {msg_data.title}\n\n-# Message ID: {msg_data.message_id}"
                    
                    embed = discord.Embed(
                        description=updated_description,
                        color=color
                    )
                    
                    # Create view (should already be registered with bot)
                    print(f"   🔧 Creating new view...")
                    view = InteractiveMessageView(msg_data)
                    
                    print(f"   📝 Updating Discord message...")
                    await message.edit(embed=embed, view=view)
                    refreshed += 1
                    print(f"   ✅ Successfully refreshed message {msg_data.message_id}")
                    
                except Exception as e:
                    print(f"   ⚠️ Could not refresh message {msg_data.message_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
                    
        except Exception as e:
            print(f"❌ Error during auto-refresh: {e}")
            import traceback
            traceback.print_exc()
        finally:
            session.close()
            
        print(f"\n🎉 Auto-refresh complete!")
        if refreshed > 0:
            print(f"✅ Successfully refreshed {refreshed} interactive messages")
        else:
            print("ℹ️ No messages were refreshed")

client = PuddlesBot()

class UserButton(discord.ui.Button):
    def __init__(self, user: discord.Member):
        super().__init__(
            label=user.display_name,
            style=discord.ButtonStyle.secondary
        )
        self.user = user

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"User Profile: {self.user.display_name}",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        embed.add_field(name="Joined Server", value=self.user.joined_at.strftime("%Y-%m-%d"))
        embed.add_field(name="Account Created", value=self.user.created_at.strftime("%Y-%m-%d"))
        embed.add_field(name="Roles", value=", ".join([role.name for role in self.user.roles[1:]]) or "No roles", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

class TaskView(discord.ui.View):
    def __init__(self, tasks, user):
        super().__init__(timeout=180)  # 3 minute timeout
        self.tasks = tasks
        self.user = user
        self.selected_task = None
        
        # Add task selection dropdown
        self.add_item(TaskSelect(tasks))

class TaskSelect(discord.ui.Select):
    def __init__(self, tasks):
        self.task_list = tasks
        options = [
            discord.SelectOption(
                label=task.name[:100],  # Discord has a 100 char limit on labels
                value=str(task.id),
                description=f"Due: {task.due_date.strftime('%Y-%m-%d %H:%M')}"[:100]
            ) for task in tasks
        ]
        super().__init__(
            placeholder="Choose a task to view details...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        view: TaskView = self.view
        session = get_session()
        try:
            task_id = int(self.values[0])
            task = session.query(Task).get(task_id)
            if not task:
                await interaction.response.send_message("Task not found!", ephemeral=True)
                return

            view.selected_task = task
            
            # Create embed with task details
            embed = discord.Embed(
                title=f"Task: {task.name}",
                description=task.description,
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Due Date",
                value=task.due_date.strftime('%Y-%m-%d %H:%M UTC'),
                inline=False
            )
            embed.add_field(
                name="Status",
                value="Pending",
                inline=False
            )

            # Update the complete button state
            complete_button = None
            for item in view.children:
                if isinstance(item, CompleteTaskButton):
                    complete_button = item
                    complete_button.disabled = False
                    break
            
            if not complete_button:
                view.add_item(CompleteTaskButton())

            await interaction.response.edit_message(embed=embed, view=view)
        
        except Exception as e:
            print(f"Error in task selection: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                "An error occurred while processing your selection.",
                ephemeral=True
            )
        finally:
            session.close()

class CompleteTaskButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Complete Task",
            disabled=True  # Disabled by default until a task is selected
        )

    async def callback(self, interaction: discord.Interaction):
        view: TaskView = self.view
        if not view.selected_task:
            await interaction.response.send_message(
                "Please select a task first!",
                ephemeral=True
            )
            return

        if interaction.user.id != int(view.selected_task.assigned_to):
            await interaction.response.send_message(
                "You can only complete tasks assigned to you!",
                ephemeral=True
            )
            return

        session = get_session()
        try:
            task = session.query(Task).get(view.selected_task.id)
            if task:
                task.completed = True
                task.completed_at = datetime.utcnow()
                session.commit()
                
                embed = discord.Embed(
                    title="✅ Task Completed",
                    description=f"Task '{task.name}' has been marked as complete!",
                    color=discord.Color.green()
                )
                
                # Disable the complete button and dropdown
                self.disabled = True
                for item in view.children:
                    if isinstance(item, TaskSelect):
                        item.disabled = True

                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await interaction.response.send_message(
                    "Task not found! It may have been deleted.",
                    ephemeral=True
                )
        
        except Exception as e:
            print(f"Error completing task: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                f"An error occurred while completing the task: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

def log_command(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args: Any, **kwargs: Any) -> Any:
        try:
            print(f"Executing command: {func.__name__}")
            print(f"Command called by: {interaction.user.name}")
            print(f"Arguments: {args}")
            print(f"Keyword arguments: {kwargs}")
            return await func(interaction, *args, **kwargs)
        except Exception as e:
            print(f"Error in {func.__name__}:")
            print(traceback.format_exc())
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"An error occurred while processing the command. Error: {str(e)}",
                    ephemeral=True
                )
    return wrapper

async def can_create_intmsg(interaction: discord.Interaction) -> bool:
    """Check if user can create interactive messages"""
    # Check if user is administrator
    if interaction.user.guild_permissions.administrator:
        return True
    
    # Check if user is in the intmsg creator whitelist
    session = get_session()
    try:
        creator = session.query(IntMsgCreator).filter_by(
            user_id=str(interaction.user.id),
            server_id=str(interaction.guild_id)
        ).first()
        return creator is not None
    finally:
        session.close()

async def can_create_tasks(interaction: discord.Interaction) -> bool:
    """Check if a user can create tasks"""
    # Admin override
    if interaction.user.guild_permissions.administrator:
        return True
        
    # Check whitelist
    session = None
    try:
        session = get_session()
        creator = session.query(TaskCreator).filter_by(
            user_id=str(interaction.user.id),
            server_id=str(interaction.guild_id)
        ).first()
        return creator is not None
    except Exception as e:
        print(f"Error checking task creation permissions: {e}")
        return False
    finally:
        if session:
            session.close()

@client.tree.command(
    name="tcw",
    description="Add or remove a user from the task creator whitelist (Admin only)"
)
@app_commands.describe(
    user="The user to add/remove from the task creator whitelist",
    action="The action to perform: 'add' or 'remove'"
)
@checks.has_permissions(administrator=True)
@log_command
async def tcw(interaction: discord.Interaction, user: discord.Member, action: str):
    if action.lower() not in ["add", "remove"]:
        await interaction.response.send_message(
            "Invalid action. Please use 'add' or 'remove'.",
            ephemeral=True
        )
        return

    session = get_session()
    try:
        # Check if user is already whitelisted
        existing = session.query(TaskCreator).filter_by(
            user_id=str(user.id),
            server_id=str(interaction.guild_id)
        ).first()
        
        if action.lower() == "add":
            if existing:
                await interaction.response.send_message(
                    f"{user.display_name} is already whitelisted to create tasks.",
                    ephemeral=True
                )
                return
                
            # Add user to whitelist
            creator = TaskCreator(
                user_id=str(user.id),
                server_id=str(interaction.guild_id),
                added_by=str(interaction.user.id)
            )
            session.add(creator)
            session.commit()
            
            await interaction.response.send_message(
                f"✅ {user.display_name} has been added to the task creator whitelist.",
                ephemeral=True
            )
        else:  # remove
            if not existing:
                await interaction.response.send_message(
                    f"{user.display_name} is not in the task creator whitelist.",
                    ephemeral=True
                )
                return
            
            session.delete(existing)
            session.commit()
            
            await interaction.response.send_message(
                f"✅ {user.display_name} has been removed from the task creator whitelist.",
                ephemeral=True
            )
        
    except Exception as e:
        print(f"Error in tcw command: {str(e)}")
        print(traceback.format_exc())
        await interaction.response.send_message(
            f"An error occurred while managing the whitelist: {str(e)}",
            ephemeral=True
        )
    finally:
        session.close()

@client.tree.command(
    name="task",
    description="Create a new task"
)
@app_commands.describe(
    name="Name of the task",
    assigned_to="User to assign the task to (mention the user)",
    due_date="Due date in YYYY-MM-DD HH:MM format (24-hour)",
    description="Description of the task"
)
@log_command
async def task(interaction: discord.Interaction, name: str, assigned_to: discord.Member, due_date: str, description: str):
    # Check if user can create tasks
    if not await can_create_tasks(interaction):
        await interaction.response.send_message(
            "You don't have permission to create tasks. Please ask an admin to add you to the task creator whitelist.",
            ephemeral=True
        )
        return

    session = None
    try:
        due_date_dt = parser.parse(due_date)
        
        session = get_session()
        new_task = Task(
            name=name,
            assigned_to=str(assigned_to.id),
            due_date=due_date_dt,
            description=description,
            server_id=str(interaction.guild_id),
            created_by=str(interaction.user.id)
        )
        session.add(new_task)
        session.commit()
        
        embed = discord.Embed(
            title="✅ Task Created",
            description=f"Task '{name}' has been assigned to {assigned_to.display_name}",
            color=discord.Color.green()
        )
        embed.add_field(name="Due Date", value=due_date_dt.strftime('%Y-%m-%d %H:%M UTC'))
        await interaction.response.send_message(embed=embed)
        
        try:
            await assigned_to.send(
                f"You have been assigned a new task in {interaction.guild.name}:\n"
                f"**{name}**\n"
                f"Due: {due_date_dt.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                f"Description:\n{description}"
            )
        except discord.Forbidden:
            pass
            
    except ValueError as e:
        await interaction.response.send_message(
            "Invalid date format. Please use YYYY-MM-DD HH:MM format.",
            ephemeral=True
        )
    except Exception as e:
        print(f"Error creating task: {e}")
        print(traceback.format_exc())
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"An error occurred while creating the task. Please try again later.",
                ephemeral=True
            )
    finally:
        if session:
            session.close()

@client.tree.command(
    name="mytasks",
    description="View your tasks"
)
@log_command
async def mytasks(interaction: discord.Interaction):
    session = None
    try:
        session = get_session()
        tasks = session.query(Task).filter_by(
            assigned_to=str(interaction.user.id),
            server_id=str(interaction.guild_id),
            completed=False
        ).order_by(Task.due_date).all()
        
        if not tasks:
            await interaction.response.send_message(
                "You have no pending tasks! 🎉",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title="Your Tasks",
            description="Select a task from the dropdown to view details and mark as complete:",
            color=discord.Color.blue()
        )

        # Add a summary of tasks to the initial embed
        for task in tasks:
            due_date = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
            try:
                creator = await client.fetch_user(int(task.created_by)) if task.created_by != "0" else None
                creator_name = creator.display_name if creator else "Unknown"
            except:
                creator_name = "Unknown"

            value = (
                f"Due: {due_date}\n"
                f"Created by: {creator_name}\n"
                f"Description: {task.description[:100]}..." if len(task.description) > 100 else task.description
            )
            embed.add_field(name=task.name, value=value, inline=False)
        
        view = TaskView(tasks, interaction.user)
        await interaction.response.send_message(embed=embed, view=view)
        
    except Exception as e:
        print(f"Error in mytasks command: {e}")
        print(traceback.format_exc())
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "An error occurred while fetching your tasks. The database might be initializing. Please try again in a few seconds.",
                ephemeral=True
            )
    finally:
        if session:
            session.close()

class TaskEditSelect(discord.ui.Select):
    def __init__(self, tasks):
        self.task_list = tasks
        options = [
            discord.SelectOption(
                label=task.name[:100],
                value=str(task.id),
                description=f"Due: {task.due_date.strftime('%Y-%m-%d %H:%M')}"[:100]
            ) for task in tasks
        ]
        super().__init__(
            placeholder="Choose a task to edit...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        view: TaskEditView = self.view
        session = get_session()
        try:
            task_id = int(self.values[0])
            task = session.query(Task).get(task_id)
            if not task:
                await interaction.response.send_message("Task not found!", ephemeral=True)
                return

            view.selected_task = task
            
            # Create embed with task details
            embed = discord.Embed(
                title=f"Edit Task: {task.name}",
                description="Select what you want to edit:",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Current Details",
                value=(
                    f"Name: {task.name}\n"
                    f"Due Date: {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}\n"
                    f"Description: {task.description}"
                ),
                inline=False
            )

            # Enable the edit buttons
            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = False

            await interaction.response.edit_message(embed=embed, view=view)
        
        except Exception as e:
            print(f"Error in task selection: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                "An error occurred while processing your selection.",
                ephemeral=True
            )
        finally:
            session.close()

class TaskEditView(discord.ui.View):
    def __init__(self, tasks, user):
        super().__init__(timeout=300)  # 5 minute timeout
        self.tasks = tasks
        self.user = user
        self.selected_task = None
        
        # Add task selection dropdown
        self.add_item(TaskEditSelect(tasks))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not self.selected_task:
            return True
        
        # Check if user has permission to edit
        is_admin = interaction.user.guild_permissions.administrator
        is_creator = str(interaction.user.id) == self.selected_task.created_by
        is_assigned = str(interaction.user.id) == self.selected_task.assigned_to
        
        if not (is_admin or is_creator or is_assigned):
            await interaction.response.send_message(
                "You don't have permission to edit this task. Only administrators, task creators, and assigned users can edit tasks.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Edit Name", custom_id="edit_name_btn", style=discord.ButtonStyle.primary, disabled=True, row=1)
    async def edit_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TaskEditModal(self.selected_task, "name")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Due Date", custom_id="edit_due_date_btn", style=discord.ButtonStyle.primary, disabled=True, row=1)
    async def edit_due_date(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TaskEditModal(self.selected_task, "due_date")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Description", custom_id="edit_desc_btn", style=discord.ButtonStyle.primary, disabled=True, row=2)
    async def edit_description(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TaskEditModal(self.selected_task, "description")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Change Assignee", custom_id="edit_assignee_btn", style=discord.ButtonStyle.primary, disabled=True, row=2)
    async def edit_assignee(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TaskEditModal(self.selected_task, "assignee")
        await interaction.response.send_modal(modal)

class TaskEditModal(discord.ui.Modal):
    def __init__(self, task: Task, field: str):
        self.task = task
        self.field = field
        
        if field == "name":
            super().__init__(title="Edit Task Name")
            self.input = discord.ui.TextInput(
                label="New Task Name",
                placeholder="Enter the new task name...",
                default=task.name,
                required=True,
                max_length=100
            )
        elif field == "due_date":
            super().__init__(title="Edit Due Date")
            self.input = discord.ui.TextInput(
                label="New Due Date (YYYY-MM-DD HH:MM)",
                placeholder="Example: 2024-12-31 15:30",
                default=task.due_date.strftime("%Y-%m-%d %H:%M"),
                required=True
            )
        elif field == "description":
            super().__init__(title="Edit Description")
            self.input = discord.ui.TextInput(
                label="New Description",
                placeholder="Enter the new task description...",
                default=task.description,
                required=True,
                style=discord.TextStyle.paragraph
            )
        elif field == "assignee":
            super().__init__(title="Change Assignee")
            self.input = discord.ui.TextInput(
                label="New Assignee (User ID or @mention)",
                placeholder="Enter user ID or @mention...",
                required=True
            )
        
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        session = get_session()
        try:
            task = session.query(Task).get(self.task.id)
            if not task:
                await interaction.response.send_message("Task not found!", ephemeral=True)
                return

            if self.field == "name":
                task.name = self.input.value
            elif self.field == "due_date":
                try:
                    task.due_date = parser.parse(self.input.value)
                except ValueError:
                    await interaction.response.send_message(
                        "Invalid date format. Please use YYYY-MM-DD HH:MM format.",
                        ephemeral=True
                    )
                    return
            elif self.field == "description":
                task.description = self.input.value
            elif self.field == "assignee":
                # Handle both user ID and @mention formats
                user_input = self.input.value.strip()
                if user_input.startswith('<@') and user_input.endswith('>'):
                    user_id = user_input[2:-1]
                    if user_id.startswith('!'):
                        user_id = user_id[1:]
                else:
                    user_id = user_input

                try:
                    user = await interaction.client.fetch_user(int(user_id))
                    task.assigned_to = str(user.id)
                except:
                    await interaction.response.send_message(
                        "Invalid user. Please provide a valid user ID or @mention.",
                        ephemeral=True
                    )
                    return

            session.commit()
            
            embed = discord.Embed(
                title="✅ Task Updated",
                description=f"Task '{task.name}' has been updated.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Updated Field",
                value=f"The {self.field} has been updated successfully.",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error updating task: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                f"An error occurred while updating the task: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

@client.tree.command(
    name="taskedit",
    description="Edit an existing task"
)
@log_command
async def taskedit(interaction: discord.Interaction):
    session = get_session()
    try:
        # Get tasks that the user can edit (created by them or assigned to them)
        tasks = session.query(Task).filter(
            sqlalchemy.or_(
                Task.created_by == str(interaction.user.id),
                Task.assigned_to == str(interaction.user.id)
            ),
            Task.server_id == str(interaction.guild_id),
            Task.completed == False
        ).order_by(Task.due_date).all()
        
        if not tasks:
            await interaction.response.send_message(
                "You have no tasks that you can edit!",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title="Edit Task",
            description="Select a task to edit:",
            color=discord.Color.blue()
        )
        
        view = TaskEditView(tasks, interaction.user)
        await interaction.response.send_message(embed=embed, view=view)
        
    except Exception as e:
        print(f"Error in taskedit command: {str(e)}")
        print(traceback.format_exc())
        await interaction.response.send_message(
            f"An error occurred while fetching tasks: {str(e)}",
            ephemeral=True
        )
    finally:
        session.close()

@client.tree.command(
    name="showtasks",
    description="View tasks assigned to a specific user"
)
@app_commands.describe(
    target_user="The user whose tasks you want to view (mention the user)"
)
@log_command
async def showtasks(interaction: discord.Interaction, target_user: discord.Member):
    session = get_session()
    try:
        tasks = session.query(Task).filter_by(
            server_id=str(interaction.guild_id),
            assigned_to=str(target_user.id),
            completed=False
        ).order_by(Task.due_date).all()
        
        if not tasks:
            await interaction.response.send_message(
                f"{target_user.display_name} has no active tasks!",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title=f"Tasks for {target_user.display_name}",
            description=f"Here are the active tasks assigned to {target_user.display_name}:",
            color=discord.Color.blue()
        )
        
        for task in tasks:
            try:
                creator = await client.fetch_user(int(task.created_by)) if task.created_by != "0" else None
                creator_name = creator.display_name if creator else "Unknown"
            except:
                creator_name = "Unknown"
            
            due_date = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
            value = (
                f"Created by: {creator_name}\n"
                f"Due: {due_date}\n"
                f"Description: {task.description}"
            )
            embed.add_field(name=task.name, value=value, inline=False)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        print(f"Error in showtasks command: {str(e)}")
        print(traceback.format_exc())
        await interaction.response.send_message(
            f"An error occurred while fetching tasks: {str(e)}",
            ephemeral=True
        )
    finally:
        session.close()

@client.tree.command(
    name="quack",
    description="Get a random duck image! 🦆"
)
@log_command
async def quack(interaction: discord.Interaction):
    try:
        # Get a random duck image from random-d.uk API
        response = requests.get('https://random-d.uk/api/v2/random')
        if response.status_code == 200:
            data = response.json()
            embed = discord.Embed(
                title="Quack! 🦆",
                color=discord.Color.yellow()
            )
            embed.set_image(url=data['url'])
            embed.set_footer(text="Powered by random-d.uk")
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(
                "Sorry, I couldn't fetch a duck image right now. Try again later!",
                ephemeral=True
            )
    except Exception as e:
        print(f"Error in quack command: {str(e)}")
        print(traceback.format_exc())
        await interaction.response.send_message(
            "An error occurred while fetching the duck image. Please try again later.",
            ephemeral=True
        )

class PaginatedTaskView(discord.ui.View):
    def __init__(self, tasks, tasks_per_page=5):
        super().__init__(timeout=300)
        self.tasks = tasks
        self.tasks_per_page = tasks_per_page
        self.current_page = 0
        self.total_pages = max(1, (len(tasks) + tasks_per_page - 1) // tasks_per_page)
        
        # Update button states
        self.update_buttons()
    
    def update_buttons(self):
        # Update Previous button
        self.previous_button.disabled = (self.current_page == 0)
        
        # Update Next button  
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
    
    def get_current_page_embed(self):
        start_idx = self.current_page * self.tasks_per_page
        end_idx = min(start_idx + self.tasks_per_page, len(self.tasks))
        current_tasks = self.tasks[start_idx:end_idx]
        
        if len(self.tasks) == 0:
            embed = discord.Embed(
                title="All Active Tasks",
                description="No active tasks found in this server.",
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title="All Active Tasks",
                description=f"**Page {self.current_page + 1} of {self.total_pages}** • Showing {len(current_tasks)} of {len(self.tasks)} tasks",
                color=discord.Color.blue()
            )
            
            for i, task in enumerate(current_tasks):
                task_number = start_idx + i + 1
                # Use the pre-fetched user names we stored in the task objects
                assigned_name = getattr(task, '_assigned_name', 'Unknown')
                creator_name = getattr(task, '_creator_name', 'Unknown')
                
                due_date = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
                value = (
                    f"Assigned to: {assigned_name}\n"
                    f"Created by: {creator_name}\n"
                    f"Due: {due_date}\n"
                    f"Description: {task.description}"
                )
                embed.add_field(name=f"{task_number}. {task.name}", value=value, inline=False)
        
        return embed
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = self.get_current_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed = self.get_current_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Refresh the current page
        embed = self.get_current_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

@client.tree.command(
    name="alltasks",
    description="View all active tasks in the server (Admin only)"
)
@checks.has_permissions(administrator=True)
@log_command
async def alltasks(interaction: discord.Interaction):
    session = get_session()
    try:
        tasks = session.query(Task).filter_by(
            server_id=str(interaction.guild_id),
            completed=False
        ).order_by(Task.due_date).all()
        
        if not tasks:
            await interaction.response.send_message(
                "There are no active tasks in this server!",
                ephemeral=True
            )
            return
        
        # Defer the response since we might need time to fetch user data
        await interaction.response.defer()
        
        # Pre-fetch user information and store it in task objects
        for task in tasks:
            try:
                assigned_to = await client.fetch_user(int(task.assigned_to))
                task._assigned_name = assigned_to.display_name if assigned_to else "Unknown"
                creator = await client.fetch_user(int(task.created_by)) if task.created_by != "0" else None
                task._creator_name = creator.display_name if creator else "Unknown"
            except:
                task._assigned_name = "Unknown"
                task._creator_name = "Unknown"
        
        # Create paginated view
        view = PaginatedTaskView(tasks, tasks_per_page=5)
        embed = view.get_current_page_embed()
        
        await interaction.followup.send(embed=embed, view=view)
        
    except Exception as e:
        print(f"Error in alltasks command: {str(e)}")
        print(traceback.format_exc())
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"An error occurred while fetching tasks: {str(e)}",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                f"An error occurred while fetching tasks: {str(e)}",
                ephemeral=True
            )
    finally:
        session.close()

# Removed custom on_interaction handler - Discord.py handles command processing automatically

# ============= TICKET SYSTEM COMMANDS =============



@client.event
async def on_message(message):
    """Handle conversation messages for intmsg creation"""
    # Delegate to intmsg module
    await intmsg.handle_intmsg_message(message)










        self.message_id = message_id
        
        # Load current values
        session = get_session()
        try:
            interactive_msg = session.get(InteractiveMessage, message_id)
            current_title = interactive_msg.title if interactive_msg else ""
            current_desc = interactive_msg.description if interactive_msg else ""
            
            # Ensure color is properly formatted as #RRGGBB (7 characters max)
            if interactive_msg and interactive_msg.color:
                color_value = interactive_msg.color
                # Handle different color formats and convert to #RRGGBB
                if color_value.startswith('0x'):
                    # Convert 0x5865f2 to #5865F2
                    current_color = f"#{color_value[2:].upper()}"
                elif color_value.startswith('#'):
                    # Already in correct format, just ensure uppercase
                    current_color = color_value.upper()
                else:
                    # Assume it's just the hex digits
                    current_color = f"#{color_value.upper()}"
                
                # Ensure it's exactly 7 characters (#RRGGBB)
                if len(current_color) != 7:
                    current_color = "#5865F2"  # Default if invalid
            else:
                current_color = "#5865F2"
                
        except Exception as e:
            print(f"Error loading interactive message data: {e}")
            current_title = ""
            current_desc = ""
            current_color = "#5865F2"
        finally:
            session.close()
        
        self.title_input = discord.ui.TextInput(
            label="Message Title",
            placeholder="Enter the new title...",
            required=True,
            default=current_title,
            max_length=256
        )
        self.add_item(self.title_input)
        
        self.description_input = discord.ui.TextInput(
            label="Message Description",
            placeholder="Enter the new description...",
            required=False,
            default=current_desc,
            style=discord.TextStyle.paragraph,
            max_length=2000
        )
        self.add_item(self.description_input)
        
        self.color_input = discord.ui.TextInput(
            label="Embed Color (Hex)",
            placeholder="Enter hex color (e.g., #5865F2)",
            required=False,
            default=current_color,
            max_length=7
        )
        self.add_item(self.color_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        session = get_session()
        try:
            interactive_msg = session.get(InteractiveMessage, self.message_id)
            if not interactive_msg:
                await interaction.response.send_message("❌ Interactive message not found!", ephemeral=True)
                return
            
            # Update database
            interactive_msg.title = self.title_input.value
            interactive_msg.description = self.description_input.value
            
            # Handle color
            color = discord.Color.blurple()
            if self.color_input.value:
                try:
                    color = discord.Color(int(self.color_input.value.replace('#', ''), 16))
                    interactive_msg.color = str(hex(color.value))
                except ValueError:
                    pass
            
            session.commit()
            
            # Update the actual Discord message
            try:
                channel = client.get_channel(int(interactive_msg.channel_id))
                message = await channel.fetch_message(int(interactive_msg.message_id))
                
                # Build description with larger title and message ID
                description_text = interactive_msg.description if interactive_msg.description else ""
                if description_text:
                    updated_description = f"# {interactive_msg.title}\n\n{description_text}\n\n-# Message ID: {interactive_msg.message_id}"
                else:
                    updated_description = f"# {interactive_msg.title}\n\n-# Message ID: {interactive_msg.message_id}"
                
                embed = discord.Embed(
                    description=updated_description,
                    color=color
                )
                
                # Keep existing buttons if any
                if interactive_msg.buttons:
                    view = InteractiveMessageView(interactive_msg)
                    await message.edit(embed=embed, view=view)
                else:
                    await message.edit(embed=embed, view=None)
                
                await interaction.response.send_message("✅ Interactive message updated successfully!", ephemeral=True)
                
            except Exception as e:
                print(f"Error updating Discord message: {e}")
                await interaction.response.send_message("✅ Database updated, but couldn't update Discord message. Try using 'Update & Refresh' button.", ephemeral=True)
                
        except Exception as e:
            print(f"Error updating interactive message: {e}")
            await interaction.response.send_message("❌ An error occurred while updating the message.", ephemeral=True)
        finally:
            session.close()

class ButtonRemovalView(discord.ui.View):
    def __init__(self, message_id, options):
        super().__init__(timeout=60)
        self.message_id = message_id
        
        select = ButtonRemovalSelect(message_id, options)
        self.add_item(select)

class ButtonRemovalSelect(discord.ui.Select):
    def __init__(self, message_id, options):
        super().__init__(
            placeholder="Choose a button to remove...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.message_id = message_id
    
    async def callback(self, interaction: discord.Interaction):
        session = get_session()
        try:
            button_id = int(self.values[0])
            button = session.get(MessageButton, button_id)
            
            if not button:
                await interaction.response.send_message("❌ Button not found!", ephemeral=True)
                return
            
            button_label = button.label
            session.delete(button)
            session.commit()
            
            await interaction.response.send_message(f"✅ Button '{button_label}' removed successfully!", ephemeral=True)
            
        except Exception as e:
            print(f"Error removing button: {e}")
            await interaction.response.send_message("❌ An error occurred while removing the button.", ephemeral=True)
        finally:
            session.close()

class MessageManagementView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=300)
        self.message_id = message_id
    
    @discord.ui.button(label="Add Ticket Button", style=discord.ButtonStyle.primary, emoji="🎫")
    async def add_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ButtonSetupModal(self.message_id, 'ticket')
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Add Role Button", style=discord.ButtonStyle.secondary, emoji="👤")
    async def add_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ButtonSetupModal(self.message_id, 'role')
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Update Message", style=discord.ButtonStyle.success, emoji="🔄")
    async def update_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_interactive_message(interaction)
    
    async def _update_interactive_message(self, interaction: discord.Interaction):
        session = get_session()
        try:
            interactive_msg = session.get(InteractiveMessage, self.message_id)
            if not interactive_msg:
                await interaction.response.send_message("❌ Interactive message not found!", ephemeral=True)
                return
            
            # Get the original message
            try:
                channel = client.get_channel(int(interactive_msg.channel_id))
                message = await channel.fetch_message(int(interactive_msg.message_id))
            except:
                await interaction.response.send_message("❌ Could not find the original message!", ephemeral=True)
                return
            
            # Create new embed with message ID and larger title
            color = discord.Color(int(interactive_msg.color, 16))
            
            # Build description with larger title and message ID
            description_text = interactive_msg.description if interactive_msg.description else ""
            if description_text:
                updated_description = f"# {interactive_msg.title}\n\n{description_text}\n\n-# Message ID: {interactive_msg.message_id}"
            else:
                updated_description = f"# {interactive_msg.title}\n\n-# Message ID: {interactive_msg.message_id}"
            
            embed = discord.Embed(
                description=updated_description,
                color=color
            )
            
            # Create view with buttons
            if interactive_msg.buttons:
                view = InteractiveMessageView(interactive_msg)
                await message.edit(embed=embed, view=view)
            else:
                await message.edit(embed=embed, view=None)
            
            await interaction.response.send_message("✅ Interactive message updated with current buttons!", ephemeral=True)
            
        except Exception as e:
            print(f"Error updating interactive message: {e}")
            await interaction.response.send_message("❌ An error occurred while updating the message.", ephemeral=True)
        finally:
            session.close()

@client.tree.command(
    name="intmsg",
    description="Create an interactive message with customizable buttons"
)
@log_command
async def intmsg(interaction: discord.Interaction):
    """Create an interactive message with buttons for tickets and roles"""
    # Check if user can create interactive messages
    if not await can_create_intmsg(interaction):
        await interaction.response.send_message(
            "❌ You don't have permission to create interactive messages!\n\n"
            "Only administrators or whitelisted users can use this command.\n"
            "Ask an admin to add you with `/imw add @user`",
            ephemeral=True
        )
        return
    
    await interaction.response.send_message(
        "🎨 **Interactive Message Creator Started!**\n\n"
        "I'll guide you through creating your interactive message. You can cancel anytime by typing `cancel`.\n\n"
        "**Step 1/7:** What should the **title** of your message be?",
        ephemeral=True
    )
    
    # Start the conversation flow
    await start_intmsg_conversation(interaction)

@client.tree.command(
    name="imw",
    description="Add or remove a user from the interactive message creator whitelist (Admin only)"
)
@app_commands.describe(
    user="The user to add/remove from the interactive message creator whitelist",
    action="The action to perform: 'add' or 'remove'"
)
@checks.has_permissions(administrator=True)
@log_command
async def imw(interaction: discord.Interaction, user: discord.Member, action: str):
    """Manage interactive message creator whitelist"""
    if action.lower() not in ['add', 'remove']:
        await interaction.response.send_message(
            "❌ Invalid action! Use 'add' or 'remove'.",
            ephemeral=True
        )
        return
    
    session = get_session()
    try:
        existing_creator = session.query(IntMsgCreator).filter_by(
            user_id=str(user.id),
            server_id=str(interaction.guild_id)
        ).first()
        
        if action.lower() == 'add':
            if existing_creator:
                await interaction.response.send_message(
                    f"❌ {user.display_name} is already in the interactive message creator whitelist!",
                    ephemeral=True
                )
                return
            
            new_creator = IntMsgCreator(
                user_id=str(user.id),
                server_id=str(interaction.guild_id),
                added_by=str(interaction.user.id)
            )
            session.add(new_creator)
            session.commit()
            
            await interaction.response.send_message(
                f"✅ Added {user.display_name} to the interactive message creator whitelist!\n"
                f"They can now use `/intmsg` to create interactive messages.",
                ephemeral=True
            )
            
        else:  # remove
            if not existing_creator:
                await interaction.response.send_message(
                    f"❌ {user.display_name} is not in the interactive message creator whitelist!",
                    ephemeral=True
                )
                return
            
            session.delete(existing_creator)
            session.commit()
            
            await interaction.response.send_message(
                f"✅ Removed {user.display_name} from the interactive message creator whitelist!\n"
                f"They can no longer use `/intmsg` (unless they're an admin).",
                ephemeral=True
            )
            
    except Exception as e:
        print(f"Error in imw command: {str(e)}")
        print(traceback.format_exc())
        await interaction.response.send_message(
            f"An error occurred while updating the whitelist: {str(e)}",
            ephemeral=True
        )
    finally:
        session.close()

@client.tree.command(
    name="editintmsg",
    description="Edit an existing interactive message and its buttons"
)
@app_commands.describe(
    message_id="The ID of the interactive message to edit"
)
@checks.has_permissions(manage_messages=True)
@log_command
async def editintmsg(interaction: discord.Interaction, message_id: str):
    """Edit an interactive message and its buttons"""
    session = get_session()
    try:
        # Look up by Discord message ID (not database ID)
        interactive_msg = session.query(InteractiveMessage).filter_by(message_id=message_id).first()
        if not interactive_msg:
            await interaction.response.send_message(
                f"❌ Interactive message not found!\n"
                f"**Tried to find:** {message_id}\n"
                f"Make sure you're using the Discord message ID, not the database ID.\n"
                f"Use `/listmessages` to see available messages.",
                ephemeral=True
            )
            return
        
        if str(interaction.guild_id) != interactive_msg.server_id:
            await interaction.response.send_message("❌ That message doesn't belong to this server!", ephemeral=True)
            return
        
        # Show comprehensive editing options
        view = EditIntMsgView(interactive_msg.id)
        
        # Show current message info
        button_count = len(interactive_msg.buttons)
        ticket_buttons = sum(1 for b in interactive_msg.buttons if b.button_type == 'ticket')
        role_buttons = sum(1 for b in interactive_msg.buttons if b.button_type == 'role')
        
        embed = discord.Embed(
            title="🛠️ Editing Interactive Message",
            description=f"**Message:** {interactive_msg.title}\n"
                       f"**Current Buttons:** {button_count} total ({ticket_buttons} ticket, {role_buttons} role)\n"
                       f"**Created:** {interactive_msg.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                       f"Choose what you want to edit:",
            color=discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
    except Exception as e:
        print(f"Error in editintmsg command: {e}")
        await interaction.response.send_message("❌ An error occurred while processing the command.", ephemeral=True)
    finally:
        session.close()

# OBSOLETE: /addbutton command replaced by integrated /intmsg workflow
# @client.tree.command(
#     name="addbutton",
#     description="Add a button to an existing interactive message"
# )
# @app_commands.describe(
#     message_id="The ID of the interactive message to add a button to"
# )
# @checks.has_permissions(manage_messages=True)
# @log_command
# async def addbutton(interaction: discord.Interaction, message_id: str):
#     """Add buttons to an interactive message"""
#     # This command has been replaced by the integrated /intmsg workflow
#     await interaction.response.send_message(
#         "❌ This command has been replaced! Use `/intmsg` to create messages with buttons, or `/editintmsg` to edit existing ones.",
#         ephemeral=True
#     )

@client.tree.command(
    name="listmessages",
    description="List all interactive messages in this server"
)
@checks.has_permissions(manage_messages=True)
@log_command
async def listmessages(interaction: discord.Interaction):
    """List all interactive messages in the server"""
    session = get_session()
    try:
        messages = session.query(InteractiveMessage).filter_by(
            server_id=str(interaction.guild_id)
        ).order_by(InteractiveMessage.created_at.desc()).all()
        
        if not messages:
            await interaction.response.send_message("❌ No interactive messages found in this server!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title="📋 Interactive Messages",
            description="Here are all the interactive messages in this server:",
            color=discord.Color.blue()
        )
        
        for msg in messages:
            button_count = len(msg.buttons)
            ticket_buttons = sum(1 for b in msg.buttons if b.button_type == 'ticket')
            role_buttons = sum(1 for b in msg.buttons if b.button_type == 'role')
            
            value = (
                f"**ID:** {msg.id}\n"
                f"**Channel:** <#{msg.channel_id}>\n"
                f"**Buttons:** {button_count} total ({ticket_buttons} ticket, {role_buttons} role)\n"
                f"**Created:** {msg.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
            )
            embed.add_field(name=msg.title, value=value, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"Error in listmessages command: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching messages.", ephemeral=True)
    finally:
        session.close()

@client.tree.command(
    name="ticketstats",
    description="View ticket statistics for this server"
)
@checks.has_permissions(manage_messages=True)
@log_command
async def ticketstats(interaction: discord.Interaction):
    """View ticket statistics"""
    session = get_session()
    try:
        total_tickets = session.query(Ticket).filter_by(server_id=str(interaction.guild_id)).count()
        open_tickets = session.query(Ticket).filter_by(server_id=str(interaction.guild_id), status="open").count()
        closed_tickets = session.query(Ticket).filter_by(server_id=str(interaction.guild_id), status="closed").count()
        
        embed = discord.Embed(
            title="🎫 Ticket Statistics",
            color=discord.Color.green()
        )
        embed.add_field(name="Total Tickets", value=str(total_tickets), inline=True)
        embed.add_field(name="Open Tickets", value=str(open_tickets), inline=True)
        embed.add_field(name="Closed Tickets", value=str(closed_tickets), inline=True)
        
        if total_tickets > 0:
            # Recent tickets
            recent_tickets = session.query(Ticket).filter_by(
                server_id=str(interaction.guild_id)
            ).order_by(Ticket.created_at.desc()).limit(5).all()
            
            recent_list = []
            for ticket in recent_tickets:
                try:
                    creator = await client.fetch_user(int(ticket.creator_id))
                    creator_name = creator.display_name
                except:
                    creator_name = "Unknown"
                
                status_emoji = "🟢" if ticket.status == "open" else "🔴"
                recent_list.append(f"{status_emoji} Ticket #{ticket.ticket_id} - {creator_name}")
            
            embed.add_field(
                name="Recent Tickets",
                value="\n".join(recent_list) if recent_list else "None",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"Error in ticketstats command: {e}")
        await interaction.response.send_message("❌ An error occurred while fetching statistics.", ephemeral=True)
    finally:
        session.close()

@client.tree.command(
    name="fixdb",
    description="Fix database schema issues (Admin only)"
)
@checks.has_permissions(administrator=True)
@log_command
async def fixdb(interaction: discord.Interaction):
    """Fix database schema by adding missing columns"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        # Import the database fix function
        import sqlite3
        import os
        
        db_path = os.path.join('data', 'tasks.db')
        
        if not os.path.exists(db_path):
            await interaction.followup.send("❌ Database file not found!", ephemeral=True)
            return
        
        fixed_items = []
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add missing columns to tickets table
        try:
            cursor.execute("ALTER TABLE tickets ADD COLUMN questions_answers TEXT")
            fixed_items.append("✅ Added questions_answers column to tickets table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                fixed_items.append(f"⚠️ tickets.questions_answers: {e}")
        
        # Add missing columns to message_buttons table
        try:
            cursor.execute("ALTER TABLE message_buttons ADD COLUMN ticket_questions TEXT")
            fixed_items.append("✅ Added ticket_questions column to message_buttons table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                fixed_items.append(f"⚠️ message_buttons.ticket_questions: {e}")
        
        try:
            cursor.execute("ALTER TABLE message_buttons ADD COLUMN ticket_visible_roles TEXT")
            fixed_items.append("✅ Added ticket_visible_roles column to message_buttons table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                fixed_items.append(f"⚠️ message_buttons.ticket_visible_roles: {e}")
        
        # Create intmsg_creators table if it doesn't exist
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS intmsg_creators (
                    id INTEGER PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    added_by TEXT NOT NULL,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            fixed_items.append("✅ Created/verified intmsg_creators table")
        except sqlite3.OperationalError as e:
            fixed_items.append(f"⚠️ intmsg_creators table: {e}")
        
        conn.commit()
        conn.close()
        
        # Reload persistent views after fixing database
        await client.load_persistent_views()
        
        result_text = "🔧 **Database Fix Results:**\n\n" + "\n".join(fixed_items)
        result_text += "\n\n🔄 **Persistent views reloaded!**\nAll interactive messages should now work after bot restarts."
        
        await interaction.followup.send(result_text, ephemeral=True)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Database fix failed: {str(e)}", ephemeral=True)
        print(f"Database fix error: {e}")
        print(traceback.format_exc())

@client.tree.command(
    name="testpersistence",
    description="Test the persistence system (Admin only)"
)
@checks.has_permissions(administrator=True)
@log_command
async def testpersistence(interaction: discord.Interaction):
    """Test persistence system without restarting"""
    await interaction.response.defer(ephemeral=True)
    
    await interaction.followup.send("🔄 Testing persistence system...", ephemeral=True)
    
    # Run the persistence loading system
    await client.load_persistent_views()
    
    await interaction.followup.send("✅ Persistence test complete! Check console for detailed output.", ephemeral=True)



@client.tree.command(
    name="help",
    description="Show all available commands and their descriptions"
)
@log_command
async def help_command(interaction: discord.Interaction):
    """Display comprehensive help information"""
    
    embed = discord.Embed(
        title="🤖 Puddles Bot - Command Help",
        description="Here are all the available commands and how to use them:",
        color=discord.Color.blue()
    )
    
    # Task Management Commands
    embed.add_field(
        name="📋 **Task Management**",
        value=(
            "`/task` - Create a new task with name, assignee, due date, and description\n"
            "`/mytasks` - View all tasks assigned to you\n"
            "`/taskedit` - Edit your existing tasks (name, due date, description, assignee)\n"
            "`/showtasks @user` - View tasks assigned to a specific user\n"
            "`/alltasks` - **[Admin]** View all active tasks in the server (paginated)\n"
            "`/tcw @user add/remove` - **[Admin]** Manage task creator whitelist"
        ),
        inline=False
    )
    
    # Interactive Message & Ticket System
    embed.add_field(
        name="🎫 **Interactive Messages & Tickets**",
        value=(
            "`/intmsg` - Create interactive messages with ticket/role buttons\n"
            "`/editintmsg [message_id]` - **[Staff]** Edit existing interactive messages\n"
            "`/listmessages` - **[Staff]** List all interactive messages in the server\n"
            "`/ticketstats` - **[Staff]** View ticket statistics and recent activity\n"
            "`/imw @user add/remove` - **[Admin]** Manage interactive message creator whitelist"
        ),
        inline=False
    )
    
    # Fun & Utility Commands
    embed.add_field(
        name="🎮 **Fun & Utility**",
        value=(
            "`/quack` - Get a random duck image 🦆\n"
            "`/diceroll [1-100]` - Roll dice and see visual results with statistics\n"
            "`/help` - Show this help message"
        ),
        inline=False
    )
    
    # Admin & System Commands
    embed.add_field(
        name="🔧 **Admin & System**",
        value=(
            "`/fixdb` - **[Admin]** Fix database schema issues\n"
            "`/testpersistence` - **[Admin]** Test the persistence system"
        ),
        inline=False
    )
    
    # Permission Legend
    embed.add_field(
        name="🔑 **Permission Legend**",
        value=(
            "**[Admin]** - Requires Administrator permission\n"
            "**[Staff]** - Requires Manage Messages permission\n"
            "No tag - Available to all users (some may require whitelist)"
        ),
        inline=False
    )
    
    # Additional Info
    embed.add_field(
        name="💡 **Special Features**",
        value=(
            "• **Persistent Views** - Buttons work even after bot restarts\n"
            "• **Task Notifications** - Get DMs when tasks are due soon\n"
            "• **Ticket System** - Create support tickets with custom questions\n"
            "• **Role Management** - Assign/remove roles with buttons\n"
            "• **Pagination** - Large lists are split into easy-to-read pages\n"
            "• **Ping Support** - Use @everyone/@here in interactive messages"
        ),
        inline=False
    )
    
    embed.set_footer(text="For detailed help with any command, try using it and see the prompts!")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ============= END TICKET SYSTEM COMMANDS =============

# Keep the bot alive
keep_alive()

# Start the bot with the token
client.run(os.getenv('TOKEN')) 