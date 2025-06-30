import discord
from discord import app_commands
import random
import functools
from typing import Callable, Any
import traceback

# Store reference to the client
_client = None

def setup_dice_system(client):
    """Initialize the dice system with client reference"""
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

def setup_dice_commands(tree: app_commands.CommandTree):
    """Setup dice rolling commands"""
    
    @tree.command(
        name="diceroll",
        description="Roll dice and see the results! 🎲"
    )
    @app_commands.describe(
        number_of_dice="Number of 6-sided dice to roll (1-100)"
    )
    @log_command
    async def diceroll(interaction: discord.Interaction, number_of_dice: int):
        """Roll dice and display results visually"""
        
        # Validate input
        if number_of_dice < 1:
            await interaction.response.send_message("❌ You need to roll at least 1 die!", ephemeral=True)
            return
        
        if number_of_dice > 100:
            await interaction.response.send_message("❌ Maximum 100 dice allowed!", ephemeral=True)
            return
        
        try:
            # Roll the dice
            rolls = [random.randint(1, 6) for _ in range(number_of_dice)]
            total = sum(rolls)
            
            # Dice face emojis
            dice_faces = {
                1: "⚀",
                2: "⚁", 
                3: "⚂",
                4: "⚃",
                5: "⚄",
                6: "⚅"
            }
            
            # Create visual representation with bigger spacing
            dice_visual = "  ".join([dice_faces[roll] for roll in rolls])
            
            # For many dice, break into lines of 20 for better readability
            if number_of_dice > 20:
                dice_lines = []
                for i in range(0, len(rolls), 20):
                    line_rolls = rolls[i:i+20]
                    line_visual = "  ".join([dice_faces[roll] for roll in line_rolls])
                    dice_lines.append(line_visual)
                dice_visual = "\n".join(dice_lines)
            
            # Create embed
            embed = discord.Embed(
                title="🎲 Dice Roll Results",
                color=discord.Color.random()
            )
            
            embed.add_field(
                name=f"Rolling {number_of_dice} dice:",
                value=f"```\n{dice_visual}\n```",
                inline=False
            )
            
            embed.add_field(
                name="Individual rolls:",
                value=f"`{', '.join(map(str, rolls))}`",
                inline=True
            )
            
            embed.add_field(
                name="Total sum:",
                value=f"**{total}**",
                inline=True
            )
            
            # Add some fun statistics for multiple dice
            if number_of_dice > 1:
                average = total / number_of_dice
                min_possible = number_of_dice
                max_possible = number_of_dice * 6
                
                embed.add_field(
                    name="Statistics:",
                    value=f"Average: {average:.1f}\nRange: {min_possible}-{max_possible}",
                    inline=True
                )
            
            embed.set_footer(text=f"Rolled by {interaction.user.display_name}")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Error in diceroll command: {e}")
            await interaction.response.send_message("❌ An error occurred while rolling dice!", ephemeral=True) 