import discord
from discord import app_commands
import random
import functools
from typing import Callable, Any
import traceback
import time
import asyncio
from collections import defaultdict

# Store reference to the client
_client = None

# Cooldown tracking
user_cooldowns = defaultdict(float)

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
        number_of_dice="Number of dice to roll (1-1,000,000,000)",
        sides="Number of sides on each die (2-100, default: 6)"
    )
    @log_command
    async def diceroll(interaction: discord.Interaction, number_of_dice: int, sides: int = 6):
        """Roll dice and display results visually"""
        
        # Get user's language preference
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        # Validate input
        if number_of_dice < 1:
            error_msg = language.get_text("dice_roll_min_error", user_lang)
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        if number_of_dice > 1000000000:
            error_msg = language.get_text("dice_roll_max_error", user_lang)
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        if sides < 2:
            error_msg = language.get_text("dice_sides_min_error", user_lang)
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        if sides > 100:
            error_msg = language.get_text("dice_sides_max_error", user_lang)
            await interaction.response.send_message(error_msg, ephemeral=True)
            return
        
        # Check cooldown for large rolls
        user_id = interaction.user.id
        current_time = time.time()
        
        if number_of_dice > 100:
            if user_id in user_cooldowns:
                time_left = user_cooldowns[user_id] - current_time
                if time_left > 0:
                    minutes = int(time_left // 60)
                    seconds = int(time_left % 60)
                    cooldown_msg = language.get_text("dice_roll_cooldown", user_lang, minutes=minutes, seconds=seconds)
                    await interaction.response.send_message(cooldown_msg, ephemeral=True)
                    return
            
            # Set cooldown for 2 minutes
            user_cooldowns[user_id] = current_time + 120
        
        try:
            # For very large numbers, defer the response to avoid timeout
            if number_of_dice > 10000:
                await interaction.response.defer()
            
            # Dice face emojis (only for 6-sided dice)
            dice_faces = {
                1: "⚀",
                2: "⚁", 
                3: "⚂",
                4: "⚃",
                5: "⚄",
                6: "⚅"
            }
            
            # For non-6-sided dice, use numbers
            def get_die_display(roll, die_sides):
                if die_sides == 6 and roll in dice_faces:
                    return dice_faces[roll]
                else:
                    return f"[{roll}]"
            
            # Ultra-optimized rolling system based on size
            if number_of_dice <= 1000:
                # For smaller numbers, generate all rolls for detailed analysis
                rolls = [random.randint(1, sides) for _ in range(number_of_dice)]
                total = sum(rolls)
                roll_counts = {i: rolls.count(i) for i in range(1, sides + 1)}
                highest = max(rolls) if rolls else 0
                lowest = min(rolls) if rolls else 0
                
            elif number_of_dice <= 1000000:
                # For medium numbers, use streaming approach
                roll_counts = {i: 0 for i in range(1, sides + 1)}
                total = 0
                highest = 0
                lowest = sides + 1
                sample_rolls = []
                
                # Process in chunks to avoid memory issues
                for i in range(number_of_dice):
                    roll = random.randint(1, sides)
                    roll_counts[roll] += 1
                    total += roll
                    
                    # Track extremes
                    if roll > highest:
                        highest = roll
                    if roll < lowest:
                        lowest = roll
                    
                    # Keep first 20 rolls for sample display
                    if i < 20:
                        sample_rolls.append(roll)
                    
                    # Yield control periodically for very large numbers
                    if i % 100000 == 0 and i > 0:
                        await asyncio.sleep(0.001)  # Prevent blocking
                
                rolls = sample_rolls  # Only keep sample for display
                
            else:
                # For massive numbers (>1M), use mathematical simulation
                # This is much faster than actually rolling each die
                
                # Theoretical distribution for fair dice
                expected_per_face = number_of_dice / sides
                
                # Add some realistic variance using binomial distribution approximation
                # For very large numbers, we can use normal approximation
                import math
                
                roll_counts = {}
                total = 0
                
                # Generate realistic counts with proper variance
                for face in range(1, sides + 1):
                    # Standard deviation for binomial distribution
                    std_dev = math.sqrt(number_of_dice * (1/sides) * ((sides-1)/sides))
                    
                    # Generate count with normal approximation
                    variance = random.gauss(0, std_dev)
                    count = int(expected_per_face + variance)
                    
                    # Ensure non-negative and reasonable bounds
                    count = max(0, min(count, number_of_dice))
                    roll_counts[face] = count
                    total += face * count
                
                # Adjust counts to exactly match number_of_dice
                current_total = sum(roll_counts.values())
                if current_total != number_of_dice:
                    # Distribute the difference
                    diff = number_of_dice - current_total
                    # Add/subtract from random faces
                    for _ in range(abs(diff)):
                        face = random.randint(1, sides)
                        if diff > 0:
                            roll_counts[face] += 1
                            total += face
                        else:
                            if roll_counts[face] > 0:
                                roll_counts[face] -= 1
                                total -= face
                
                # Generate sample rolls for display
                sample_rolls = [random.randint(1, sides) for _ in range(20)]
                rolls = sample_rolls
                
                # Set realistic extremes
                highest = sides
                lowest = 1
            
            # Create embed
            title_text = language.get_text("dice_roll_title", user_lang)
            embed = discord.Embed(
                title=f"{title_text} ({sides}-sided)",
                color=discord.Color.random()
            )
            
            # Handle display based on number of dice
            if number_of_dice <= 50:
                # Show visual dice for small numbers
                dice_visual = "  ".join([get_die_display(roll, sides) for roll in rolls])
                
                # Break into lines for better readability
                max_per_line = 20 if sides == 6 else 15  # Fewer per line for larger numbers
                if number_of_dice > max_per_line:
                    dice_lines = []
                    for i in range(0, len(rolls), max_per_line):
                        line_rolls = rolls[i:i+max_per_line]
                        line_visual = "  ".join([get_die_display(roll, sides) for roll in line_rolls])
                        dice_lines.append(line_visual)
                    dice_visual = "\n".join(dice_lines)
                
                embed.add_field(
                    name=f"Rolling {number_of_dice:,} {sides}-sided dice:",
                    value=f"```\n{dice_visual}\n```",
                    inline=False
                )
                
                # Show individual rolls for small numbers
                if number_of_dice <= 1000:
                    rolls_text = ', '.join(map(str, rolls))
                    if len(rolls_text) <= 1020:  # Leave some buffer for Discord's 1024 limit
                        embed.add_field(
                            name="Individual rolls:",
                            value=f"`{rolls_text}`",
                            inline=False
                        )
                
            else:
                # For large numbers, show summary statistics instead
                summary_lines = []
                for face in range(1, sides + 1):
                    count = roll_counts[face]
                    percentage = (count / number_of_dice) * 100
                    display = get_die_display(face, sides)
                    summary_lines.append(f"{display} **{count:,}** ({percentage:.2f}%)")
                
                # Split into columns if too many sides
                if sides > 20:
                    mid_point = (sides + 1) // 2
                    left_column = summary_lines[:mid_point]  
                    right_column = summary_lines[mid_point:]
                    
                    embed.add_field(
                        name=f"Rolling {number_of_dice:,} {sides}-sided dice - Summary (1-{mid_point}):",
                        value="\n".join(left_column),
                        inline=True
                    )
                    embed.add_field(
                        name=f"Summary ({mid_point + 1}-{sides}):",
                        value="\n".join(right_column),
                        inline=True
                    )
                else:
                    embed.add_field(
                        name=f"Rolling {number_of_dice:,} {sides}-sided dice - Summary:",
                        value="\n".join(summary_lines),
                        inline=False
                    )
                
                # Show a sample of the first 20 rolls
                sample_visual = "  ".join([get_die_display(roll, sides) for roll in rolls[:20]])
                embed.add_field(
                    name="Sample (first 20 rolls):",
                    value=f"```\n{sample_visual}\n```",
                    inline=False
                )
                
                # Add processing method info for very large numbers
                if number_of_dice > 1000000:
                    embed.add_field(
                        name="Processing Method:",
                        value="🧮 Mathematical simulation used for ultra-fast processing",
                        inline=False
                    )
            
            # Always show total and statistics
            embed.add_field(
                name="Total sum:",
                value=f"**{total:,}**",
                inline=True
            )
            
            # Add statistics for multiple dice
            if number_of_dice > 1:
                average = total / number_of_dice
                min_possible = number_of_dice
                max_possible = number_of_dice * sides
                
                # Format large numbers with appropriate units
                def format_large_number(num):
                    if num >= 1_000_000_000:
                        return f"{num / 1_000_000_000:.2f}B"
                    elif num >= 1_000_000:
                        return f"{num / 1_000_000:.2f}M"
                    elif num >= 1_000:
                        return f"{num / 1_000:.2f}K"
                    else:
                        return f"{num:,}"
                
                embed.add_field(
                    name="Statistics:",
                    value=f"Average: {average:.4f}\nRange: {format_large_number(min_possible)}-{format_large_number(max_possible)}",
                    inline=True
                )
                
                # Add highest and lowest rolls for larger sets
                if number_of_dice > 10:
                    embed.add_field(
                        name="Extremes:",
                        value=f"Highest: {highest}\nLowest: {lowest}",
                        inline=True
                    )
                
                # Add efficiency info for massive rolls
                if number_of_dice > 100000000:  # 100M+
                    embed.add_field(
                        name="Performance:",
                        value="⚡ Ultra-optimized for billion+ dice rolls",
                        inline=True
                    )
            
            # Add die type info
            die_type_emoji = {
                2: "🪙",  # Coin flip
                4: "🔷",  # Tetrahedron  
                6: "🎲",  # Standard die
                8: "🔶",  # Octahedron
                10: "🔟", # d10
                12: "🔸", # Dodecahedron
                20: "⭐"  # d20
            }
            
            die_emoji = die_type_emoji.get(sides, "🎯")
            embed.set_footer(text=f"{die_emoji} Rolled by {interaction.user.display_name}")
            
            # Send response (deferred or immediate)
            if number_of_dice > 10000:
                await interaction.followup.send(embed=embed)
            else:
                await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Error in diceroll command: {e}")
            error_msg = "❌ An error occurred while rolling dice!"
            if number_of_dice > 10000:
                await interaction.followup.send(error_msg, ephemeral=True)
            else:
                await interaction.response.send_message(error_msg, ephemeral=True) 