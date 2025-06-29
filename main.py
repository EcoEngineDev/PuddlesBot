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
            await self.tree.sync(guild=None)  # None means global sync
            print("Commands synced successfully!")
            print("Available commands: /task, /mytasks, /taskedit, /quack")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
            print("Full error:", traceback.format_exc())
        
        self.scheduler.start()
        self.scheduler.add_job(self.check_due_tasks, 'interval', hours=1)

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

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
    description="Add a user to the task creator whitelist (Admin only)"
)
@app_commands.describe(
    user="The user to add to the task creator whitelist"
)
@checks.has_permissions(administrator=True)
@log_command
async def tcw(interaction: discord.Interaction, user: discord.Member):
    session = get_session()
    try:
        # Check if user is already whitelisted
        existing = session.query(TaskCreator).filter_by(
            user_id=str(user.id),
            server_id=str(interaction.guild_id)
        ).first()
        
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
        
    except Exception as e:
        print(f"Error in tcw command: {str(e)}")
        print(traceback.format_exc())
        await interaction.response.send_message(
            f"An error occurred while adding the user to the whitelist: {str(e)}",
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

@client.tree.command(
    name="taskedit",
    description="Edit a task (Admin only)"
)
@app_commands.describe(
    task_name="Name of the task to edit",
    new_name="New name for the task (optional)",
    new_assigned_to="New user to assign the task to (optional)",
    new_due_date="New due date in YYYY-MM-DD HH:MM format (optional)",
    new_description="New description for the task (optional)"
)
async def taskedit(
    interaction: discord.Interaction,
    task_name: str,
    new_name: Optional[str] = None,
    new_assigned_to: Optional[discord.Member] = None,
    new_due_date: Optional[str] = None,
    new_description: Optional[str] = None
):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("You need administrator permissions to edit tasks.", ephemeral=True)
        return
        
    session = get_session()
    try:
        task = session.query(Task).filter_by(name=task_name).first()
        if not task:
            await interaction.response.send_message(f"Task '{task_name}' not found.", ephemeral=True)
            return
            
        if new_name:
            task.name = new_name
        if new_assigned_to:
            task.assigned_to = str(new_assigned_to.id)
        if new_due_date:
            try:
                task.due_date = parser.parse(new_due_date)
            except ValueError:
                await interaction.response.send_message("Invalid date format. Please use YYYY-MM-DD HH:MM format.", ephemeral=True)
                return
        if new_description:
            task.description = new_description
            
        session.commit()
        
        embed = discord.Embed(
            title="✅ Task Updated",
            description=f"Task '{task_name}' has been updated",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)
        
        if new_assigned_to:
            try:
                await new_assigned_to.send(f"You have been assigned to the task: **{task.name}**\nDue: {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}\n\nDescription:\n{task.description}")
            except discord.Forbidden:
                pass
                
    finally:
        session.close()

@client.tree.command(
    name="quack",
    description="Get a random duck image!"
)
async def quack(interaction: discord.Interaction):
    response = requests.get('https://random-d.uk/api/v2/random')
    if response.status_code == 200:
        duck_data = response.json()
        embed = discord.Embed(title="Quack! 🦆", color=discord.Color.yellow())
        embed.set_image(url=duck_data['url'])
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Sorry, couldn't fetch a duck right now! 😢")

@client.tree.command(
    name="oldtasks",
    description="View completed tasks"
)
@log_command
async def oldtasks(interaction: discord.Interaction):
    session = get_session()
    try:
        tasks = session.query(Task).filter_by(
            assigned_to=str(interaction.user.id),
            server_id=str(interaction.guild_id),
            completed=True
        ).order_by(Task.completed_at.desc()).all()
        
        if not tasks:
            await interaction.response.send_message(
                "You have no completed tasks!",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title="Your Completed Tasks",
            description="Here are your completed tasks:",
            color=discord.Color.green()
        )
        
        for task in tasks:
            completed_time = task.completed_at.strftime('%Y-%m-%d %H:%M UTC') if task.completed_at else "Unknown"
            due_date = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
            
            try:
                creator = await client.fetch_user(int(task.created_by)) if task.created_by != "0" else None
                creator_name = creator.display_name if creator else "Unknown"
            except:
                creator_name = "Unknown"
            
            value = (
                f"Due Date: {due_date}\n"
                f"Completed: {completed_time}\n"
                f"Created by: {creator_name}\n"
                f"Description: {task.description}"
            )
            embed.add_field(name=task.name, value=value, inline=False)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        print(f"Error in oldtasks command: {str(e)}")
        print(traceback.format_exc())
        await interaction.response.send_message(
            f"An error occurred while fetching your completed tasks: {str(e)}",
            ephemeral=True
        )
    finally:
        session.close()

@client.tree.command(
    name="alltasks",
    description="View all active tasks in the server"
)
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
                "There are no active tasks in the server!",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title="All Active Tasks",
            description="Here are all active tasks in the server:",
            color=discord.Color.blue()
        )
        
        for task in tasks:
            try:
                assigned_user = await client.fetch_user(int(task.assigned_to))
                creator_user = await client.fetch_user(int(task.created_by))
                assigned_name = assigned_user.display_name if assigned_user else "Unknown User"
                creator_name = creator_user.display_name if creator_user else "Unknown User"
                
                due_date = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
                value = (
                    f"Assigned to: {assigned_name}\n"
                    f"Created by: {creator_name}\n"
                    f"Due: {due_date}\n"
                    f"Description: {task.description}"
                )
                embed.add_field(name=task.name, value=value, inline=False)
            except:
                continue
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        print(f"Error in alltasks command: {str(e)}")
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
    user="The user whose tasks you want to view"
)
@log_command
async def showtasks(interaction: discord.Interaction, user: discord.Member):
    session = get_session()
    try:
        tasks = session.query(Task).filter_by(
            server_id=str(interaction.guild_id),
            assigned_to=str(user.id),
            completed=False
        ).order_by(Task.due_date).all()
        
        if not tasks:
            await interaction.response.send_message(
                f"{user.display_name} has no active tasks!",
                ephemeral=True
            )
            return
            
        embed = discord.Embed(
            title=f"Tasks for {user.display_name}",
            description=f"Here are the active tasks assigned to {user.display_name}:",
            color=discord.Color.blue()
        )
        
        for task in tasks:
            creator_user = await client.fetch_user(int(task.created_by))
            creator_name = creator_user.display_name if creator_user else "Unknown User"
            
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

@client.event
async def on_interaction(interaction: discord.Interaction):
    try:
        # Let the command tree handle the interaction
        if interaction.type == discord.InteractionType.application_command:
            command = client.tree.get_command(interaction.command.name)
            if command:
                await command.callback(interaction)
            else:
                await interaction.response.send_message(
                    "Command not found.",
                    ephemeral=True
                )
    except Exception as e:
        print(f"Error in on_interaction:")
        print(traceback.format_exc())
        
        # Only send error message if the interaction hasn't been responded to
        if not interaction.response.is_done():
            try:
                await interaction.response.send_message(
                    "An error occurred while processing the command. Please try again.",
                    ephemeral=True
                )
            except:
                pass  # Ignore any errors in error handling

# Keep the bot alive
keep_alive()

# Start the bot with the token
client.run(os.getenv('TOKEN')) 