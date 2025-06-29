import discord
from discord import app_commands
import requests
import os
from keep_alive import keep_alive
from datetime import datetime, timedelta
from dateutil import parser
from database import Task, get_session
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import Optional

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
    def __init__(self, tasks, show_complete=True, user=None):
        super().__init__(timeout=180)
        self.tasks = tasks
        self.show_complete = show_complete
        if user:
            self.add_item(UserButton(user))
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        
        # Add a select menu for tasks
        options = []
        for i, task in enumerate(self.tasks):
            due_date = task.due_date.strftime('%Y-%m-%d')
            options.append(discord.SelectOption(
                label=f"{task.name} (Due: {due_date})",
                value=str(i),
                description=f"Click to view details"
            ))
        
        if options:
            select_menu = discord.ui.Select(
                placeholder="Select a task to view details",
                options=options,
                custom_id="task_select"
            )
            select_menu.callback = self.handle_select
            self.add_item(select_menu)
            
            if self.show_complete:
                # Add complete buttons for each task
                for i, task in enumerate(self.tasks):
                    complete_button = discord.ui.Button(
                        label=f"Complete: {task.name}",
                        custom_id=f"complete_{i}",
                        style=discord.ButtonStyle.success,
                        row=i+1
                    )
                    complete_button.callback = lambda i=i: self.handle_complete(i)
                    self.add_item(complete_button)

    async def handle_select(self, interaction: discord.Interaction):
        task_index = int(interaction.data['values'][0])
        task = self.tasks[task_index]
        
        embed = discord.Embed(
            title=f"Task Details: {task.name}",
            description=task.description,
            color=discord.Color.blue()
        )
        embed.add_field(name="Due Date", value=task.due_date.strftime('%Y-%m-%d %H:%M UTC'))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def handle_complete(self, task_index: int):
        task = self.tasks[task_index]
        session = get_session()
        try:
            task_db = session.query(Task).filter_by(id=task.id).first()
            if task_db:
                task_db.completed = True
                session.commit()
                self.tasks.pop(task_index)
                
                if not self.tasks:
                    await interaction.message.delete()
                    await interaction.response.send_message("All tasks completed! 🎉")
                    return
                    
                self.update_buttons()
                await self.update_message(interaction)
        finally:
            session.close()

    async def update_message(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Tasks",
            description="Select a task to view details or mark as complete",
            color=discord.Color.blue()
        )
        
        # Add task summaries to embed
        for task in self.tasks:
            embed.add_field(
                name=task.name,
                value=f"Due: {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}",
                inline=False
            )
            
        await interaction.response.edit_message(embed=embed, view=self)

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
async def task(interaction: discord.Interaction, name: str, assigned_to: discord.Member, due_date: str, description: str):
    try:
        due_date_dt = parser.parse(due_date)
        
        session = get_session()
        try:
            new_task = Task(
                name=name,
                assigned_to=str(assigned_to.id),
                due_date=due_date_dt,
                description=description
            )
            session.add(new_task)
            session.commit()
            
            embed = discord.Embed(
                title="✅ Task Created",
                description=f"Task '{name}' has been assigned to {assigned_to.mention}",
                color=discord.Color.green()
            )
            embed.add_field(name="Due Date", value=due_date_dt.strftime('%Y-%m-%d %H:%M UTC'))
            await interaction.response.send_message(embed=embed)
            
            try:
                await assigned_to.send(f"You have been assigned a new task: **{name}**\nDue: {due_date_dt.strftime('%Y-%m-%d %H:%M UTC')}\n\nDescription:\n{description}")
            except discord.Forbidden:
                pass
                
        finally:
            session.close()
            
    except ValueError:
        await interaction.response.send_message("Invalid date format. Please use YYYY-MM-DD HH:MM format.", ephemeral=True)

