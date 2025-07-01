import discord
from discord import app_commands
from discord.ext import commands
from discord.app_commands import checks
import asyncio
import functools
from typing import Callable, Any
import traceback
from datetime import datetime, timedelta
from dateutil import parser
from database import Task, TaskCreator, get_session

# Store reference to the client
_client = None

def setup_tasks_system(client):
    """Initialize the task system with client reference"""
    global _client
    _client = client

def log_command(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args: Any, **kwargs: Any) -> Any:
        try:
            print(f"Executing task command: {func.__name__}")
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
    session = get_session()
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
            
            # Enable all buttons
            for item in view.children:
                if hasattr(item, 'disabled'):
                    item.disabled = False

            await interaction.response.edit_message(view=view)
        
        except Exception as e:
            print(f"Error in task edit selection: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                "An error occurred while processing your selection.",
                ephemeral=True
            )
        finally:
            session.close()

class TaskEditView(discord.ui.View):
    def __init__(self, tasks, user):
        super().__init__(timeout=300)
        self.tasks = tasks
        self.user = user
        self.selected_task = None
        
        # Add the task selection dropdown
        self.add_item(TaskEditSelect(tasks))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Ensure only the original user can interact with this view"""
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "You cannot interact with someone else's task editor.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Edit Name", custom_id="edit_name_btn", style=discord.ButtonStyle.primary, disabled=True, row=1)
    async def edit_name(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_task:
            await interaction.response.send_message("Please select a task first!", ephemeral=True)
            return
        
        modal = TaskEditModal(self.selected_task, "name")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Due Date", custom_id="edit_due_date_btn", style=discord.ButtonStyle.primary, disabled=True, row=1)
    async def edit_due_date(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_task:
            await interaction.response.send_message("Please select a task first!", ephemeral=True)
            return
        
        modal = TaskEditModal(self.selected_task, "due_date")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Edit Description", custom_id="edit_desc_btn", style=discord.ButtonStyle.primary, disabled=True, row=2)
    async def edit_description(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_task:
            await interaction.response.send_message("Please select a task first!", ephemeral=True)
            return
        
        modal = TaskEditModal(self.selected_task, "description")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Change Assignee", custom_id="edit_assignee_btn", style=discord.ButtonStyle.primary, disabled=True, row=2)
    async def edit_assignee(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_task:
            await interaction.response.send_message("Please select a task first!", ephemeral=True)
            return
        
        modal = TaskEditModal(self.selected_task, "assignee")
        await interaction.response.send_modal(modal)

class TaskEditModal(discord.ui.Modal):
    def __init__(self, task: Task, field: str):
        self.task = task
        self.field = field
        
        if field == "name":
            super().__init__(title="Edit Task Name")
            self.add_item(discord.ui.TextInput(
                label="Task Name",
                default=task.name,
                max_length=200,
                required=True
            ))
        elif field == "due_date":
            super().__init__(title="Edit Due Date")
            self.add_item(discord.ui.TextInput(
                label="Due Date (YYYY-MM-DD HH:MM)",
                default=task.due_date.strftime('%Y-%m-%d %H:%M'),
                max_length=16,
                required=True
            ))
        elif field == "description":
            super().__init__(title="Edit Task Description")
            self.add_item(discord.ui.TextInput(
                label="Description",
                default=task.description,
                style=discord.TextStyle.paragraph,
                max_length=1000,
                required=True
            ))
        elif field == "assignee":
            super().__init__(title="Change Assignee")
            self.add_item(discord.ui.TextInput(
                label="New Assignee (User ID)",
                placeholder="Enter the Discord User ID",
                max_length=20,
                required=True
            ))

    async def on_submit(self, interaction: discord.Interaction):
        session = get_session()
        try:
            # Refresh the task from database
            task = session.query(Task).get(self.task.id)
            if not task:
                await interaction.response.send_message("Task not found!", ephemeral=True)
                return

            field_value = self.children[0].value

            if self.field == "name":
                task.name = field_value
                await interaction.response.send_message(f"✅ Task name updated to: {field_value}", ephemeral=True)
            
            elif self.field == "due_date":
                try:
                    new_due_date = parser.parse(field_value)
                    task.due_date = new_due_date
                    await interaction.response.send_message(f"✅ Due date updated to: {new_due_date.strftime('%Y-%m-%d %H:%M UTC')}", ephemeral=True)
                except ValueError:
                    await interaction.response.send_message("❌ Invalid date format! Please use YYYY-MM-DD HH:MM", ephemeral=True)
                    return
            
            elif self.field == "description":
                task.description = field_value
                await interaction.response.send_message("✅ Task description updated successfully!", ephemeral=True)
            
            elif self.field == "assignee":
                try:
                    user_id = int(field_value)
                    # Verify the user exists
                    try:
                        user = await _client.fetch_user(user_id)
                        task.assigned_to = str(user_id)
                        await interaction.response.send_message(f"✅ Task reassigned to: {user.display_name}", ephemeral=True)
                    except discord.NotFound:
                        await interaction.response.send_message("❌ User not found! Please check the User ID.", ephemeral=True)
                        return
                except ValueError:
                    await interaction.response.send_message("❌ Invalid User ID! Please enter a valid Discord User ID.", ephemeral=True)
                    return

            session.commit()
            
        except Exception as e:
            print(f"Error updating task: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(f"❌ An error occurred while updating the task: {str(e)}", ephemeral=True)
        finally:
            session.close()

class PaginatedTaskView(discord.ui.View):
    def __init__(self, tasks, tasks_per_page=5):
        super().__init__(timeout=300)
        self.tasks = tasks
        self.tasks_per_page = tasks_per_page
        self.current_page = 0
        self.total_pages = max(1, (len(tasks) + tasks_per_page - 1) // tasks_per_page)
        
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

    @tree.command(
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
                    creator = await _client.fetch_user(int(task.created_by)) if task.created_by != "0" else None
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

    @tree.command(
        name="taskedit",
        description="Edit an existing task"
    )
    @log_command
    async def taskedit(interaction: discord.Interaction):
        session = get_session()
        try:
            # Get tasks created by or assigned to this user
            user_created_tasks = session.query(Task).filter_by(
                created_by=str(interaction.user.id),
                server_id=str(interaction.guild_id),
                completed=False
            ).all()
            
            user_assigned_tasks = session.query(Task).filter_by(
                assigned_to=str(interaction.user.id),
                server_id=str(interaction.guild_id),
                completed=False
            ).all()
            
            # Combine and deduplicate
            all_user_tasks = list({task.id: task for task in user_created_tasks + user_assigned_tasks}.values())
            
            if not all_user_tasks:
                await interaction.response.send_message(
                    "You have no tasks to edit! You can only edit tasks you created or tasks assigned to you.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="Task Editor",
                description="Select a task to edit from the dropdown below:",
                color=discord.Color.orange()
            )
            
            view = TaskEditView(all_user_tasks, interaction.user)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            print(f"Error in taskedit command: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                f"An error occurred while processing the command: {str(e)}",
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
        session = get_session()
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
            
            embed = discord.Embed(
                title=f"Tasks for {target_user.display_name}",
                color=discord.Color.blue()
            )
            
            for task in tasks:
                due_date = task.due_date.strftime('%Y-%m-%d %H:%M UTC')
                try:
                    creator = await _client.fetch_user(int(task.created_by)) if task.created_by != "0" else None
                    creator_name = creator.display_name if creator else "Unknown"
                except:
                    creator_name = "Unknown"
                
                value = (
                    f"Due: {due_date}\n"
                    f"Created by: {creator_name}\n"
                    f"Description: {task.description}"
                )
                embed.add_field(name=task.name, value=value, inline=False)
            
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
                    assigned_to = await _client.fetch_user(int(task.assigned_to))
                    task._assigned_name = assigned_to.display_name if assigned_to else "Unknown"
                    creator = await _client.fetch_user(int(task.created_by)) if task.created_by != "0" else None
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

    print("✅ Task commands registered successfully")

# Export the setup function
__all__ = ['setup_tasks_system', 'setup_task_commands'] 