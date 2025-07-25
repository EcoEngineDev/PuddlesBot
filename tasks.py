import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta, timezone
from dateutil import parser
import pytz
from database import Task, TaskCreator, get_session, TimezoneSettings, SnipeRequest, SnipeSettings
import asyncio
from typing import Optional, Callable, Any
import traceback
from discord.app_commands import checks
import functools
import re

# Store reference to the client
_client = None

def setup_task_system(client):
    """Initialize the task system with client reference"""
    global _client
    _client = client

def ensure_utc(dt):
    """Ensure datetime is in UTC timezone"""
    if dt.tzinfo is None:
        # Assume naive datetime is UTC
        return dt.replace(tzinfo=timezone.utc)
    else:
        # Convert to UTC if timezone-aware
        return dt.astimezone(timezone.utc).replace(tzinfo=None)

def get_current_utc():
    """Get current UTC time consistently"""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def get_server_timezone(server_id: str) -> str:
    """Get the timezone setting for a server"""
    session = get_session(server_id)
    try:
        tz_setting = session.query(TimezoneSettings).filter_by(server_id=server_id).first()
        if tz_setting:
            return tz_setting.timezone
        return 'UTC'  # Default to UTC
    finally:
        session.close()

def set_server_timezone(server_id: str, timezone_name: str):
    """Set the timezone for a server"""
    session = get_session(server_id)
    try:
        tz_setting = session.query(TimezoneSettings).filter_by(server_id=server_id).first()
        if tz_setting:
            tz_setting.timezone = timezone_name
            tz_setting.updated_at = get_current_utc()
        else:
            tz_setting = TimezoneSettings(
                server_id=server_id,
                timezone=timezone_name
            )
            session.add(tz_setting)
        session.commit()
    finally:
        session.close()

def convert_to_server_timezone(utc_dt: datetime, server_id: str) -> datetime:
    """Convert UTC datetime to server's timezone"""
    server_tz_name = get_server_timezone(server_id)
    try:
        server_tz = pytz.timezone(server_tz_name)
        utc_tz = pytz.UTC
        # Make UTC datetime timezone-aware
        utc_aware = utc_tz.localize(utc_dt)
        # Convert to server timezone
        server_aware = utc_aware.astimezone(server_tz)
        return server_aware
    except:
        # Fallback to UTC if timezone conversion fails
        return pytz.UTC.localize(utc_dt)

def convert_from_server_timezone(server_dt: datetime, server_id: str) -> datetime:
    """Convert server timezone datetime to UTC"""
    server_tz_name = get_server_timezone(server_id)
    try:
        server_tz = pytz.timezone(server_tz_name)
        # If datetime is naive, assume it's in server timezone
        if server_dt.tzinfo is None:
            server_aware = server_tz.localize(server_dt)
        else:
            server_aware = server_dt
        # Convert to UTC and return naive datetime
        utc_aware = server_aware.astimezone(pytz.UTC)
        return utc_aware.replace(tzinfo=None)
    except:
        # Fallback: assume it's already UTC
        return ensure_utc(server_dt)

def get_all_timezones():
    """Get all available timezones grouped by region"""
    timezones = {}
    for tz in pytz.all_timezones:
        if '/' in tz:
            region, city = tz.split('/', 1)
            if region not in timezones:
                timezones[region] = []
            timezones[region].append(tz)
        else:
            if 'Other' not in timezones:
                timezones['Other'] = []
            timezones['Other'].append(tz)
    
    # Sort each region's timezones
    for region in timezones:
        timezones[region].sort()
    
    return timezones

def format_task_date(utc_date: datetime, server_id: str, include_timezone: bool = True) -> str:
    """Format a task date in the server's timezone"""
    try:
        # Convert UTC date to server timezone
        server_tz_date = convert_to_server_timezone(utc_date, server_id)
        server_tz_name = get_server_timezone(server_id)
        
        if include_timezone:
            return f"{server_tz_date.strftime('%Y-%m-%d %H:%M')} {server_tz_date.strftime('%Z')} ({server_tz_name})"
        else:
            return server_tz_date.strftime('%Y-%m-%d %H:%M')
    except:
        # Fallback to UTC if conversion fails
        return f"{utc_date.strftime('%Y-%m-%d %H:%M')} UTC"

async def get_user_mention(bot, user_id: str, guild_id: str = None) -> str:
    """Get a user mention with display name, fallback to username"""
    try:
        user = bot.get_user(int(user_id))
        if not user:
            user = await bot.fetch_user(int(user_id))
        
        if guild_id and user:
            guild = bot.get_guild(int(guild_id))
            if guild:
                member = guild.get_member(int(user_id))
                if member:
                    return f"<@{user_id}>"
        
        return f"<@{user_id}>" if user else "Unknown User"
    except:
        return "Unknown User"

async def get_multiple_user_mentions(bot, assigned_to: str, guild_id: str = None) -> str:
    """Get mentions for multiple users from comma-separated user IDs"""
    if not assigned_to:
        return "No assignees"
    
    user_ids = assigned_to.split(',')
    mentions = []
    
    # Use asyncio.gather for concurrent user fetching
    async def get_mention_safe(user_id):
        try:
            return await get_user_mention(bot, user_id.strip(), guild_id)
        except:
            return "Unknown User"
    
    mention_results = await asyncio.gather(*[get_mention_safe(uid) for uid in user_ids], return_exceptions=True)
    
    for result in mention_results:
        if isinstance(result, str):
            mentions.append(result)
        else:
            mentions.append("Unknown User")
    
    return ', '.join(mentions)

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
        server_id = str(user.guild.id) if hasattr(user, 'guild') and user.guild else None
        self.add_item(TaskSelect(tasks, server_id))

