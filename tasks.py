import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from dateutil import parser
from database import Task, TaskCreator, get_session
import asyncio
from typing import Optional, Callable, Any
import traceback
from discord.app_commands import checks
import functools

# Store reference to the client
_client = None

def setup_task_system(client):
    """Initialize the task system with client reference"""
    global _client
    _client = client

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
    """Check if user can create tasks"""
    # Check if user is administrator
    if interaction.user.guild_permissions.administrator:
        return True
    
    # Check if user is in the task creator whitelist
    session = get_session(str(interaction.guild_id))
    try:
        creator = session.query(TaskCreator).filter_by(
            user_id=str(interaction.user.id),
            server_id=str(interaction.guild_id)
        ).first()
        return creator is not None
    finally:
        session.close()

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
        session = get_session(str(interaction.guild_id))
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

        session = get_session(str(interaction.guild_id))
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

class TaskEditSelect(discord.ui.Select):
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
            placeholder="Choose a task to edit...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        view: TaskEditView = self.view
        task_id = int(self.values[0])
        
        # Find the selected task
        selected_task = None
        for task in self.task_list:
            if task.id == task_id:
                selected_task = task
                break
        
        if not selected_task:
            await interaction.response.send_message("Task not found!", ephemeral=True)
            return
        
        view.selected_task = selected_task
        
        # Enable all edit buttons
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = False
        
        embed = discord.Embed(
            title=f"Editing Task: {selected_task.name}",
            description=f"**Current Description:** {selected_task.description}\n**Due Date:** {selected_task.due_date.strftime('%Y-%m-%d %H:%M UTC')}",
            color=discord.Color.orange()
        )
        
        await interaction.response.edit_message(embed=embed, view=view)

