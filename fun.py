import discord
from discord import app_commands
import requests
import functools
from typing import Callable, Any
import traceback
import random
import json
import os

# Store reference to the client
_client = None

def setup_fun_system(client):
    """Initialize the fun system with client reference"""
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
                    f"An error occurred while executing the command: {str(e)}",
                    ephemeral=True
                )
            raise
    return wrapper

@app_commands.command(
    name="quack",
    description="Get a random duck image! 🦆"
)
@log_command
async def quack(interaction: discord.Interaction):
    """Get a random duck image from random-d.uk API"""
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

@app_commands.command(
    name="coinflip",
    description="Flip a coin! Heads or Tails? 🪙"
)
@log_command
async def coinflip(interaction: discord.Interaction):
    """Flip a coin and get heads or tails with actual coin images"""
    try:
        # Generate random result
        result = random.choice(['Heads', 'Tails'])
        
        # Get the appropriate folder path
        if result == 'Heads':
            folder_path = 'Media/coinflip/head'
            emoji = '🟡'
            color = discord.Color.gold()
        else:
            folder_path = 'Media/coinflip/tail'
            emoji = '⚪'
            color = discord.Color.from_rgb(192, 192, 192)  # Silver color for tails
        
        # Get all PNG files from the appropriate folder
        try:
            image_files = [f for f in os.listdir(folder_path) if f.lower().endswith('.png')]
            
            if not image_files:
                # Fallback if no images found
                raise FileNotFoundError(f"No images found in {folder_path}")
            
            # Select a random image
            random_image = random.choice(image_files)
            image_path = os.path.join(folder_path, random_image)
            
            # Create embed with result
            embed = discord.Embed(
                title="🪙 Coin Flip Result",
                description=f"🪙 ← **The coin landed on {result.upper()}!**",
                color=color
            )
            
            embed.add_field(
                name="Result",
                value=f"{emoji} **{result.upper()}!**",
                inline=False
            )
            
            embed.set_footer(text=f"Flipped by {interaction.user.display_name}")
            
            # Send the message with the coin image
            with open(image_path, 'rb') as image_file:
                discord_file = discord.File(image_file, filename=f"coin_{result.lower()}.png")
                embed.set_image(url=f"attachment://coin_{result.lower()}.png")
                await interaction.response.send_message(embed=embed, file=discord_file)
                
        except (FileNotFoundError, OSError) as file_error:
            print(f"File error in coinflip: {str(file_error)}")
            # Fallback to text-only version
            embed = discord.Embed(
                title="🪙 Coin Flip Result",
                description=f"🪙 ← **The coin landed on {result.upper()}!**",
                color=color
            )
            
            embed.add_field(
                name="Result",
                value=f"{emoji} **{result.upper()}!**",
                inline=False
            )
            
            embed.add_field(
                name="Note",
                value="🖼️ Coin images temporarily unavailable",
                inline=False
            )
            
            embed.set_footer(text=f"Flipped by {interaction.user.display_name}")
            await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        print(f"Error in coinflip command: {str(e)}")
        print(traceback.format_exc())
        await interaction.response.send_message(
            "An error occurred while flipping the coin. Please try again!",
            ephemeral=True
        )

@app_commands.command(
    name="meme",
    description="Get a random meme to brighten your day! 😂"
)
@log_command
async def meme(interaction: discord.Interaction):
    """Get a random meme from meme-api.com"""
    try:
        # Use the reliable meme-api.com service
        api_url = 'https://meme-api.com/gimme'
        
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Check if we got valid meme data and it's not NSFW
            if 'url' in data and 'title' in data and not data.get('nsfw', False):
                embed = discord.Embed(
                    title=data.get('title', 'Random Meme'),
                    color=discord.Color.purple()
                )
                embed.set_image(url=data['url'])
                
                # Add meme information
                if 'author' in data:
                    embed.add_field(name="📝 Posted by", value=f"u/{data['author']}", inline=True)
                if 'subreddit' in data:
                    embed.add_field(name="📍 From", value=f"r/{data['subreddit']}", inline=True)
                if 'ups' in data:
                    embed.add_field(name="⬆️ Upvotes", value=f"{data['ups']:,}", inline=True)
                
                # Add post link if available
                if 'postLink' in data:
                    embed.add_field(name="🔗 Original Post", value=f"[View on Reddit]({data['postLink']})", inline=False)
                
                embed.set_footer(text="😂 Enjoy your meme! • Powered by meme-api.com")
                await interaction.response.send_message(embed=embed)
            else:
                # Handle NSFW or invalid content
                if data.get('nsfw', False):
                    embed = discord.Embed(
                        title="🔞 NSFW Content Filtered",
                        description="Sorry, I found a meme but it's not suitable for all audiences. Try again for a different one!",
                        color=discord.Color.orange()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    raise Exception("Invalid meme data received")
        else:
            # API returned an error status
            embed = discord.Embed(
                title="😅 Meme Service Unavailable",
                description=f"Sorry, the meme service returned an error (Status: {response.status_code}). Try again in a moment!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    except requests.exceptions.Timeout:
        embed = discord.Embed(
            title="⏰ Request Timeout",
            description="The meme service is taking too long to respond. Please try again!",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except requests.exceptions.RequestException as req_error:
        print(f"Request error in meme command: {str(req_error)}")
        embed = discord.Embed(
            title="🌐 Network Error",
            description="Unable to connect to the meme service. Please check your internet connection and try again!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"Error in meme command: {str(e)}")
        print(traceback.format_exc())
        embed = discord.Embed(
            title="❌ Unexpected Error",
            description="An unexpected error occurred while fetching your meme. Please try again later!",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

def setup_fun_commands(tree):
    """Add fun commands to the command tree"""
    tree.add_command(quack)
    tree.add_command(coinflip)
    tree.add_command(meme)
    print("✅ Fun commands loaded: /quack, /coinflip, /meme") 