class TaskSelect(discord.ui.Select):
    def __init__(self, tasks, server_id: str = None):
        self.task_list = tasks
        self.server_id = server_id
        
        options = []
        for task in tasks:
            if server_id:
                due_date_str = format_task_date(task.due_date, server_id, False)
            else:
                due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
            
            options.append(discord.SelectOption(
                label=task.name[:100],  # Discord has a 100 char limit on labels
                value=str(task.id),
                description=f"Due: {due_date_str}"[:100]
            ))
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
            
            # Show all assignees for this task
            try:
                all_assignees = await get_multiple_user_mentions(interaction.client, task.assigned_to, str(interaction.guild_id))
                embed.add_field(name="👥 Assigned To", value=all_assignees, inline=False)
            except:
                # Fallback if mention fetching fails
                assigned_ids = task.assigned_to.split(',') if task.assigned_to else []
                assignee_mentions = ', '.join([f"<@{uid.strip()}>" for uid in assigned_ids])
                embed.add_field(name="👥 Assigned To", value=assignee_mentions, inline=False)
            
            embed.add_field(
                name="Due Date",
                value=format_task_date(task.due_date, str(interaction.guild_id)),
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

        # Check if the user is one of the assigned users
        assigned_user_ids = view.selected_task.assigned_to.split(',') if view.selected_task.assigned_to else []
        user_is_assigned = str(interaction.user.id) in assigned_user_ids
        
        if not user_is_assigned:
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
                task.completed_at = get_current_utc()
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
    def __init__(self, tasks, server_id: str = None):
        self.task_list = tasks
        self.server_id = server_id
        
        options = []
        for task in tasks:
            if server_id:
                due_date_str = format_task_date(task.due_date, server_id, False)
            else:
                due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
            
            options.append(discord.SelectOption(
                label=task.name[:100],  # Discord has a 100 char limit on labels
                value=str(task.id),
                description=f"Due: {due_date_str}"[:100]
            ))
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
        server_id = str(user.guild.id) if hasattr(user, 'guild') and user.guild else None
        self.add_item(TaskEditSelect(tasks, server_id))

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

    @discord.ui.button(label="🗑️ Delete Task", custom_id="delete_task_btn", style=discord.ButtonStyle.danger, disabled=True, row=3)
    async def delete_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.selected_task:
            # Show confirmation modal
            view = TaskDeleteConfirmView(self.selected_task)
            embed = discord.Embed(
                title="⚠️ Confirm Task Deletion",
                description=f"Are you sure you want to delete the task **{self.selected_task.name}**?\n\n"
                           f"**This action cannot be undone!**",
                color=discord.Color.red()
            )
            # Show multiple assignees
            if self.selected_task.assigned_to:
                assigned_ids = self.selected_task.assigned_to.split(',')
                assigned_mentions = ', '.join([f"<@{uid.strip()}>" for uid in assigned_ids])
            else:
                assigned_mentions = "Unknown"
                
            embed.add_field(name="Task Details", 
                          value=f"**Assigned to:** {assigned_mentions}\n"
                                f"**Due:** {self.selected_task.due_date.strftime('%Y-%m-%d %H:%M UTC')}\n"
                                f"**Description:** {self.selected_task.description}", 
                          inline=False)
            await interaction.response.edit_message(embed=embed, view=view)

class TaskDeleteConfirmView(discord.ui.View):
    def __init__(self, task: Task):
        super().__init__(timeout=60)  # 1 minute timeout for safety
        self.task = task

    @discord.ui.button(label="✅ Confirm Delete", style=discord.ButtonStyle.danger)
    async def confirm_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = get_session(str(interaction.guild_id))
        try:
            # Get the task from database to ensure it still exists
            task = session.query(Task).get(self.task.id)
            if not task:
                await interaction.response.send_message("Task not found! It may have already been deleted.", ephemeral=True)
                return

            # Delete the task
            session.delete(task)
            session.commit()
            
            embed = discord.Embed(
                title="🗑️ Task Deleted",
                description=f"Task **{self.task.name}** has been permanently deleted.",
                color=discord.Color.red()
            )
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.response.edit_message(embed=embed, view=self)
            
        except Exception as e:
            print(f"Error deleting task: {str(e)}")
            await interaction.response.send_message(
                f"An error occurred while deleting the task: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Go back to the task edit view
        view = TaskEditView([self.task], interaction.user)
        view.selected_task = self.task
        
        # Enable all edit buttons since a task is selected
        for item in view.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = False
        
        embed = discord.Embed(
            title=f"Editing Task: {self.task.name}",
            description=f"**Current Description:** {self.task.description}\n**Due Date:** {self.task.due_date.strftime('%Y-%m-%d %H:%M UTC')}",
            color=discord.Color.orange()
        )
        
        await interaction.response.edit_message(embed=embed, view=view)

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
            super().__init__(title="Change Task Assignees")
            self.text_input = discord.ui.TextInput(
                label="New Assignees (User IDs or mentions)",
                placeholder="Enter user IDs or mentions: @user1 @user2 123456789",
                default=task.assigned_to,
                max_length=200
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
                    # Ensure the date is in UTC
                    new_due_date = ensure_utc(new_due_date)
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
                    # Parse user mentions and IDs from the input
                    import re
                    input_text = new_value.strip()
                    
                    # Extract user mentions
                    user_mentions = re.findall(r'<@!?(\d+)>', input_text)
                    
                    # Extract plain user IDs (sequences of digits)
                    remaining_text = re.sub(r'<@!?(\d+)>', '', input_text)
                    user_ids_plain = re.findall(r'\b(\d{15,20})\b', remaining_text)
                    
                    # Combine all user IDs
                    all_user_ids = user_mentions + user_ids_plain
                    
                    if not all_user_ids:
                        await interaction.response.send_message(
                            "Invalid format! Please provide user mentions (@user) or user IDs (123456789).",
                            ephemeral=True
                        )
                        return
                    
                    # Validate that all user IDs exist
                    validated_ids = []
                    for user_id in all_user_ids:
                        try:
                            user = await _client.fetch_user(int(user_id))
                            if user:
                                validated_ids.append(user_id)
                        except (ValueError, discord.NotFound):
                            await interaction.response.send_message(
                                f"Invalid user ID: {user_id}! Please check that all users exist.",
                                ephemeral=True
                            )
                            return
                    
                    # Store as comma-separated string
                    task.assigned_to = ','.join(validated_ids)
                    
                except Exception as e:
                    await interaction.response.send_message(
                        f"Error processing assignees: {str(e)}",
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
    def __init__(self, tasks, tasks_per_page=5, server_id: str = None, bot = None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.tasks = tasks
        self.tasks_per_page = tasks_per_page
        self.current_page = 0
        self.total_pages = max(1, (len(tasks) + tasks_per_page - 1) // tasks_per_page)
        self.server_id = server_id
        self.bot = bot
        
        # Update button states
        self.update_buttons()
    
    def update_buttons(self):
        # Update Previous button
        self.previous_button.disabled = (self.current_page == 0)
        
        # Update Next button  
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
    
    async def get_current_page_embed(self):
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
                
                # Format date in server timezone
                if self.server_id:
                    due_date = format_task_date(task.due_date, self.server_id, False)
                else:
                    due_date = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
                
                # Get user mentions if bot is available
                if self.bot and self.server_id:
                    assigned_mention = await get_multiple_user_mentions(self.bot, task.assigned_to, self.server_id)
                    creator_mention = await get_user_mention(self.bot, task.created_by, self.server_id)
                else:
                    assigned_mention = assigned_name
                    creator_mention = creator_name
                
                value = (
                    f"Assigned to: {assigned_mention}\n"
                    f"Created by: {creator_mention}\n"
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
            embed = await self.get_current_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed = await self.get_current_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Refresh the current page
        embed = await self.get_current_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class PaginatedCompletedTaskView(discord.ui.View):
    def __init__(self, tasks, user_name, total_completed, late_completed, tasks_per_page=5, server_id: str = None, bot = None):
        super().__init__(timeout=300)  # 5 minute timeout
        self.tasks = tasks
        self.user_name = user_name
        self.total_completed = total_completed
        self.late_completed = late_completed
        self.tasks_per_page = tasks_per_page
        self.current_page = 0
        self.total_pages = max(1, (len(tasks) + tasks_per_page - 1) // tasks_per_page)
        self.server_id = server_id
        self.bot = bot
        
        # Update button states
        self.update_buttons()
    
    def update_buttons(self):
        # Update Previous button
        self.previous_button.disabled = (self.current_page == 0)
        
        # Update Next button  
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
    
    async def get_current_page_embed(self):
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
                
                # Format dates in server timezone
                if self.server_id:
                    due_date = format_task_date(task.due_date, self.server_id, False)
                    completed_date = format_task_date(task.completed_at, self.server_id, False) if task.completed_at else 'Unknown'
                else:
                    due_date = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
                    completed_date = task.completed_at.strftime('%Y-%m-%d %H:%M UTC') if task.completed_at else 'Unknown'
                
                # Check if completed late
                late_indicator = ""
                if task.completed_at and task.completed_at > task.due_date:
                    late_indicator = " ⚠️ (Late)"
                
                # Check if task was sniped
                snipe_indicator = ""
                if getattr(task, 'is_sniped', False):
                    if self.bot and self.server_id:
                        sniped_from_mention = await get_user_mention(self.bot, task.sniped_from, self.server_id) if task.sniped_from else "Unknown"
                    else:
                        sniped_from_mention = f"<@{task.sniped_from}>" if task.sniped_from else "Unknown"
                    snipe_indicator = f" 🎯 (Sniped from {sniped_from_mention})"
                
                # Get user mention if bot is available
                if self.bot and self.server_id:
                    creator_mention = await get_user_mention(self.bot, task.created_by, self.server_id)
                    # Get all assignees for this completed task
                    try:
                        all_assignees = await get_multiple_user_mentions(self.bot, task.assigned_to, self.server_id)
                    except:
                        # Fallback if mention fetching fails
                        assigned_ids = task.assigned_to.split(',') if task.assigned_to else []
                        all_assignees = ', '.join([f"<@{uid.strip()}>" for uid in assigned_ids])
                else:
                    creator_mention = creator_name
                    # Fallback display for assignees
                    assigned_ids = task.assigned_to.split(',') if task.assigned_to else []
                    all_assignees = ', '.join([f"<@{uid.strip()}>" for uid in assigned_ids])
                
                value = (
                    f"**👥 Assigned to:** {all_assignees}\n"
                    f"**Created by:** {creator_mention}\n"
                    f"**Due:** {due_date}\n"
                    f"**Completed:** {completed_date}{late_indicator}{snipe_indicator}\n"
                    f"**Description:** {task.description}"
                )
                embed.add_field(name=f"{task_number}. {task.name}", value=value, inline=False)
        
        return embed
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = await self.get_current_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed = await self.get_current_page_embed()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="🔄 Refresh", style=discord.ButtonStyle.primary)
    async def refresh_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Refresh the current page
        embed = await self.get_current_page_embed()
        await interaction.response.edit_message(embed=embed, view=self)

class TaskCreationModal(discord.ui.Modal):
    def __init__(self, assigned_users: list, server_id: str = None):
        super().__init__(title="Create New Task")
        
        self.assigned_users = assigned_users
        self.server_id = server_id
        
        self.name = discord.ui.TextInput(
            label="Task Name",
            placeholder="Enter a name for the task...",
            required=True,
            max_length=256
        )
        self.add_item(self.name)
        
        self.description = discord.ui.TextInput(
            label="Task Description",
            placeholder="Enter a detailed description of the task...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        self.add_item(self.description)
        
        # Get server timezone for the placeholder
        if server_id:
            server_tz = get_server_timezone(server_id)
            try:
                tz_obj = pytz.timezone(server_tz)
                current_time = datetime.now(tz_obj)
                example_time = current_time.strftime('%Y-%m-%d %H:%M')
                # Truncate timezone name to fit Discord's 45-character limit
                max_tz_length = 45 - len("Due Date (YYYY-MM-DD HH:MM) - ")  # 15 characters left
                truncated_tz = server_tz[:max_tz_length] if len(server_tz) > max_tz_length else server_tz
                timezone_label = f"Due Date (YYYY-MM-DD HH:MM) - {truncated_tz}"
                placeholder_text = f"Example: {example_time}"
            except:
                timezone_label = "Due Date (YYYY-MM-DD HH:MM) - UTC"
                placeholder_text = "Example: 2024-12-31 23:59"
        else:
            timezone_label = "Due Date (YYYY-MM-DD HH:MM) - UTC"
            placeholder_text = "Example: 2024-12-31 23:59"
        
        self.due_date = discord.ui.TextInput(
            label=timezone_label,
            placeholder=placeholder_text,
            required=True,
            max_length=16
        )
        self.add_item(self.due_date)
        
        self.send_dm = discord.ui.TextInput(
            label="Send DM to assignees? (yes/no)",
            placeholder="Type 'yes' or 'no'",
            required=True,
            max_length=3,
            default="yes"
        )
        self.add_item(self.send_dm)
    
    async def on_submit(self, interaction: discord.Interaction):
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
            # Parse the due date with timezone handling
            parsed_date = parser.parse(self.due_date.value)
            # Convert from server timezone to UTC for storage
            server_id = str(interaction.guild_id)
            parsed_date = convert_from_server_timezone(parsed_date, server_id)
            
            # Parse send_dm value
            send_dm = self.send_dm.value.lower() in ('yes', 'y', 'true', '1')
            
            # Create comma-separated list of user IDs for storage
            assigned_to_ids = ','.join([str(user.id) for user in self.assigned_users])
            
            # Create the task
            session = get_session(str(interaction.guild_id))
            try:
                new_task = Task(
                    name=self.name.value,
                    description=self.description.value,
                    assigned_to=assigned_to_ids,
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
                embed.add_field(name="Task Name", value=self.name.value, inline=False)
                
                # Show all assigned users
                assigned_mentions = ', '.join([user.mention for user in self.assigned_users])
                embed.add_field(name="Assigned To", value=assigned_mentions, inline=True)
                
                # Display date in server timezone
                server_tz_date = convert_to_server_timezone(parsed_date, server_id)
                server_tz_name = get_server_timezone(server_id)
                embed.add_field(name="Due Date", value=f"{server_tz_date.strftime('%Y-%m-%d %H:%M %Z')} ({server_tz_name})", inline=True)
                embed.add_field(name="Description", value=self.description.value, inline=False)
                embed.set_footer(text=f"Created by {interaction.user.display_name}")
                
                await interaction.response.send_message(embed=embed)
                
                # Send DM to all assigned users if requested
                if send_dm:
                    for assigned_user in self.assigned_users:
                        try:
                            dm_embed = discord.Embed(
                                title="📋 New Task Assigned",
                                description=f"You have been assigned a new task in **{interaction.guild.name}**",
                                color=discord.Color.blue()
                            )
                            dm_embed.add_field(name="Task", value=self.name.value, inline=False)
                            dm_embed.add_field(name="Due Date", value=parsed_date.strftime('%Y-%m-%d %H:%M UTC'), inline=True)
                            dm_embed.add_field(name="Assigned By", value=interaction.user.display_name, inline=True)
                            dm_embed.add_field(name="Description", value=self.description.value, inline=False)
                            dm_embed.add_field(name="Also Assigned To", value=assigned_mentions, inline=False)
                            dm_embed.set_footer(text="Use /mytasks to view all your tasks")
                            await assigned_user.send(embed=dm_embed)
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

class SnipeTaskView(discord.ui.View):
    def __init__(self, tasks, user):
        super().__init__(timeout=180)  # 3 minute timeout
        self.tasks = tasks
        self.user = user
        self.selected_task = None
        
        # Add task selection dropdown
        server_id = str(user.guild.id) if hasattr(user, 'guild') and user.guild else None
        self.add_item(SnipeTaskSelect(tasks, server_id))

class SnipeTaskSelect(discord.ui.Select):
    def __init__(self, tasks, server_id: str = None):
        self.task_list = tasks
        self.server_id = server_id
        
        options = []
        for task in tasks:
            if server_id:
                due_date_str = format_task_date(task.due_date, server_id, False)
            else:
                due_date_str = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
            
            options.append(discord.SelectOption(
                label=task.name[:100],  # Discord has a 100 char limit on labels
                value=str(task.id),
                description=f"Due: {due_date_str} | Assigned to: {getattr(task, '_assigned_name', 'Unknown')}"[:100]
            ))
        super().__init__(
            placeholder="Choose a task to snipe...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        view: SnipeTaskView = self.view
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
        
        # Show task details and confirmation
        # Get multiple user mentions for assigned users
        if interaction.client and interaction.guild_id:
            assigned_mentions = await get_multiple_user_mentions(interaction.client, selected_task.assigned_to, str(interaction.guild_id))
        else:
            # Fallback - just show user IDs as mentions
            user_ids = selected_task.assigned_to.split(',') if selected_task.assigned_to else []
            assigned_mentions = ', '.join([f"<@{uid.strip()}>" for uid in user_ids])
        
        embed = discord.Embed(
            title=f"🎯 Snipe Task: {selected_task.name}",
            description=f"**Description:** {selected_task.description}\n"
                       f"**Currently assigned to:** {assigned_mentions}\n"
                       f"**Due:** {format_task_date(selected_task.due_date, str(interaction.guild_id))}\n\n"
                       f"Are you sure you want to claim credit for this task? This will require admin approval.",
            color=discord.Color.orange()
        )
        
        # Add snipe confirm button
        view.clear_items()
        view.add_item(SnipeConfirmButton())
        view.add_item(SnipeCancelButton(self.task_list, self.server_id))
        
        await interaction.response.edit_message(embed=embed, view=view)

class SnipeConfirmButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="🎯 Confirm Snipe",
            emoji="🎯"
        )

    async def callback(self, interaction: discord.Interaction):
        view: SnipeTaskView = self.view
        if not view.selected_task:
            await interaction.response.send_message("Please select a task first!", ephemeral=True)
            return

        session = get_session(str(interaction.guild_id))
        try:
            # Check if there's already a pending snipe request for this task
            existing_request = session.query(SnipeRequest).filter_by(
                task_id=view.selected_task.id,
                status='pending'
            ).first()
            
            if existing_request:
                await interaction.response.send_message(
                    "❌ There's already a pending snipe request for this task!",
                    ephemeral=True
                )
                return

            # Create snipe request
            snipe_request = SnipeRequest(
                task_id=view.selected_task.id,
                original_assignee=view.selected_task.assigned_to,
                sniper_id=str(interaction.user.id),
                server_id=str(interaction.guild_id)
            )
            session.add(snipe_request)
            session.commit()
            
            # Check if snipe channel is configured
            snipe_settings = session.query(SnipeSettings).filter_by(server_id=str(interaction.guild_id)).first()
            if not snipe_settings:
                await interaction.response.send_message(
                    "❌ Snipe requests are not configured for this server!\n\n"
                    "Ask an admin to set up a snipe channel with `/setsnipe #channel`",
                    ephemeral=True
                )
                return
            
            # Get the snipe channel
            snipe_channel = interaction.guild.get_channel(int(snipe_settings.snipe_channel_id))
            if not snipe_channel:
                await interaction.response.send_message(
                    "❌ The configured snipe channel no longer exists!\n\n"
                    "Ask an admin to reconfigure it with `/setsnipe #channel`",
                    ephemeral=True
                )
                return
            
            # Send request to the snipe channel
            admin_view = SnipeAdminApprovalView(snipe_request, view.selected_task)
            embed = discord.Embed(
                title="🎯 Task Snipe Request",
                description=f"**{interaction.user.display_name}** wants to claim credit for a task",
                color=discord.Color.orange()
            )
            embed.add_field(name="Task", value=view.selected_task.name, inline=False)
            
            # Show multiple originally assigned users
            if view.selected_task.assigned_to:
                assigned_ids = view.selected_task.assigned_to.split(',')
                assigned_mentions = ', '.join([f"<@{uid.strip()}>" for uid in assigned_ids])
            else:
                assigned_mentions = "Unknown"
            embed.add_field(name="Originally Assigned To", value=assigned_mentions, inline=True)
            
            embed.add_field(name="Requested By", value=f"<@{interaction.user.id}>", inline=True)
            embed.add_field(name="Due Date", value=format_task_date(view.selected_task.due_date, str(interaction.guild_id)), inline=False)
            embed.add_field(name="Description", value=view.selected_task.description, inline=False)
            
            await snipe_channel.send(embed=embed, view=admin_view)
            
            embed = discord.Embed(
                title="✅ Snipe Request Submitted",
                description=f"Your request to claim **{view.selected_task.name}** has been sent to {snipe_channel.mention} for admin approval.\n\n"
                           f"You'll receive a DM when an admin responds.",
                color=discord.Color.green()
            )
            
            # Disable all buttons
            for item in view.children:
                item.disabled = True
            
            await interaction.response.edit_message(embed=embed, view=view)
            
        except Exception as e:
            print(f"Error creating snipe request: {str(e)}")
            await interaction.response.send_message(
                f"An error occurred while processing your snipe request: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

class SnipeCancelButton(discord.ui.Button):
    def __init__(self, tasks, server_id):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="❌ Cancel"
        )
        self.tasks = tasks
        self.server_id = server_id

    async def callback(self, interaction: discord.Interaction):
        # Go back to task selection
        view = SnipeTaskView(self.tasks, interaction.user)
        embed = discord.Embed(
            title="🎯 Snipe a Task",
            description=f"Select a task that you've completed but aren't assigned to.\n"
                       f"Found {len(self.tasks)} available tasks to snipe.",
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class SnipeAdminApprovalView(discord.ui.View):
    def __init__(self, snipe_request: SnipeRequest, task: Task):
        super().__init__(timeout=None)  # No timeout for admin decisions
        # Store individual attributes to avoid detached instance errors
        self.snipe_request_id = snipe_request.id
        self.task_id = task.id
        self.server_id = snipe_request.server_id
        self.sniper_id = snipe_request.sniper_id
        self.original_assignee = snipe_request.original_assignee
        self.task_name = task.name

    @discord.ui.button(label="✅ Approve", style=discord.ButtonStyle.success)
    async def approve_snipe(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[DEBUG] Approve snipe button clicked by {interaction.user.display_name}")
        try:
            await self._handle_snipe_decision(interaction, 'approved')
        except Exception as e:
            print(f"[ERROR] Error in approve_snipe: {str(e)}")
            import traceback
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Error processing approval: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Error processing approval: {str(e)}", ephemeral=True)
            except:
                pass

    @discord.ui.button(label="❌ Deny", style=discord.ButtonStyle.danger)
    async def deny_snipe(self, interaction: discord.Interaction, button: discord.ui.Button):
        print(f"[DEBUG] Deny snipe button clicked by {interaction.user.display_name}")
        try:
            await self._handle_snipe_decision(interaction, 'denied')
        except Exception as e:
            print(f"[ERROR] Error in deny_snipe: {str(e)}")
            import traceback
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Error processing denial: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Error processing denial: {str(e)}", ephemeral=True)
            except:
                pass

    async def _handle_snipe_decision(self, interaction: discord.Interaction, decision: str):
        print(f"[DEBUG] Starting _handle_snipe_decision for {decision}")
        
        # Defer the response immediately to avoid timeout
        try:
            await interaction.response.defer()
            print(f"[DEBUG] Interaction deferred successfully")
        except Exception as e:
            print(f"[ERROR] Failed to defer interaction: {str(e)}")
            return
        
        session = get_session(self.server_id)
        try:
            print(f"[DEBUG] Got database session for server {self.server_id}")
            
            # Get the latest snipe request from database
            snipe_request = session.query(SnipeRequest).get(self.snipe_request_id)
            if not snipe_request:
                print(f"[ERROR] Snipe request {self.snipe_request_id} not found!")
                await interaction.followup.send("❌ Snipe request not found!", ephemeral=True)
                return

            print(f"[DEBUG] Found snipe request with status: {snipe_request.status}")
            
            if snipe_request.status != 'pending':
                await interaction.followup.send(
                    f"❌ This request has already been {snipe_request.status} by another admin!",
                    ephemeral=True
                )
                return

            # Update snipe request
            snipe_request.status = decision
            snipe_request.handled_by = str(interaction.user.id)
            snipe_request.handled_at = datetime.utcnow()
            print(f"[DEBUG] Updated snipe request status to {decision}")

            if decision == 'approved':
                # Transfer the task to the sniper
                task = session.query(Task).get(self.task_id)
                if task:
                    print(f"[DEBUG] Found task {self.task_id}, transferring to sniper {self.sniper_id}")
                    old_assignee = task.assigned_to
                    
                    # Update task assignment and completion
                    task.assigned_to = self.sniper_id
                    task.completed = True
                    
                    # Set completion time - if current time would make it late, 
                    # set it to due date to avoid late penalty (sniper completed it on time)
                    current_time = datetime.utcnow()
                    if current_time > task.due_date:
                        # Task would be marked as late, so set completion to due date
                        task.completed_at = task.due_date
                        print(f"[DEBUG] Task would be late, setting completion time to due date to avoid late penalty")
                    else:
                        # Task is still on time, use current time
                        task.completed_at = current_time
                        print(f"[DEBUG] Task completed on time")
                    
                    # Set snipe tracking information
                    task.is_sniped = True
                    task.sniped_from = old_assignee
                    task.sniped_by = self.sniper_id
                    task.sniped_at = current_time
                    
                    print(f"[DEBUG] Task marked as completed via snipe from {old_assignee} by {self.sniper_id}")
                else:
                    print(f"[ERROR] Task {self.task_id} not found!")

            session.commit()
            print(f"[DEBUG] Database changes committed")

            # Update the admin's message first (quick response)
            embed = discord.Embed(
                title=f"✅ Snipe Request {decision.title()}",
                description=f"You have **{decision}** the snipe request for **{self.task_name}**.",
                color=discord.Color.green() if decision == 'approved' else discord.Color.red()
            )
            
            # Disable all buttons
            for item in self.children:
                item.disabled = True
            
            await interaction.followup.edit_message(interaction.message.id, embed=embed, view=self)
            print(f"[DEBUG] Admin message updated")

            # Send DM to the person who made the request (this can be slower)
            try:
                print(f"[DEBUG] Attempting to send DM to sniper {self.sniper_id}")
                sniper = await _client.fetch_user(int(self.sniper_id))
                guild = _client.get_guild(int(self.server_id))
                server_name = guild.name if guild else "Unknown Server"
                
                if sniper:
                    result_embed = discord.Embed(
                        title=f"🎯 Snipe Request {'Approved' if decision == 'approved' else 'Denied'}",
                        description=f"Your request to claim **{self.task_name}** in **{server_name}** has been **{decision}** by {interaction.user.display_name}.",
                        color=discord.Color.green() if decision == 'approved' else discord.Color.red()
                    )
                    if decision == 'approved':
                        # Check if we prevented a late penalty
                        task_for_check = session.query(Task).get(self.task_id)
                        late_prevention_note = ""
                        if task_for_check and task_for_check.completed_at == task_for_check.due_date:
                            late_prevention_note = "\n\n**Note:** Since you completed this on time, it won't be marked as late even though the admin approval came after the due date."
                        
                        result_embed.add_field(
                            name="Task Completed",
                            value=f"The task has been transferred to you and marked as completed. Great work! 🎉{late_prevention_note}",
                            inline=False
                        )
                    await sniper.send(embed=result_embed)
                    print(f"[DEBUG] DM sent to sniper successfully")
                else:
                    print(f"[ERROR] Could not fetch sniper user {self.sniper_id}")
            except Exception as dm_error:
                print(f"[ERROR] Failed to send DM to sniper: {str(dm_error)}")
                # Don't fail the whole operation if DM fails

        except Exception as e:
            print(f"[ERROR] Error handling snipe decision: {str(e)}")
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(
                    f"❌ An error occurred while processing the decision: {str(e)}",
                    ephemeral=True
                )
            except:
                print(f"[ERROR] Failed to send error message to admin")
        finally:
            session.close()
            print(f"[DEBUG] Database session closed")

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
        assigned_to="Users to assign the task to (mention users separated by spaces: @user1 @user2 @user3)"
    )
    @log_command
    async def task(interaction: discord.Interaction, assigned_to: str):
        # Check if user can create tasks
        if not await can_create_tasks(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to create tasks!\n\n"
                "Only administrators or whitelisted users can use this command.\n"
                "Ask an admin to add you with `/tcw add @user`",
                ephemeral=True
            )
            return
        
        # Parse user mentions from the assigned_to string
        user_mentions = re.findall(r'<@!?(\d+)>', assigned_to)
        if not user_mentions:
            await interaction.response.send_message(
                "❌ Invalid user format! Please mention users like this:\n"
                "`@user1 @user2 @user3`\n\n"
                "Example: `/task assigned_to: @John @Jane @Bob`",
                ephemeral=True
            )
            return
        
        # Validate that all mentioned users exist in the server
        assigned_users = []
        for user_id in user_mentions:
            try:
                user = interaction.guild.get_member(int(user_id))
                if user:
                    assigned_users.append(user)
                else:
                    # Try to fetch the user if not in cache
                    user = await interaction.guild.fetch_member(int(user_id))
                    assigned_users.append(user)
            except (discord.NotFound, discord.HTTPException):
                await interaction.response.send_message(
                    f"❌ User with ID {user_id} not found in this server!",
                    ephemeral=True
                )
                return
        
        if not assigned_users:
            await interaction.response.send_message(
                "❌ No valid users found! Please mention users that are in this server.",
                ephemeral=True
            )
            return
        
        # Show the task creation modal with selected users
        modal = TaskCreationModal(assigned_users, str(interaction.guild_id))
        await interaction.response.send_modal(modal)

    @tree.command(
        name="mytasks",
        description="View your tasks"
    )
    @log_command
    async def mytasks(interaction: discord.Interaction):
        session = get_session(str(interaction.guild_id))
        try:
            # Query for tasks where user ID appears in the comma-separated assigned_to field
            user_id = str(interaction.user.id)
            tasks = session.query(Task).filter(
                Task.assigned_to.like(f'%{user_id}%'),
                Task.completed == False
            ).order_by(Task.due_date).all()
            
            # Filter to ensure exact match (avoid partial ID matches)
            filtered_tasks = []
            for task in tasks:
                assigned_ids = task.assigned_to.split(',') if task.assigned_to else []
                if user_id in assigned_ids:
                    filtered_tasks.append(task)
            
            if not filtered_tasks:
                await interaction.response.send_message(
                    "You have no pending tasks! 🎉",
                    ephemeral=True
                )
                return
            
            if len(filtered_tasks) == 1:
                # Single task - show detailed view
                task = filtered_tasks[0]
                embed = discord.Embed(
                    title="📋 Your Task",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Task Name", value=task.name, inline=False)
                
                # Show all assignees for this task
                try:
                    all_assignees = await get_multiple_user_mentions(interaction.client, task.assigned_to, str(interaction.guild_id))
                    embed.add_field(name="👥 Assigned To", value=all_assignees, inline=False)
                except:
                    # Fallback if mention fetching fails
                    assigned_ids = task.assigned_to.split(',') if task.assigned_to else []
                    assignee_mentions = ', '.join([f"<@{uid.strip()}>" for uid in assigned_ids])
                    embed.add_field(name="👥 Assigned To", value=assignee_mentions, inline=False)
                
                embed.add_field(name="Due Date", value=format_task_date(task.due_date, str(interaction.guild_id)), inline=True)
                embed.add_field(name="Description", value=task.description, inline=False)
                
                # Calculate time remaining
                time_diff = task.due_date - get_current_utc()
                if time_diff.total_seconds() > 0:
                    days = time_diff.days
                    hours, remainder = divmod(time_diff.seconds, 3600)
                    embed.add_field(name="Time Remaining", value=f"{days}d {hours}h", inline=True)
                else:
                    embed.add_field(name="Status", value="⚠️ OVERDUE", inline=True)
                
                view = TaskView(filtered_tasks, interaction.user)
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            else:
                # Multiple tasks - show list view
                view = TaskView(filtered_tasks, interaction.user)
                embed = discord.Embed(
                    title=f"📋 Your Tasks ({len(filtered_tasks)})",
                    description="Select a task below to view details and mark as complete:",
                    color=discord.Color.blue()
                )
                
                for i, task in enumerate(filtered_tasks[:5]):  # Show first 5 tasks in embed
                    due_date = task.due_date.strftime('%Y-%m-%d %H:%M')
                    embed.add_field(
                        name=f"{i+1}. {task.name}",
                        value=f"Due: {due_date}\n{task.description[:50]}{'...' if len(task.description) > 50 else ''}",
                        inline=False
                    )
                
                if len(filtered_tasks) > 5:
                    embed.set_footer(text=f"Showing first 5 tasks. Use the dropdown to see all {len(filtered_tasks)} tasks.")
                
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
            # Query for tasks where target user ID appears in the comma-separated assigned_to field
            user_id = str(target_user.id)
            tasks = session.query(Task).filter(
                Task.assigned_to.like(f'%{user_id}%'),
                Task.server_id == str(interaction.guild_id),
                Task.completed == False
            ).order_by(Task.due_date).all()
            
            # Filter to ensure exact match (avoid partial ID matches)
            filtered_tasks = []
            for task in tasks:
                assigned_ids = task.assigned_to.split(',') if task.assigned_to else []
                if user_id in assigned_ids:
                    filtered_tasks.append(task)
            
            if not filtered_tasks:
                await interaction.response.send_message(
                    f"{target_user.display_name} has no pending tasks!",
                    ephemeral=True
                )
                return
            
            # Collect all unique creator IDs for tasks we'll display
            display_tasks = filtered_tasks[:10]  # Limit to 10 tasks to avoid embed limits
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
                # Format date in server timezone
                due_date = format_task_date(task.due_date, str(interaction.guild_id), False)
                
                # Calculate time remaining
                time_diff = task.due_date - get_current_utc()
                if time_diff.total_seconds() > 0:
                    days = time_diff.days
                    hours, remainder = divmod(time_diff.seconds, 3600)
                    time_status = f"⏰ {days}d {hours}h remaining"
                else:
                    time_status = "⚠️ OVERDUE"
                
                # Get all assignees for this task
                try:
                    all_assignees = await get_multiple_user_mentions(interaction.client, task.assigned_to, str(interaction.guild_id))
                except:
                    # Fallback if mention fetching fails
                    assigned_ids = task.assigned_to.split(',') if task.assigned_to else []
                    all_assignees = ', '.join([f"<@{uid.strip()}>" for uid in assigned_ids])
                
                # Get creator mention
                creator_name = user_cache.get(task.created_by, "Unknown") if task.created_by != "0" else "Unknown"
                try:
                    creator_mention = await get_user_mention(interaction.client, task.created_by, str(interaction.guild_id))
                except:
                    creator_mention = creator_name
                
                value = (
                    f"**👥 Assigned to:** {all_assignees}\n"
                    f"**Due:** {due_date}\n"
                    f"**Status:** {time_status}\n"
                    f"**Created by:** {creator_mention}\n"
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
        description="View all active tasks in the server"
    )
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
                if task.assigned_to:
                    assigned_ids = task.assigned_to.split(',')
                    assigned_names = []
                    for user_id in assigned_ids:
                        user_id = user_id.strip()
                        assigned_names.append(user_cache.get(user_id, "Unknown"))
                    task._assigned_name = ', '.join(assigned_names)
                else:
                    task._assigned_name = "Unknown"
                task._creator_name = user_cache.get(task.created_by, "Unknown") if task.created_by != "0" else "Unknown"
            
            # Create paginated view
            view = PaginatedTaskView(tasks, tasks_per_page=5, server_id=str(interaction.guild_id), bot=interaction.client)
            embed = await view.get_current_page_embed()
            
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
            # Query for completed tasks where user ID appears in the comma-separated assigned_to field
            user_id = str(user.id)
            completed_tasks = session.query(Task).filter(
                Task.assigned_to.like(f'%{user_id}%'),
                Task.server_id == str(interaction.guild_id),
                Task.completed == True
            ).order_by(Task.completed_at.desc()).all()  # Most recent first
            
            # Filter to ensure exact match (avoid partial ID matches)
            filtered_tasks = []
            for task in completed_tasks:
                assigned_ids = task.assigned_to.split(',') if task.assigned_to else []
                if user_id in assigned_ids:
                    filtered_tasks.append(task)
            
            # Calculate statistics
            total_completed = len(filtered_tasks)
            late_completed = 0
            
            for task in filtered_tasks:
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
            for task in filtered_tasks:
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
            for task in filtered_tasks:
                task._creator_name = user_cache.get(task.created_by, "Unknown") if task.created_by != "0" else "Unknown"
            
            # Create paginated view with statistics
            view = PaginatedCompletedTaskView(
                tasks=filtered_tasks,
                user_name=user.display_name,
                total_completed=total_completed,
                late_completed=late_completed,
                tasks_per_page=5,
                server_id=str(interaction.guild_id),
                bot=interaction.client
            )
            embed = await view.get_current_page_embed()
            
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

    # ============= TIMEZONE SELECTION VIEWS =============
    
    class TimezoneRegionSelect(discord.ui.Select):
        def __init__(self):
            timezones = get_all_timezones()
            # Create options for major regions
            regions = ['America', 'Europe', 'Asia', 'Africa', 'Australia', 'Pacific', 'Other']
            options = []
            
            for region in regions:
                if region in timezones:
                    count = len(timezones[region])
                    options.append(discord.SelectOption(
                        label=region,
                        value=region,
                        description=f"{count} timezones available"
                    ))
            
            super().__init__(
                placeholder="Select a region to view timezones...",
                options=options,
                min_values=1,
                max_values=1
            )
        
        async def callback(self, interaction: discord.Interaction):
            region = self.values[0]
            timezones = get_all_timezones()
            
            if region not in timezones:
                await interaction.response.send_message("❌ Invalid region selected.", ephemeral=True)
                return
            
            # Create timezone selection view
            view = TimezoneSelectionView(region, timezones[region])
            
            embed = discord.Embed(
                title=f"🌍 Select Timezone - {region}",
                description=f"Choose a timezone from the {region} region:",
                color=discord.Color.blue()
            )
            
            # Add pagination info if multiple pages
            if len(timezones[region]) > 25:
                pages = (len(timezones[region]) + 24) // 25  # Round up
                embed.set_footer(text=f"Page 1 of {pages} • Use navigation buttons to browse all timezones")
            
            await interaction.response.edit_message(embed=embed, view=view)

    class TimezoneSelectionView(discord.ui.View):
        def __init__(self, region: str, timezone_list: list, page: int = 0):
            super().__init__(timeout=300)
            self.region = region
            self.timezone_list = timezone_list
            self.page = page
            
            # Split timezones into chunks of 25 (Discord's limit for select options)
            chunk_size = 25
            chunks = [timezone_list[i:i + chunk_size] for i in range(0, len(timezone_list), chunk_size)]
            self.chunks = chunks
            self.total_pages = len(chunks)
            
            # Add current page select
            if chunks:
                current_chunk = chunks[page] if page < len(chunks) else chunks[0]
                select = TimezoneSelect(current_chunk, f"{region} - Page {page + 1}/{len(chunks)}")
                self.add_item(select)
            
            # Add navigation buttons if multiple pages
            if self.total_pages > 1:
                if page > 0:
                    self.add_item(PreviousPageButton())
                if page < self.total_pages - 1:
                    self.add_item(NextPageButton())
            
            # Add back button
            self.add_item(BackToRegionsButton())

    class TimezoneSelect(discord.ui.Select):
        def __init__(self, timezones: list, label: str):
            options = []
            for tz in timezones:
                # Get current time in this timezone for preview
                try:
                    tz_obj = pytz.timezone(tz)
                    current_time = datetime.now(tz_obj)
                    time_str = current_time.strftime("%H:%M")
                    
                    # Format display name
                    display_name = tz.replace('_', ' ')
                    if '/' in display_name:
                        display_name = display_name.split('/')[-1]
                    
                    options.append(discord.SelectOption(
                        label=display_name[:100],  # Discord limit
                        value=tz,
                        description=f"{time_str} - {tz}"[:100]
                    ))
                except:
                    options.append(discord.SelectOption(
                        label=tz[:100],
                        value=tz,
                        description=tz[:100]
                    ))
            
            super().__init__(
                placeholder=f"Select timezone from {label}...",
                options=options,
                min_values=1,
                max_values=1
            )
        
        async def callback(self, interaction: discord.Interaction):
            selected_tz = self.values[0]
            server_id = str(interaction.guild_id)
            
            try:
                # Validate timezone
                pytz.timezone(selected_tz)
                
                # Save timezone setting
                set_server_timezone(server_id, selected_tz)
                
                # Get current time in selected timezone
                tz_obj = pytz.timezone(selected_tz)
                current_time = datetime.now(tz_obj)
                
                embed = discord.Embed(
                    title="✅ Timezone Set Successfully!",
                    description=f"Server timezone has been set to **{selected_tz}**",
                    color=discord.Color.green()
                )
                embed.add_field(
                    name="Current Time",
                    value=f"{current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                    inline=False
                )
                embed.add_field(
                    name="Note",
                    value="All new tasks will be displayed in this timezone. Existing tasks remain in their original timezone.",
                    inline=False
                )
                
                await interaction.response.edit_message(embed=embed, view=None)
                
            except Exception as e:
                await interaction.response.send_message(
                    f"❌ Error setting timezone: {str(e)}",
                                    ephemeral=True
            )

    class PreviousPageButton(discord.ui.Button):
        def __init__(self):
            super().__init__(
                label="◀️ Previous",
                style=discord.ButtonStyle.secondary,
                row=4
            )
        
        async def callback(self, interaction: discord.Interaction):
            # Get current view
            current_view = self.view
            if hasattr(current_view, 'page') and hasattr(current_view, 'region'):
                new_page = max(0, current_view.page - 1)
                view = TimezoneSelectionView(current_view.region, current_view.timezone_list, new_page)
                
                embed = discord.Embed(
                    title=f"🌍 Select Timezone - {current_view.region}",
                    description=f"Choose a timezone from the {current_view.region} region:",
                    color=discord.Color.blue()
                )
                
                if len(current_view.timezone_list) > 25:
                    pages = (len(current_view.timezone_list) + 24) // 25
                    embed.set_footer(text=f"Page {new_page + 1} of {pages} • Use navigation buttons to browse all timezones")
                
                await interaction.response.edit_message(embed=embed, view=view)

    class NextPageButton(discord.ui.Button):
        def __init__(self):
            super().__init__(
                label="Next ▶️",
                style=discord.ButtonStyle.secondary,
                row=4
            )
        
        async def callback(self, interaction: discord.Interaction):
            # Get current view
            current_view = self.view
            if hasattr(current_view, 'page') and hasattr(current_view, 'region'):
                new_page = min(current_view.total_pages - 1, current_view.page + 1)
                view = TimezoneSelectionView(current_view.region, current_view.timezone_list, new_page)
                
                embed = discord.Embed(
                    title=f"🌍 Select Timezone - {current_view.region}",
                    description=f"Choose a timezone from the {current_view.region} region:",
                    color=discord.Color.blue()
                )
                
                if len(current_view.timezone_list) > 25:
                    pages = (len(current_view.timezone_list) + 24) // 25
                    embed.set_footer(text=f"Page {new_page + 1} of {pages} • Use navigation buttons to browse all timezones")
                
                await interaction.response.edit_message(embed=embed, view=view)

    class BackToRegionsButton(discord.ui.Button):
        def __init__(self):
            super().__init__(
                label="← Back to Regions",
                style=discord.ButtonStyle.secondary,
                row=4
            )
        
        async def callback(self, interaction: discord.Interaction):
            view = TimezoneRegionView()
            
            embed = discord.Embed(
                title="🌍 Server Timezone Settings",
                description="Select a region to browse available timezones:",
                color=discord.Color.blue()
            )
            
            # Show current timezone
            server_id = str(interaction.guild_id)
            current_tz = get_server_timezone(server_id)
            try:
                tz_obj = pytz.timezone(current_tz)
                current_time = datetime.now(tz_obj)
                embed.add_field(
                    name="Current Timezone",
                    value=f"**{current_tz}**\n{current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                    inline=False
                )
            except:
                embed.add_field(
                    name="Current Timezone",
                    value=f"**{current_tz}** (UTC)",
                    inline=False
                )
            
            await interaction.response.edit_message(embed=embed, view=view)

    class TimezoneRegionView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=300)
            self.add_item(TimezoneRegionSelect())

    @tree.command(
        name="snipe",
        description="Claim credit for a task assigned to someone else that you completed"
    )
    @log_command
    async def snipe(interaction: discord.Interaction):
        """Allow users to claim credit for tasks they completed but weren't assigned to"""
        session = get_session(str(interaction.guild_id))
        try:
            # Get all incomplete tasks and filter out ones assigned to current user
            all_tasks = session.query(Task).filter_by(
                server_id=str(interaction.guild_id),
                completed=False
            ).order_by(Task.due_date).all()
            
            # Filter out tasks where the current user is already assigned
            tasks = []
            current_user_id = str(interaction.user.id)
            for task in all_tasks:
                assigned_ids = task.assigned_to.split(',') if task.assigned_to else []
                if current_user_id not in assigned_ids:
                    tasks.append(task)
            
            if not tasks:
                await interaction.response.send_message(
                    "🎯 No tasks available to snipe!\n\n"
                    "Either all tasks are completed, assigned to you, or there are no active tasks.",
                    ephemeral=True
                )
                return

            # Fetch user names for better display
            user_ids = set()
            for task in tasks:
                if task.assigned_to:
                    assigned_ids = task.assigned_to.split(',')
                    for user_id in assigned_ids:
                        user_ids.add(user_id.strip())
            
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

            # Add user names to tasks for display
            for task in tasks:
                if task.assigned_to:
                    assigned_ids = task.assigned_to.split(',')
                    assigned_names = []
                    for user_id in assigned_ids:
                        user_id = user_id.strip()
                        assigned_names.append(user_cache.get(user_id, "Unknown"))
                    task._assigned_name = ', '.join(assigned_names)
                else:
                    task._assigned_name = "Unknown"

            view = SnipeTaskView(tasks, interaction.user)
            embed = discord.Embed(
                title="🎯 Snipe a Task",
                description=f"Select a task that you've completed but aren't assigned to.\n"
                           f"Found **{len(tasks)}** available tasks to snipe.\n\n"
                           f"**Note:** Snipe requests require admin approval.",
                color=discord.Color.blue()
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            print(f"Error in snipe command: {str(e)}")
            await interaction.response.send_message(
                f"An error occurred while fetching available tasks: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
        name="setsnipe",
        description="Set the channel where snipe requests will be sent for admin approval"
    )
    @app_commands.describe(channel="The channel where snipe requests will be posted")
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def setsnipe(interaction: discord.Interaction, channel: discord.TextChannel):
        """Set the snipe request channel for this server"""
        session = get_session(str(interaction.guild_id))
        try:
            # Check if setting already exists
            snipe_settings = session.query(SnipeSettings).filter_by(server_id=str(interaction.guild_id)).first()
            
            if snipe_settings:
                # Update existing setting
                old_channel_id = snipe_settings.snipe_channel_id
                snipe_settings.snipe_channel_id = str(channel.id)
                snipe_settings.updated_at = datetime.utcnow()
                action = "updated"
            else:
                # Create new setting
                snipe_settings = SnipeSettings(
                    server_id=str(interaction.guild_id),
                    snipe_channel_id=str(channel.id)
                )
                session.add(snipe_settings)
                action = "set"
            
            session.commit()
            
            embed = discord.Embed(
                title="✅ Snipe Channel Configuration",
                description=f"Snipe requests have been {action} to go to {channel.mention}",
                color=discord.Color.green()
            )
            embed.add_field(
                name="How it works",
                value="• Users can now use `/snipe` to claim tasks assigned to others\n"
                      "• All snipe requests will appear in this channel\n"
                      "• Admins can approve/deny requests using the buttons\n"
                      "• Users will be notified via DM of the decision",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Error in setsnipe command: {str(e)}")
            await interaction.response.send_message(
                f"❌ An error occurred while setting the snipe channel: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
        name="clearsnipes",
        description="Clear all pending snipe requests"
    )
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def clearsnipes(interaction: discord.Interaction):
        """Clear all pending snipe requests for this server"""
        session = get_session(str(interaction.guild_id))
        try:
            # Get all pending snipe requests
            pending_requests = session.query(SnipeRequest).filter_by(
                server_id=str(interaction.guild_id),
                status='pending'
            ).all()
            
            if not pending_requests:
                await interaction.response.send_message(
                    "✅ No pending snipe requests found!",
                    ephemeral=True
                )
                return
            
            # Delete all pending requests
            for request in pending_requests:
                session.delete(request)
            
            session.commit()
            
            embed = discord.Embed(
                title="🗑️ Snipe Requests Cleared",
                description=f"Cleared **{len(pending_requests)}** pending snipe request(s).",
                color=discord.Color.red()
            )
            embed.add_field(
                name="What was cleared",
                value="All pending snipe requests have been permanently removed.\n"
                      "Users will not be notified of this action.",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Error in clearsnipes command: {str(e)}")
            await interaction.response.send_message(
                f"❌ An error occurred while clearing snipe requests: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
        name="timezone",
        description="Set the timezone for task display in this server"
    )
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def timezone(interaction: discord.Interaction):
        """Set server timezone for task display"""
        try:
            view = TimezoneRegionView()
            
            embed = discord.Embed(
                title="🌍 Server Timezone Settings",
                description="Select a region to browse available timezones:",
                color=discord.Color.blue()
            )
            
            # Show current timezone
            server_id = str(interaction.guild_id)
            current_tz = get_server_timezone(server_id)
            try:
                tz_obj = pytz.timezone(current_tz)
                current_time = datetime.now(tz_obj)
                embed.add_field(
                    name="Current Timezone",
                    value=f"**{current_tz}**\n{current_time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                    inline=False
                )
            except:
                embed.add_field(
                    name="Current Timezone",
                    value=f"**{current_tz}** (UTC)",
                    inline=False
                )
            
            embed.add_field(
                name="How it works",
                value="• New tasks will be displayed in your selected timezone\n"
                      "• Task due dates are converted for display only\n"
                      "• All times are stored in UTC internally for accuracy",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error loading timezone settings: {str(e)}",
                ephemeral=True
            )

# Export the setup function
__all__ = ['setup_task_system', 'setup_task_commands'] 