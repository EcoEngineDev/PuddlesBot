import discord
from discord import app_commands
import requests
import functools
from typing import Callable, Any
import traceback
import random
import json
import os
import time
from collections import defaultdict

# Store reference to the client
_client = None

# Cooldown tracking for fortune cookie
fortune_cooldowns = defaultdict(float)

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
            # Get server's language preference
            import language
            server_lang = language.get_server_language(interaction.guild_id)
            
            # Get translated text
            title_text = language.get_text("quack_title", server_lang)
            footer_text = language.get_text("quack_footer", server_lang)
            
            embed = discord.Embed(
                title=title_text,
                color=discord.Color.yellow()
            )
            embed.set_image(url=data['url'])
            embed.set_footer(text=footer_text)
            await interaction.response.send_message(embed=embed)
        else:
            # Get server's language preference for error message
            import language
            server_lang = language.get_server_language(interaction.guild_id)
            error_text = language.get_text("quack_error", server_lang)
            
            await interaction.response.send_message(
                error_text,
                ephemeral=True
            )
    except Exception as e:
        print(f"Error in quack command: {str(e)}")
        print(traceback.format_exc())
        # Get server's language preference for error message
        import language
        server_lang = language.get_server_language(interaction.guild_id)
        general_error_text = language.get_text("quack_general_error", server_lang)
        
        await interaction.response.send_message(
            general_error_text,
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
            
            # Get user's language preference
            import language
            user_lang = language.get_server_language(interaction.guild_id)
            
            # Get translated text
            title_text = language.get_text("coinflip_title", user_lang)
            description_text = language.get_text("coinflip_description", user_lang, result=result.upper())
            result_text = language.get_text("coinflip_result", user_lang, result=result.upper())
            footer_text = language.get_text("coinflip_footer", user_lang, user_name=interaction.user.display_name)
            
            # Create embed with result
            embed = discord.Embed(
                title=title_text,
                description=description_text,
                color=color
            )
            
            embed.add_field(
                name="Result",
                value=f"{emoji} {result_text}",
                inline=False
            )
            
            embed.set_footer(text=footer_text)
            
            # Send the message with the coin image
            with open(image_path, 'rb') as image_file:
                discord_file = discord.File(image_file, filename=f"coin_{result.lower()}.png")
                embed.set_image(url=f"attachment://coin_{result.lower()}.png")
                await interaction.response.send_message(embed=embed, file=discord_file)
                
        except (FileNotFoundError, OSError) as file_error:
            print(f"File error in coinflip: {str(file_error)}")
            # Get user's language preference for fallback
            import language
            user_lang = language.get_server_language(interaction.guild_id)
            
            # Get translated text
            title_text = language.get_text("coinflip_title", user_lang)
            description_text = language.get_text("coinflip_description", user_lang, result=result.upper())
            result_text = language.get_text("coinflip_result", user_lang, result=result.upper())
            note_text = language.get_text("coinflip_images_unavailable", user_lang)
            footer_text = language.get_text("coinflip_footer", user_lang, user_name=interaction.user.display_name)
            
            # Fallback to text-only version
            embed = discord.Embed(
                title=title_text,
                description=description_text,
                color=color
            )
            
            embed.add_field(
                name="Result",
                value=f"{emoji} {result_text}",
                inline=False
            )
            
            embed.add_field(
                name="Note",
                value=note_text,
                inline=False
            )
            
            embed.set_footer(text=footer_text)
            await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        print(f"Error in coinflip command: {str(e)}")
        print(traceback.format_exc())
        # Get user's language preference for error message
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        error_text = language.get_text("coinflip_error", user_lang)
        
        await interaction.response.send_message(
            error_text,
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
            
            # Get server's language preference
            import language
            server_lang = language.get_server_language(interaction.guild_id)
            
            # Check if we got valid meme data and it's not NSFW
            if 'url' in data and 'title' in data and not data.get('nsfw', False):
                # Get translated text
                title_text = data.get('title', language.get_text("meme_title", server_lang))
                footer_text = language.get_text("meme_footer", server_lang)
                posted_by_text = language.get_text("meme_posted_by", server_lang)
                from_text = language.get_text("meme_from", server_lang)
                upvotes_text = language.get_text("meme_upvotes", server_lang)
                original_post_text = language.get_text("meme_original_post", server_lang)
                view_on_reddit_text = language.get_text("meme_view_on_reddit", server_lang)
                
                embed = discord.Embed(
                    title=title_text,
                    color=discord.Color.purple()
                )
                embed.set_image(url=data['url'])
                
                # Add meme information
                if 'author' in data:
                    embed.add_field(name=posted_by_text, value=f"u/{data['author']}", inline=True)
                if 'subreddit' in data:
                    embed.add_field(name=from_text, value=f"r/{data['subreddit']}", inline=True)
                if 'ups' in data:
                    embed.add_field(name=upvotes_text, value=f"{data['ups']:,}", inline=True)
                
                # Add post link if available
                if 'postLink' in data:
                    embed.add_field(name=original_post_text, value=f"[{view_on_reddit_text}]({data['postLink']})", inline=False)
                
                embed.set_footer(text=footer_text)
                await interaction.response.send_message(embed=embed)
            else:
                # Handle NSFW or invalid content
                if data.get('nsfw', False):
                    nsfw_title = language.get_text("meme_nsfw_filtered", server_lang)
                    nsfw_message = language.get_text("meme_nsfw_message", server_lang)
                    embed = discord.Embed(
                        title=nsfw_title,
                        description=nsfw_message,
                        color=discord.Color.orange()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                else:
                    raise Exception("Invalid meme data received")
        else:
            # API returned an error status
            service_unavailable_title = language.get_text("meme_service_unavailable", server_lang)
            service_error_message = language.get_text("meme_service_error", server_lang, status=response.status_code)
            embed = discord.Embed(
                title=service_unavailable_title,
                description=service_error_message,
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    except requests.exceptions.Timeout:
        # Get server's language preference for timeout error
        import language
        server_lang = language.get_server_language(interaction.guild_id)
        timeout_title = language.get_text("meme_timeout", server_lang)
        timeout_message = language.get_text("meme_timeout_message", server_lang)
        
        embed = discord.Embed(
            title=timeout_title,
            description=timeout_message,
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except requests.exceptions.RequestException as req_error:
        print(f"Request error in meme command: {str(req_error)}")
        # Get server's language preference for network error
        import language
        server_lang = language.get_server_language(interaction.guild_id)
        network_title = language.get_text("meme_network_error", server_lang)
        network_message = language.get_text("meme_network_message", server_lang)
        
        embed = discord.Embed(
            title=network_title,
            description=network_message,
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"Error in meme command: {str(e)}")
        print(traceback.format_exc())
        # Get server's language preference for unexpected error
        import language
        server_lang = language.get_server_language(interaction.guild_id)
        unexpected_title = language.get_text("meme_unexpected_error", server_lang)
        unexpected_message = language.get_text("meme_unexpected_message", server_lang)
        
        embed = discord.Embed(
            title=unexpected_title,
            description=unexpected_message,
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.command(
    name="fortunecookie",
    description="Get a random fortune from a fortune cookie! 🥠 (3 hour cooldown)"
)
@log_command
async def fortunecookie(interaction: discord.Interaction):
    """Get a random fortune from fortunes.txt file"""
    try:
        # Get server's language preference
        import language
        server_lang = language.get_server_language(interaction.guild_id)
        
        # Check cooldown (3 hours = 10800 seconds)
        user_id = interaction.user.id
        current_time = time.time()
        cooldown_duration = 10800  # 3 hours in seconds
        
        if user_id in fortune_cooldowns:
            time_left = fortune_cooldowns[user_id] - current_time
            if time_left > 0:
                hours = int(time_left // 3600)
                minutes = int((time_left % 3600) // 60)
                seconds = int(time_left % 60)
                
                if hours > 0:
                    time_str = f"{hours}h {minutes}m {seconds}s"
                elif minutes > 0:
                    time_str = f"{minutes}m {seconds}s"
                else:
                    time_str = f"{seconds}s"
                
                cooldown_text = language.get_text("cooldown_active", server_lang, time=time_str)
                await interaction.response.send_message(
                    cooldown_text,
                    ephemeral=True
                )
                return
        
        # Check if language-specific fortunes file exists, fallback to English
        fortunes_file = f'fortunes/fortunes-{server_lang}.txt'
        if not os.path.exists(fortunes_file):
            # Fallback to English if language-specific file doesn't exist
            fortunes_file = 'fortunes/fortunes-en.txt'
            if not os.path.exists(fortunes_file):
                # Final fallback to root fortunes.txt
                fortunes_file = 'fortunes.txt'
                if not os.path.exists(fortunes_file):
                    file_not_found_text = language.get_text("fortune_cookie_file_not_found", server_lang)
                    await interaction.response.send_message(
                        file_not_found_text,
                        ephemeral=True
                    )
                    return
        
        # Read fortunes from file
        try:
            with open(fortunes_file, 'r', encoding='utf-8') as file:
                fortunes = [line.strip() for line in file if line.strip()]
        except Exception as e:
            print(f"Error reading fortunes file {fortunes_file}: {str(e)}")
            read_error_text = language.get_text("fortune_cookie_read_error", server_lang)
            await interaction.response.send_message(
                read_error_text,
                ephemeral=True
            )
            return
        
        # Check if we have any fortunes
        if not fortunes:
            no_fortunes_text = language.get_text("fortune_cookie_no_fortunes", server_lang)
            await interaction.response.send_message(
                no_fortunes_text,
                ephemeral=True
            )
            return
        
        # Select a random fortune
        random_fortune = random.choice(fortunes)
        
        # Set cooldown
        fortune_cooldowns[user_id] = current_time + cooldown_duration
        
        # Create embed for the fortune
        # Get translated text
        title_text = language.get_text("fortune_cookie_title", server_lang)
        footer_text = language.get_text("fortune_cookie_footer", server_lang, user_name=interaction.user.display_name)
        
        embed = discord.Embed(
            title=title_text,
            description=f"**{random_fortune}**",
            color=discord.Color.orange()
        )
        embed.set_footer(text=footer_text)
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        print(f"Error in fortunecookie command: {str(e)}")
        print(traceback.format_exc())
        # Get server's language preference for error message
        import language
        server_lang = language.get_server_language(interaction.guild_id)
        error_text = language.get_text("fortune_cookie_error", server_lang)
        
        await interaction.response.send_message(
            error_text,
            ephemeral=True
        )

def setup_fun_commands(tree):
    """Add fun commands to the command tree"""
    # Import language system
    import language
    
    # Register commands for localization
    language.register_command("quack", quack, "quack", "Get a random duck image! 🦆")
    language.register_command("coinflip", coinflip, "coinflip", "Flip a coin! Heads or Tails? 🪙")
    language.register_command("meme", meme, "meme", "Get a random meme to brighten your day! 😂")
    language.register_command("fortunecookie", fortunecookie, "fortunecookie", "Get a random fortune from a fortune cookie! 🥠 (3 hour cooldown)")
    
    # Add commands to tree
    tree.add_command(quack)
    tree.add_command(coinflip)
    tree.add_command(meme)
    tree.add_command(fortunecookie)
    print("✅ Fun commands loaded: /quack, /coinflip, /meme, /fortunecookie") 