class TaskEditView(discord.ui.View):
    def __init__(self, tasks, user):
        super().__init__(timeout=300)  # 5 minute timeout
        self.tasks = tasks
        self.user = user
        self.selected_task = None
        
        # Add task selection dropdown
        self.add_item(TaskEditSelect(tasks))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the user who initiated the edit can use the buttons"""
        if interaction.user != self.user:
            await interaction.response.send_message(
                "You cannot edit someone else's task selection!", 
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Edit Name", custom_id="edit_name_btn", style=discord.ButtonStyle.primary, disabled=True, row=1)
    async def edit_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_task:
            modal = TaskEditModal(self.selected_task, "name")
            await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Due Date", custom_id="edit_due_date_btn", style=discord.ButtonStyle.primary, disabled=True, row=1)
    async def edit_due_date(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_task:
            modal = TaskEditModal(self.selected_task, "due_date")
            await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Description", custom_id="edit_desc_btn", style=discord.ButtonStyle.primary, disabled=True, row=2)
    async def edit_description(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_task:
            modal = TaskEditModal(self.selected_task, "description")
            await interaction.response.send_modal(modal)

    @discord.ui.button(label="Change Assignee", custom_id="edit_assignee_btn", style=discord.ButtonStyle.primary, disabled=True, row=2)
    async def edit_assignee(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_task:
            modal = TaskEditModal(self.selected_task, "assigned_to")
            await interaction.response.send_modal(modal)

class TaskEditModal(discord.ui.Modal):
    def __init__(self, task: Task, field: str):
        self.task = task
        self.field = field
        
        if field == "name":
            super().__init__(title="Edit Task Name")
            self.text_input = discord.ui.TextInput(
                label="Task Name",
                placeholder="Enter the new task name...",
                default=task.name,
                max_length=256
            )
        elif field == "due_date":
            super().__init__(title="Edit Due Date")
            self.text_input = discord.ui.TextInput(
                label="Due Date (YYYY-MM-DD HH:MM)",
                placeholder="Enter the new due date...",
                default=task.due_date.strftime('%Y-%m-%d %H:%M'),
                max_length=16
            )
        elif field == "description":
            super().__init__(title="Edit Task Description")
            self.text_input = discord.ui.TextInput(
                label="Task Description",
                placeholder="Enter the new task description...",
                default=task.description,
                style=discord.TextStyle.paragraph,
                max_length=1000
            )
        elif field == "assigned_to":
            super().__init__(title="Change Task Assignee")
            self.text_input = discord.ui.TextInput(
                label="New Assignee (User ID)",
                placeholder="Enter the user ID of the new assignee...",
                default=task.assigned_to,
                max_length=20
            )
        
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction):
        session = get_session(str(interaction.guild_id))
        try:
            # Get the latest version of the task from the database
            task = session.query(Task).get(self.task.id)
            if not task:
                await interaction.response.send_message("Task not found!", ephemeral=True)
                return

            old_value = None
            new_value = self.text_input.value

            if self.field == "name":
                old_value = task.name
                task.name = new_value
            elif self.field == "due_date":
                old_value = task.due_date.strftime('%Y-%m-%d %H:%M')
                try:
                    new_due_date = parser.parse(new_value)
                    task.due_date = new_due_date
                except ValueError:
                    await interaction.response.send_message(
                        "Invalid date format! Please use YYYY-MM-DD HH:MM format.",
                        ephemeral=True
                    )
                    return
            elif self.field == "description":
                old_value = task.description
                task.description = new_value
            elif self.field == "assigned_to":
                old_value = task.assigned_to
                try:
                    # Validate that the user ID exists and is a number
                    user_id = int(new_value)
                    # Try to fetch the user to verify they exist
                    user = await _client.fetch_user(user_id)
                    task.assigned_to = str(user_id)
                except (ValueError, discord.NotFound):
                    await interaction.response.send_message(
                        "Invalid user ID! Please provide a valid Discord user ID.",
                        ephemeral=True
                    )
                    return

            session.commit()
            
            embed = discord.Embed(
                title="✅ Task Updated",
                description=f"Task '{task.name}' has been updated successfully!",
                color=discord.Color.green()
            )
            embed.add_field(name="Field Changed", value=self.field.replace('_', ' ').title(), inline=True)
            embed.add_field(name="Old Value", value=str(old_value)[:100], inline=True)
            embed.add_field(name="New Value", value=str(new_value)[:100], inline=True)
            
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

class PaginatedTaskView(discord.ui.View):
    def __init__(self, tasks, tasks_per_page=5):
        super().__init__(timeout=300)  # 5 minute timeout
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

class PaginatedCompletedTaskView(discord.ui.View):
    def __init__(self, tasks, user_name, total_completed, late_completed, tasks_per_page=5):
        super().__init__(timeout=300)  # 5 minute timeout
        self.tasks = tasks
        self.user_name = user_name
        self.total_completed = total_completed
        self.late_completed = late_completed
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
                title=f"📋 Completed Tasks - {self.user_name}",
                description="No completed tasks found for this user.",
                color=discord.Color.green()
            )
            # Still show the stats even if no tasks
            embed.add_field(
                name="📊 Statistics",
                value=f"**Total Completed:** {self.total_completed}\n**Completed Late:** {self.late_completed}",
                inline=False
            )
        else:
            embed = discord.Embed(
                title=f"📋 Completed Tasks - {self.user_name}",
                description=f"**Page {self.current_page + 1} of {self.total_pages}** • Showing {len(current_tasks)} of {len(self.tasks)} tasks",
                color=discord.Color.green()
            )
            
            # Add statistics at the top
            embed.add_field(
                name="📊 Statistics",
                value=f"**Total Completed:** {self.total_completed}\n**Completed Late:** {self.late_completed}",
                inline=False
            )
            
            for i, task in enumerate(current_tasks):
                task_number = start_idx + i + 1
                # Use the pre-fetched user names we stored in the task objects
                creator_name = getattr(task, '_creator_name', 'Unknown')
                
                # Format dates
                due_date = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
                completed_date = task.completed_at.strftime('%Y-%m-%d %H:%M UTC') if task.completed_at else 'Unknown'
                
                # Check if completed late
                late_indicator = ""
                if task.completed_at and task.completed_at > task.due_date:
                    late_indicator = " ⚠️ (Late)"
                
                value = (
                    f"**Created by:** {creator_name}\n"
                    f"**Due:** {due_date}\n"
                    f"**Completed:** {completed_date}{late_indicator}\n"
                    f"**Description:** {task.description}"
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

def setup_task_commands(tree: app_commands.CommandTree):
    """Setup task management commands"""
    
    @tree.command(
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
        """Manage task creator whitelist"""
        if action.lower() not in ['add', 'remove']:
            await interaction.response.send_message(
                "❌ Invalid action! Use 'add' or 'remove'.",
                ephemeral=True
            )
            return
        
        session = get_session(str(interaction.guild_id))
        try:
            existing_creator = session.query(TaskCreator).filter_by(
                user_id=str(user.id),
                server_id=str(interaction.guild_id)
            ).first()
            
            if action.lower() == 'add':
                if existing_creator:
                    await interaction.response.send_message(
                        f"❌ {user.display_name} is already in the task creator whitelist!",
                        ephemeral=True
                    )
                    return
                
                new_creator = TaskCreator(
                    user_id=str(user.id),
                    server_id=str(interaction.guild_id),
                    added_by=str(interaction.user.id)
                )
                session.add(new_creator)
                session.commit()
                
                await interaction.response.send_message(
                    f"✅ Added {user.display_name} to the task creator whitelist!\n"
                    f"They can now use `/task` to create tasks.",
                    ephemeral=True
                )
                
            else:  # remove
                if not existing_creator:
                    await interaction.response.send_message(
                        f"❌ {user.display_name} is not in the task creator whitelist!",
                        ephemeral=True
                    )
                    return
                
                session.delete(existing_creator)
                session.commit()
                
                await interaction.response.send_message(
                    f"✅ Removed {user.display_name} from the task creator whitelist!\n"
                    f"They can no longer use `/task` (unless they're an admin).",
                    ephemeral=True
                )
                
        except Exception as e:
            print(f"Error in tcw command: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                f"An error occurred while updating the whitelist: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
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
                "❌ You don't have permission to create tasks!\n\n"
                "Only administrators or whitelisted users can use this command.\n"
                "Ask an admin to add you with `/tcw add @user`",
                ephemeral=True
            )
            return
        
        try:
            # Parse the due date
            parsed_date = parser.parse(due_date)
            
            # Create the task
            session = get_session(str(interaction.guild_id))
            try:
                new_task = Task(
                    name=name,
                    description=description,
                    assigned_to=str(assigned_to.id),
                    due_date=parsed_date,
                    server_id=str(interaction.guild_id),
                    created_by=str(interaction.user.id)
                )
                session.add(new_task)
                session.commit()
                
                embed = discord.Embed(
                    title="✅ Task Created Successfully!",
                    color=discord.Color.green()
                )
                embed.add_field(name="Task Name", value=name, inline=False)
                embed.add_field(name="Assigned To", value=assigned_to.mention, inline=True)
                embed.add_field(name="Due Date", value=parsed_date.strftime('%Y-%m-%d %H:%M UTC'), inline=True)
                embed.add_field(name="Description", value=description, inline=False)
                embed.set_footer(text=f"Created by {interaction.user.display_name}")
                
                await interaction.response.send_message(embed=embed)
                
                # Send DM to assigned user
                try:
                    dm_embed = discord.Embed(
                        title="📋 New Task Assigned",
                        description=f"You have been assigned a new task in **{interaction.guild.name}**",
                        color=discord.Color.blue()
                    )
                    dm_embed.add_field(name="Task", value=name, inline=False)
                    dm_embed.add_field(name="Due Date", value=parsed_date.strftime('%Y-%m-%d %H:%M UTC'), inline=True)
                    dm_embed.add_field(name="Assigned By", value=interaction.user.display_name, inline=True)
                    dm_embed.add_field(name="Description", value=description, inline=False)
                    dm_embed.set_footer(text="Use /mytasks to view all your tasks")
                    
                    await assigned_to.send(embed=dm_embed)
                except discord.Forbidden:
                    # User has DMs disabled
                    pass
                
            finally:
                session.close()
                
        except ValueError as e:
            await interaction.response.send_message(
                f"❌ Invalid date format! Please use YYYY-MM-DD HH:MM format (24-hour).\n"
                f"Example: 2024-01-15 14:30\n\n"
                f"Error details: {str(e)}",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error creating task: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                f"An error occurred while creating the task: {str(e)}",
                ephemeral=True
            )

    @tree.command(
        name="mytasks",
        description="View your tasks"
    )
    @log_command
    async def mytasks(interaction: discord.Interaction):
        session = get_session(str(interaction.guild_id))
        try:
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
            
            if len(tasks) == 1:
                # Single task - show detailed view
                task = tasks[0]
                embed = discord.Embed(
                    title="📋 Your Task",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Task Name", value=task.name, inline=False)
                embed.add_field(name="Due Date", value=task.due_date.strftime('%Y-%m-%d %H:%M UTC'), inline=True)
                embed.add_field(name="Description", value=task.description, inline=False)
                
                # Calculate time remaining
                time_diff = task.due_date - datetime.utcnow()
                if time_diff.total_seconds() > 0:
                    days = time_diff.days
                    hours, remainder = divmod(time_diff.seconds, 3600)
                    embed.add_field(name="Time Remaining", value=f"{days}d {hours}h", inline=True)
                else:
                    embed.add_field(name="Status", value="⚠️ OVERDUE", inline=True)
                
                view = TaskView(tasks, interaction.user)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                # Multiple tasks - show list view
                view = TaskView(tasks, interaction.user)
                embed = discord.Embed(
                    title=f"📋 Your Tasks ({len(tasks)})",
                    description="Select a task below to view details and mark as complete:",
                    color=discord.Color.blue()
                )
                
                for i, task in enumerate(tasks[:5]):  # Show first 5 tasks in embed
                    due_date = task.due_date.strftime('%Y-%m-%d %H:%M')
                    embed.add_field(
                        name=f"{i+1}. {task.name}",
                        value=f"Due: {due_date}\n{task.description[:50]}{'...' if len(task.description) > 50 else ''}",
                        inline=False
                    )
                
                if len(tasks) > 5:
                    embed.set_footer(text=f"Showing first 5 tasks. Use the dropdown to see all {len(tasks)} tasks.")
                
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                
        except Exception as e:
            print(f"Error in mytasks command: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                f"An error occurred while fetching your tasks: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
        name="taskedit",
        description="Edit an existing task"
    )
    @log_command
    async def taskedit(interaction: discord.Interaction):
        session = get_session(str(interaction.guild_id))
        try:
            # Get tasks created by this user or assigned to them (if they're admin)
            if interaction.user.guild_permissions.administrator:
                # Admins can edit any task in the server
                tasks = session.query(Task).filter_by(
                    server_id=str(interaction.guild_id),
                    completed=False
                ).order_by(Task.due_date).all()
            else:
                # Regular users can only edit tasks they created
                tasks = session.query(Task).filter_by(
                    created_by=str(interaction.user.id),
                    server_id=str(interaction.guild_id),
                    completed=False
                ).order_by(Task.due_date).all()
            
            if not tasks:
                message = "You have no tasks to edit!" if not interaction.user.guild_permissions.administrator else "No active tasks found in this server!"
                await interaction.response.send_message(message, ephemeral=True)
                return
            
            view = TaskEditView(tasks, interaction.user)
            embed = discord.Embed(
                title="✏️ Edit Tasks",
                description=f"Select a task to edit from the dropdown below.\nYou can edit {len(tasks)} task(s).",
                color=discord.Color.orange()
            )
            
            permission_text = "Administrator permissions detected - you can edit any task in this server." if interaction.user.guild_permissions.administrator else "You can edit tasks you created."
            embed.set_footer(text=permission_text)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            print(f"Error in taskedit command: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                f"An error occurred while fetching tasks: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
        name="showtasks",
        description="View tasks assigned to a specific user"
    )
    @app_commands.describe(
        target_user="The user whose tasks you want to view (mention the user)"
    )
    @log_command
    async def showtasks(interaction: discord.Interaction, target_user: discord.Member):
        session = get_session(str(interaction.guild_id))
        try:
            tasks = session.query(Task).filter_by(
                assigned_to=str(target_user.id),
                server_id=str(interaction.guild_id),
                completed=False
            ).order_by(Task.due_date).all()
            
            if not tasks:
                await interaction.response.send_message(
                    f"{target_user.display_name} has no pending tasks!",
                    ephemeral=True
                )
                return
            
            # Collect all unique creator IDs for tasks we'll display
            display_tasks = tasks[:10]  # Limit to 10 tasks to avoid embed limits
            creator_ids = set()
            for task in display_tasks:
                if task.created_by != "0":
                    creator_ids.add(task.created_by)
            
            # Fetch all creators in parallel for better performance
            user_cache = {}
            if creator_ids:
                async def fetch_user_safe(user_id):
                    try:
                        user = await _client.fetch_user(int(user_id))
                        return user_id, user.display_name if user else "Unknown"
                    except:
                        return user_id, "Unknown"
                
                # Fetch all users concurrently
                user_results = await asyncio.gather(*[fetch_user_safe(uid) for uid in creator_ids], return_exceptions=True)
                
                # Build user cache from results
                for result in user_results:
                    if isinstance(result, tuple):
                        user_id, display_name = result
                        user_cache[user_id] = display_name
            
            embed = discord.Embed(
                title=f"📋 Tasks for {target_user.display_name}",
                description=f"Total pending tasks: {len(tasks)}",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=target_user.display_avatar.url)
            
            for i, task in enumerate(display_tasks):
                due_date = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
                
                # Calculate time remaining
                time_diff = task.due_date - datetime.utcnow()
                if time_diff.total_seconds() > 0:
                    days = time_diff.days
                    hours, remainder = divmod(time_diff.seconds, 3600)
                    time_status = f"⏰ {days}d {hours}h remaining"
                else:
                    time_status = "⚠️ OVERDUE"
                
                # Get creator name from cache
                creator_name = user_cache.get(task.created_by, "Unknown") if task.created_by != "0" else "Unknown"
                
                value = (
                    f"**Due:** {due_date}\n"
                    f"**Status:** {time_status}\n"
                    f"**Created by:** {creator_name}\n"
                    f"**Description:** {task.description[:100]}{'...' if len(task.description) > 100 else ''}"
                )
                embed.add_field(name=f"{i+1}. {task.name}", value=value, inline=False)
            
            if len(tasks) > 10:
                embed.set_footer(text=f"Showing first 10 tasks out of {len(tasks)} total tasks.")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in showtasks command: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                f"An error occurred while fetching tasks: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
        name="alltasks",
        description="View all active tasks in the server (Admin only)"
    )
    @checks.has_permissions(administrator=True)
    @log_command
    async def alltasks(interaction: discord.Interaction):
        session = get_session(str(interaction.guild_id))
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
            
            # Collect all unique user IDs from tasks
            user_ids = set()
            for task in tasks:
                user_ids.add(task.assigned_to)
                if task.created_by != "0":
                    user_ids.add(task.created_by)
            
            # Fetch all users in parallel for much better performance
            user_cache = {}
            if user_ids:
                async def fetch_user_safe(user_id):
                    try:
                        user = await _client.fetch_user(int(user_id))
                        return user_id, user.display_name if user else "Unknown"
                    except:
                        return user_id, "Unknown"
                
                # Fetch all users concurrently
                user_results = await asyncio.gather(*[fetch_user_safe(uid) for uid in user_ids], return_exceptions=True)
                
                # Build user cache from results
                for result in user_results:
                    if isinstance(result, tuple):
                        user_id, display_name = result
                        user_cache[user_id] = display_name
                    else:
                        # Handle exceptions by marking as Unknown
                        continue
            
            # Assign names to tasks using the cache
            for task in tasks:
                task._assigned_name = user_cache.get(task.assigned_to, "Unknown")
                task._creator_name = user_cache.get(task.created_by, "Unknown") if task.created_by != "0" else "Unknown"
            
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

    @tree.command(
        name="oldtasks",
        description="View completed tasks for a specific user"
    )
    @app_commands.describe(
        user="The user whose completed tasks you want to view (mention the user)"
    )
    @log_command
    async def oldtasks(interaction: discord.Interaction, user: discord.Member):
        session = get_session(str(interaction.guild_id))
        try:
            # Query completed tasks for the specified user
            completed_tasks = session.query(Task).filter_by(
                assigned_to=str(user.id),
                server_id=str(interaction.guild_id),
                completed=True
            ).order_by(Task.completed_at.desc()).all()  # Most recent first
            
            # Calculate statistics
            total_completed = len(completed_tasks)
            late_completed = 0
            
            for task in completed_tasks:
                if task.completed_at and task.completed_at > task.due_date:
                    late_completed += 1
            
            if total_completed == 0:
                embed = discord.Embed(
                    title=f"📋 Completed Tasks - {user.display_name}",
                    description="This user has no completed tasks!",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="📊 Statistics",
                    value=f"**Total Completed:** 0\n**Completed Late:** 0",
                    inline=False
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Defer the response since we might need time to fetch user data
            await interaction.response.defer()
            
            # Collect all unique creator IDs from completed tasks
            creator_ids = set()
            for task in completed_tasks:
                if task.created_by != "0":
                    creator_ids.add(task.created_by)
            
            # Fetch all creators in parallel for better performance
            user_cache = {}
            if creator_ids:
                async def fetch_user_safe(user_id):
                    try:
                        user = await _client.fetch_user(int(user_id))
                        return user_id, user.display_name if user else "Unknown"
                    except:
                        return user_id, "Unknown"
                
                # Fetch all users concurrently
                user_results = await asyncio.gather(*[fetch_user_safe(uid) for uid in creator_ids], return_exceptions=True)
                
                # Build user cache from results
                for result in user_results:
                    if isinstance(result, tuple):
                        user_id, display_name = result
                        user_cache[user_id] = display_name
            
            # Assign creator names to tasks using the cache
            for task in completed_tasks:
                task._creator_name = user_cache.get(task.created_by, "Unknown") if task.created_by != "0" else "Unknown"
            
            # Create paginated view with statistics
            view = PaginatedCompletedTaskView(
                tasks=completed_tasks,
                user_name=user.display_name,
                total_completed=total_completed,
                late_completed=late_completed,
                tasks_per_page=5
            )
            embed = view.get_current_page_embed()
            
            await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            print(f"Error in oldtasks command: {str(e)}")
            print(traceback.format_exc())
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"An error occurred while fetching completed tasks: {str(e)}",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"An error occurred while fetching completed tasks: {str(e)}",
                    ephemeral=True
                )
        finally:
            session.close()

# Export the setup function
__all__ = ['setup_task_system', 'setup_task_commands'] 