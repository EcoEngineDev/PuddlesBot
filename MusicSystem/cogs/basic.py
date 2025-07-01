# Minimal basic.py cog for Vocard compatibility
from discord.ext import commands

class Basic(commands.Cog):
    """Minimal basic cog - music commands disabled in compatibility mode"""
    
    def __init__(self, bot):
        self.bot = bot
        print("⚠️ Music commands disabled (compatibility mode)")
        print("💡 To enable music: Restore complete Vocard files")

async def setup(bot):
    await bot.add_cog(Basic(bot)) 