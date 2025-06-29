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
from ticket_system import (
    InteractiveMessage, MessageButton, Ticket, 
    InteractiveMessageView, ButtonSetupModal
)

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
            print("Available commands: /task, /mytasks, /taskedit, /showtasks, /alltasks, /tcw, /quack")
            print("Ticket system commands: /intmsg, /addbutton, /listmessages, /ticketstats")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
            print("Full error:", traceback.format_exc())
        
        self.scheduler.start()
        self.scheduler.add_job(self.check_due_tasks, 'interval', hours=1)
        # Add backup job to run every 6 hours
        self.scheduler.add_job(self.backup_database, 'interval', hours=6)
        
        # Load persistent views for ticket system
        await self.load_persistent_views()

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
        try:
            # Load interactive message views
            interactive_messages = session.query(InteractiveMessage).all()
            restored_messages = 0
            
            for msg_data in interactive_messages:
                try:
                    # Get the channel and message
                    channel = self.get_channel(int(msg_data.channel_id))
                    if not channel:
                        continue
                    
                    message = await channel.fetch_message(int(msg_data.message_id))
                    if not message:
                        continue
                    
                    # Only add view if there are buttons
                    if msg_data.buttons:
                        view = InteractiveMessageView(msg_data)
                        # Don't edit the message, just add the view for future interactions
                        self.add_view(view, message_id=int(msg_data.message_id))
                        restored_messages += 1
                        
                except Exception as e:
                    print(f"Error restoring interactive message {msg_data.id}: {e}")
                    continue
            
            # Load ticket control views
            open_tickets = session.query(Ticket).filter_by(status="open").all()
            restored_tickets = 0
            
            for ticket in open_tickets:
                try:
                    channel = self.get_channel(int(ticket.channel_id))
                    if channel:
                        view = TicketControlView(ticket.id)
                        self.add_view(view)
                        restored_tickets += 1
                except Exception as e:
                    print(f"Error restoring ticket view {ticket.id}: {e}")
                    continue
            
            print(f"Restored {restored_messages} interactive message views and {restored_tickets} ticket views")
            
        except Exception as e:
            print(f"Error loading persistent views: {e}")
            print(traceback.format_exc())
        finally:
            session.close()

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
            
        embed = discord.Embed(
            title="All Active Tasks",
            description="Here are all active tasks in the server:",
            color=discord.Color.blue()
        )
        
        for task in tasks:
            try:
                assigned_to = await client.fetch_user(int(task.assigned_to))
                assigned_name = assigned_to.display_name if assigned_to else "Unknown"
                creator = await client.fetch_user(int(task.created_by)) if task.created_by != "0" else None
                creator_name = creator.display_name if creator else "Unknown"
            except:
                assigned_name = "Unknown"
                creator_name = "Unknown"
            
            due_date = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
            value = (
                f"Assigned to: {assigned_name}\n"
                f"Created by: {creator_name}\n"
                f"Due: {due_date}\n"
                f"Description: {task.description}"
            )
            embed.add_field(name=task.name, value=value, inline=False)
        
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

# Removed custom on_interaction handler - Discord.py handles command processing automatically

# ============= TICKET SYSTEM COMMANDS =============

class MessageSetupModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Create Interactive Message")
        
        self.title_input = discord.ui.TextInput(
            label="Message Title",
            placeholder="Enter the title for your interactive message...",
            required=True,
            max_length=256
        )
        self.add_item(self.title_input)
        
        self.description_input = discord.ui.TextInput(
            label="Message Description", 
            placeholder="Enter the description for your interactive message...",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=2000
        )
        self.add_item(self.description_input)
        
        self.color_input = discord.ui.TextInput(
            label="Embed Color (Hex)",
            placeholder="Enter hex color (e.g., #5865F2) or leave blank for default",
            required=False,
            max_length=7
        )
        self.add_item(self.color_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        session = get_session()
        try:
            # Create embed
            color = discord.Color.blurple()
            if self.color_input.value:
                try:
                    color = discord.Color(int(self.color_input.value.replace('#', ''), 16))
                except ValueError:
                    pass
            
            # Build description with message ID
            description_text = self.description_input.value if self.description_input.value else ""
            
            embed = discord.Embed(
                title=self.title_input.value,
                description=description_text,
                color=color
            )
            
            # Send the message first to get the message ID
            message = await interaction.response.send_message(embed=embed, view=None)
            message = await interaction.original_response()
            
            # Update the embed with the message ID at the bottom
            if description_text:
                updated_description = f"{description_text}\n\n-# Message ID: {message.id}"
            else:
                updated_description = f"-# Message ID: {message.id}"
            
            embed.description = updated_description
            await message.edit(embed=embed)
            
            # Save to database
            interactive_msg = InteractiveMessage(
                message_id=str(message.id),
                channel_id=str(interaction.channel_id),
                server_id=str(interaction.guild_id),
                title=self.title_input.value,
                description=self.description_input.value,
                color=str(hex(color.value)),
                created_by=str(interaction.user.id)
            )
            session.add(interactive_msg)
            session.commit()
            
            # Send follow-up with instructions
            await interaction.followup.send(
                f"✅ Interactive message created! Use `/addbutton {interactive_msg.id}` to add buttons to it.",
                ephemeral=True
            )
            
        except Exception as e:
            print(f"Error creating interactive message: {e}")
            await interaction.response.send_message(
                "❌ An error occurred while creating the interactive message.",
                ephemeral=True
            )
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
            interactive_msg = session.query(InteractiveMessage).get(self.message_id)
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
            
            # Create new embed with message ID
            color = discord.Color(int(interactive_msg.color, 16))
            
            # Build description with message ID
            description_text = interactive_msg.description if interactive_msg.description else ""
            if description_text:
                updated_description = f"{description_text}\n\n-# Message ID: {interactive_msg.message_id}"
            else:
                updated_description = f"-# Message ID: {interactive_msg.message_id}"
            
            embed = discord.Embed(
                title=interactive_msg.title,
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
@checks.has_permissions(manage_messages=True)
@log_command
async def intmsg(interaction: discord.Interaction):
    """Create an interactive message with buttons for tickets and roles"""
    modal = MessageSetupModal()
    await interaction.response.send_modal(modal)

@client.tree.command(
    name="addbutton",
    description="Add a button to an existing interactive message"
)
@app_commands.describe(
    message_id="The ID of the interactive message to add a button to"
)
@checks.has_permissions(manage_messages=True)
@log_command
async def addbutton(interaction: discord.Interaction, message_id: str):
    """Add buttons to an interactive message"""
    session = get_session()
    try:
        # Try to convert message_id to int for database lookup
        try:
            db_message_id = int(message_id)
        except ValueError:
            await interaction.response.send_message("❌ Invalid message ID format!", ephemeral=True)
            return
        
        interactive_msg = session.query(InteractiveMessage).get(db_message_id)
        if not interactive_msg:
            await interaction.response.send_message("❌ Interactive message not found!", ephemeral=True)
            return
        
        if str(interaction.guild_id) != interactive_msg.server_id:
            await interaction.response.send_message("❌ That message doesn't belong to this server!", ephemeral=True)
            return
        
        view = MessageManagementView(db_message_id)
        await interaction.response.send_message(
            f"**Managing Interactive Message:** {interactive_msg.title}\n\n"
            "Choose what type of button you want to add:",
            view=view,
            ephemeral=True
        )
        
    except Exception as e:
        print(f"Error in addbutton command: {e}")
        await interaction.response.send_message("❌ An error occurred while processing the command.", ephemeral=True)
    finally:
        session.close()

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

# ============= END TICKET SYSTEM COMMANDS =============

# Keep the bot alive
keep_alive()

# Start the bot with the token
client.run(os.getenv('TOKEN')) 