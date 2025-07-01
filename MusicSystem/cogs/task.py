# Minimal task.py cog for Vocard compatibility
from discord.ext import commands

class Task(commands.Cog):
    """Minimal task cog - background tasks disabled in compatibility mode"""
    
    def __init__(self, bot):
        self.bot = bot
        print("⚠️ Music background tasks disabled (compatibility mode)")

async def setup(bot):
    await bot.add_cog(Task(bot)) 