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
        # This is called when the bot starts
        print("Syncing commands...")
        # Sync commands with Discord
        await self.tree.sync()
        print("Commands synced!")
        
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

class TaskView(discord.ui.View):
    def __init__(self, tasks):
        super().__init__(timeout=180)
        self.tasks = tasks
        self.current_page = 0
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        if len(self.tasks) > 1:
            prev_button = discord.ui.Button(label="Previous", custom_id="prev", style=discord.ButtonStyle.secondary, disabled=self.current_page == 0)
            next_button = discord.ui.Button(label="Next", custom_id="next", style=discord.ButtonStyle.secondary, disabled=self.current_page == len(self.tasks) - 1)
            self.add_item(prev_button)
            self.add_item(next_button)
            prev_button.callback = lambda i: self.handle_button(i, "prev")
            next_button.callback = lambda i: self.handle_button(i, "next")

        details_button = discord.ui.Button(label="View Details", custom_id="details", style=discord.ButtonStyle.primary)
        complete_button = discord.ui.Button(label="Complete", custom_id="complete", style=discord.ButtonStyle.success)
        self.add_item(details_button)
        self.add_item(complete_button)
        details_button.callback = lambda i: self.handle_button(i, "details")
        complete_button.callback = lambda i: self.handle_button(i, "complete")

    async def handle_button(self, interaction: discord.Interaction, button_id: str):
        if button_id == "prev" and self.current_page > 0:
            self.current_page -= 1
        elif button_id == "next" and self.current_page < len(self.tasks) - 1:
            self.current_page += 1
        elif button_id == "details":
            task = self.tasks[self.current_page]
            embed = discord.Embed(
                title=f"Task Details: {task.name}",
                description=task.description,
                color=discord.Color.blue()
            )
            embed.add_field(name="Due Date", value=task.due_date.strftime('%Y-%m-%d %H:%M UTC'))
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        elif button_id == "complete":
            task = self.tasks[self.current_page]
            session = get_session()
            try:
                task_db = session.query(Task).filter_by(id=task.id).first()
                if task_db:
                    task_db.completed = True
                    session.commit()
                    self.tasks.pop(self.current_page)
                    if not self.tasks:
                        await interaction.message.delete()
                        await interaction.response.send_message("All tasks completed! 🎉", ephemeral=True)
                        return
                    if self.current_page >= len(self.tasks):
                        self.current_page = len(self.tasks) - 1
            finally:
                session.close()

        self.update_buttons()
        await self.update_message(interaction)

    async def update_message(self, interaction: discord.Interaction):
        task = self.tasks[self.current_page]
        embed = discord.Embed(
            title="Your Tasks",
            description=f"Task: {task.name}\nDue: {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Task {self.current_page + 1} of {len(self.tasks)}")
        await interaction.response.edit_message(embed=embed, view=self)

@client.tree.command(name="task", description="Create a new task")
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

@client.tree.command(name="mytasks", description="View your tasks")
async def mytasks(interaction: discord.Interaction):
    session = get_session()
    try:
        tasks = session.query(Task).filter_by(
            assigned_to=str(interaction.user.id),
            completed=False
        ).order_by(Task.due_date).all()
        
        if not tasks:
            await interaction.response.send_message("You have no pending tasks! 🎉", ephemeral=True)
            return
            
        embed = discord.Embed(
            title="Your Tasks",
            description=f"Task: {tasks[0].name}\nDue: {tasks[0].due_date.strftime('%Y-%m-%d %H:%M UTC')}",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Task 1 of {len(tasks)}")
        
        view = TaskView(tasks)
        await interaction.response.send_message(embed=embed, view=view)
        
    finally:
        session.close()

@client.tree.command(name="taskedit", description="Edit a task (Admin only)")
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

@client.tree.command(name="quack", description="Get a random duck image!")
async def quack(interaction: discord.Interaction):
    response = requests.get('https://random-d.uk/api/v2/random')
    if response.status_code == 200:
        duck_data = response.json()
        embed = discord.Embed(title="Quack! 🦆", color=discord.Color.yellow())
        embed.set_image(url=duck_data['url'])
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Sorry, couldn't fetch a duck right now! 😢")

# Keep the bot alive
keep_alive()

# Start the bot with the token
client.run(os.getenv('TOKEN')) 