@client.tree.command(
    name="mytasks",
    description="View your tasks"
)
async def mytasks(interaction: discord.Interaction):
    session = get_session()
    try:
        tasks = session.query(Task).filter_by(
            assigned_to=str(interaction.user.id),
            completed=False
        ).order_by(Task.due_date).all()
        
        if not tasks:
            await interaction.response.send_message(f"No pending tasks! 🎉")
            return
            
        embed = discord.Embed(
            title=f"Tasks",
            description="Select a task to view details or mark as complete:",
            color=discord.Color.blue()
        )
        
        for task in tasks:
            embed.add_field(
                name=task.name,
                value=f"Due: {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}",
                inline=False
            )
        
        view = TaskView(tasks, user=interaction.user)
        await interaction.response.send_message(embed=embed, view=view)
        
    finally:
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
    description="View completed tasks and their status"
)
async def oldtasks(interaction: discord.Interaction):
    session = get_session()
    try:
        completed_tasks = session.query(Task).filter_by(completed=True).order_by(Task.due_date.desc()).all()
        
        if not completed_tasks:
            await interaction.response.send_message("No completed tasks found!")
            return
            
        embed = discord.Embed(
            title="Completed Tasks History",
            description="Here are all completed tasks and their status:",
            color=discord.Color.gold()
        )
        
        # Group tasks by user
        tasks_by_user = {}
        for task in completed_tasks:
            user_id = task.assigned_to
            if user_id not in tasks_by_user:
                tasks_by_user[user_id] = []
            tasks_by_user[user_id].append(task)
        
        view = discord.ui.View(timeout=180)
        
        # Add tasks to embed, grouped by user
        for user_id, user_tasks in tasks_by_user.items():
            try:
                user = await client.fetch_user(int(user_id))
                if not user:
                    continue
                    
                # Add user profile button
                view.add_item(UserButton(user))
                
                tasks_text = []
                for task in user_tasks:
                    # Check if task was completed before or after due date
                    completed_status = "✅ On time" if task.completed_at <= task.due_date else "⚠️ Late"
                    tasks_text.append(
                        f"• {task.name}\n"
                        f"  Due: {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}\n"
                        f"  Status: {completed_status}"
                    )
                
                embed.add_field(
                    name=f"Tasks completed by {user.display_name}",
                    value="\n".join(tasks_text) or "No completed tasks",
                    inline=False
                )
            except:
                continue
        
        await interaction.response.send_message(embed=embed, view=view)
        
    finally:
        session.close()

@client.tree.command(
    name="alltasks",
    description="View all tasks in the server"
)
async def alltasks(interaction: discord.Interaction):
    session = get_session()
    try:
        tasks = session.query(Task).filter_by(completed=False).order_by(Task.due_date).all()
        
        if not tasks:
            await interaction.response.send_message("No pending tasks in the server! 🎉")
            return
            
        embed = discord.Embed(
            title="All Server Tasks",
            description="Here are all pending tasks:",
            color=discord.Color.blue()
        )
        
        # Group tasks by assigned user
        tasks_by_user = {}
        for task in tasks:
            user_id = task.assigned_to
            if user_id not in tasks_by_user:
                tasks_by_user[user_id] = []
            tasks_by_user[user_id].append(task)
        
        view = discord.ui.View(timeout=180)
        
        # Add tasks to embed
        for user_id, user_tasks in tasks_by_user.items():
            try:
                user = await client.fetch_user(int(user_id))
                if not user:
                    continue
                
                # Add user profile button
                view.add_item(UserButton(user))
                
                tasks_text = "\n".join([
                    f"• {task.name} (Due: {task.due_date.strftime('%Y-%m-%d %H:%M UTC')})"
                    for task in user_tasks
                ])
                
                embed.add_field(
                    name=f"Tasks for {user.display_name}",
                    value=tasks_text,
                    inline=False
                )
            except:
                continue
        
        await interaction.response.send_message(embed=embed, view=view)
        
    finally:
        session.close()

@client.tree.command(
    name="showtasks",
    description="View tasks for a specific user"
)
@app_commands.describe(
    user="The user whose tasks you want to view"
)
async def showtasks(interaction: discord.Interaction, user: discord.Member):
    session = get_session()
    try:
        tasks = session.query(Task).filter_by(
            assigned_to=str(user.id),
            completed=False
        ).order_by(Task.due_date).all()
        
        if not tasks:
            await interaction.response.send_message(f"No pending tasks! 🎉")
            return
            
        embed = discord.Embed(
            title=f"Tasks",
            description="Here are the pending tasks:",
            color=discord.Color.blue()
        )
        
        for task in tasks:
            embed.add_field(
                name=task.name,
                value=f"Due: {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}\nDescription: {task.description}",
                inline=False
            )
        
        view = TaskView(tasks, show_complete=False, user=user)
        await interaction.response.send_message(embed=embed, view=view)
        
    finally:
        session.close()

# Keep the bot alive
keep_alive()

# Start the bot with the token
client.run(os.getenv('TOKEN')) 