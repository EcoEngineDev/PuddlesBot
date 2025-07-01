"""
Music System Integration Module for PuddlesBot
Integrates the Vocard music system with the existing bot architecture
"""

import discord
from discord import app_commands
import os
import sys
import asyncio
import logging
from typing import Optional

# Add MusicSystem to the path so we can import from it
sys.path.append(os.path.join(os.path.dirname(__file__), 'MusicSystem'))

try:
    import lavaplay
    import function as music_func
    from addons import Settings
    from MusicSystem.main import Vocard
except ImportError as e:
    print(f"Warning: Could not import music system components: {e}")
    lavaplay = None
    music_func = None
    Settings = None
    Vocard = None

# Global variables for the music system
music_client = None
music_settings = None

def setup_music_system(client):
    """Initialize the music system with the main bot client"""
    global music_client, music_settings
    music_client = client
    
    # Initialize music system settings
    if music_func and Settings:
        try:
            # Update settings with environment variables
            from music_config import update_music_settings, validate_music_config
            
            if validate_music_config():
                update_music_settings()
                
                settings_path = os.path.join(os.path.dirname(__file__), 'MusicSystem', 'settings.json')
                if os.path.exists(settings_path):
                    music_settings = Settings(music_func.open_json("MusicSystem/settings.json"))
                    music_func.settings = music_settings
                    print("✅ Music system settings loaded successfully")
                else:
                    print("❌ Music system settings.json not found")
            else:
                print("❌ Music system configuration validation failed")
        except Exception as e:
            print(f"❌ Failed to load music system settings: {e}")

async def initialize_music_components(client):
    """Initialize the music system components after the bot is ready"""
    global music_settings
    
    if not music_func or not music_settings:
        print("❌ Music system not properly initialized")
        return False
    
    try:
        # Set up language system
        music_func.langs_setup()
        
        # Connect to MongoDB if configured
        if hasattr(music_settings, 'mongodb_url') and hasattr(music_settings, 'mongodb_name'):
            if music_settings.mongodb_url and music_settings.mongodb_name:
                try:
                    from motor.motor_asyncio import AsyncIOMotorClient
                    music_func.MONGO_DB = AsyncIOMotorClient(host=music_settings.mongodb_url)
                    await music_func.MONGO_DB.server_info()
                    music_func.SETTINGS_DB = music_func.MONGO_DB[music_settings.mongodb_name]["Settings"]
                    music_func.USERS_DB = music_func.MONGO_DB[music_settings.mongodb_name]["Users"]
                    print("✅ Music system MongoDB connected")
                except Exception as e:
                    print(f"⚠️ MongoDB connection failed, music system will work without database: {e}")
        
        # Initialize Lavaplay for music playback
        if lavaplay and hasattr(music_settings, 'nodes'):
            try:
                # Create lavaplay client
                lavalink_client = lavaplay.Lavalink()
                
                # Add nodes from settings
                for node_name, node_config in music_settings.nodes.items():
                    node = lavalink_client.create_node(
                        host=node_config['host'],
                        port=node_config['port'],
                        password=node_config['password'],
                        user_id=client.user.id,
                        secure=node_config.get('secure', False),
                        identifier=node_config.get('identifier', node_name)
                    )
                    await node.connect()
                
                # Store the lavalink client globally for use in commands
                global lavalink_client
                music_func.lavalink_client = lavalink_client
                
                print("✅ Music system Lavalink nodes connected successfully")
                return True
            except Exception as e:
                print(f"❌ Failed to connect to Lavalink nodes: {e}")
                return False
    except Exception as e:
        print(f"❌ Failed to initialize music components: {e}")
        return False
    
    return False

def setup_music_commands(tree):
    """Set up music commands in the command tree"""
    if not music_func or not lavaplay:
        return
    
    @tree.command(name="play", description="Play music from various sources (YouTube, Spotify, etc.)")
    @app_commands.describe(query="Song name, URL, or search query")
    async def play(interaction: discord.Interaction, query: str):
        """Play music command"""
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ You need to be in a voice channel to use music commands!", ephemeral=True)
        
        # Get lavalink client
        lavalink_client = getattr(music_func, 'lavalink_client', None)
        if not lavalink_client:
            return await interaction.response.send_message("❌ Music system not properly initialized!", ephemeral=True)
        
        # Get or create player
        player = lavalink_client.get_player(interaction.guild.id)
        
        # Connect to voice channel if not connected
        if not player.is_connected:
            try:
                await player.connect(interaction.user.voice.channel.id)
            except Exception as e:
                return await interaction.response.send_message(f"❌ Failed to connect to voice channel: {e}", ephemeral=True)
        
        await interaction.response.defer()
        
        try:
            # Search for tracks
            tracks = await player.auto_search_tracks(query)
            
            if not tracks:
                return await interaction.followup.send("❌ No tracks found for your query!")
            
            if hasattr(tracks, '__iter__') and len(tracks) > 1:
                # Handle multiple tracks/playlist
                for track in tracks:
                    player.queue.append(track)
                await interaction.followup.send(f"✅ Added {len(tracks)} tracks to the queue!")
            else:
                # Handle single track
                track = tracks[0] if hasattr(tracks, '__iter__') else tracks
                player.queue.append(track)
                await interaction.followup.send(f"✅ Added **{track.title}** to the queue!")
            
            # Start playing if not already playing
            if not player.is_playing:
                await player.play()
                
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {e}")
    
    @tree.command(name="skip", description="Skip the current song")
    async def skip(interaction: discord.Interaction):
        """Skip the current song"""
        lavalink_client = getattr(music_func, 'lavalink_client', None)
        if not lavalink_client:
            return await interaction.response.send_message("❌ Music system not properly initialized!", ephemeral=True)
        
        player = lavalink_client.get_player(interaction.guild.id)
        
        if not player.is_connected:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        if not player.is_playing:
            return await interaction.response.send_message("❌ No music is currently playing!", ephemeral=True)
        
        await player.skip()
        await interaction.response.send_message("⏭️ Skipped the current song!")
    
    @tree.command(name="stop", description="Stop music and disconnect from voice channel")
    async def stop(interaction: discord.Interaction):
        """Stop music and disconnect"""
        lavalink_client = getattr(music_func, 'lavalink_client', None)
        if not lavalink_client:
            return await interaction.response.send_message("❌ Music system not properly initialized!", ephemeral=True)
        
        player = lavalink_client.get_player(interaction.guild.id)
        
        if not player.is_connected:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        await player.disconnect()
        await interaction.response.send_message("⏹️ Stopped music and disconnected from voice channel!")
    
    @tree.command(name="pause", description="Pause the current song")
    async def pause(interaction: discord.Interaction):
        """Pause the current song"""
        lavalink_client = getattr(music_func, 'lavalink_client', None)
        if not lavalink_client:
            return await interaction.response.send_message("❌ Music system not properly initialized!", ephemeral=True)
        
        player = lavalink_client.get_player(interaction.guild.id)
        
        if not player.is_connected:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        if not player.is_playing:
            return await interaction.response.send_message("❌ No music is currently playing!", ephemeral=True)
        
        if player.is_paused:
            return await interaction.response.send_message("❌ Music is already paused!", ephemeral=True)
        
        await player.pause(True)
        await interaction.response.send_message("⏸️ Paused the current song!")
    
    @tree.command(name="resume", description="Resume the paused song")
    async def resume(interaction: discord.Interaction):
        """Resume the paused song"""
        lavalink_client = getattr(music_func, 'lavalink_client', None)
        if not lavalink_client:
            return await interaction.response.send_message("❌ Music system not properly initialized!", ephemeral=True)
        
        player = lavalink_client.get_player(interaction.guild.id)
        
        if not player.is_connected:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        if not player.is_paused:
            return await interaction.response.send_message("❌ Music is not paused!", ephemeral=True)
        
        await player.pause(False)
        await interaction.response.send_message("▶️ Resumed the current song!")
    
    @tree.command(name="queue", description="Show the current music queue")
    async def queue(interaction: discord.Interaction):
        """Show the current queue"""
        lavalink_client = getattr(music_func, 'lavalink_client', None)
        if not lavalink_client:
            return await interaction.response.send_message("❌ Music system not properly initialized!", ephemeral=True)
        
        player = lavalink_client.get_player(interaction.guild.id)
        
        if not player.is_connected:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        if not player.queue:
            return await interaction.response.send_message("❌ The queue is empty!", ephemeral=True)
        
        embed = discord.Embed(title="🎵 Music Queue", color=0x00ff00)
        
        if player.current:
            embed.add_field(name="🎵 Now Playing", value=f"**{player.current.title}**", inline=False)
        
        queue_list = []
        for i, track in enumerate(player.queue[:10], 1):  # Show first 10 tracks
            queue_list.append(f"{i}. **{track.title}**")
        
        if queue_list:
            embed.add_field(name="📋 Up Next", value="\n".join(queue_list), inline=False)
        
        if len(player.queue) > 10:
            embed.add_field(name="", value=f"... and {len(player.queue) - 10} more tracks", inline=False)
        
        await interaction.response.send_message(embed=embed)
    
    @tree.command(name="volume", description="Set the music volume (0-100)")
    @app_commands.describe(volume="Volume level (0-100)")
    async def volume(interaction: discord.Interaction, volume: int):
        """Set the music volume"""
        lavalink_client = getattr(music_func, 'lavalink_client', None)
        if not lavalink_client:
            return await interaction.response.send_message("❌ Music system not properly initialized!", ephemeral=True)
        
        player = lavalink_client.get_player(interaction.guild.id)
        
        if not player.is_connected:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        if not 0 <= volume <= 100:
            return await interaction.response.send_message("❌ Volume must be between 0 and 100!", ephemeral=True)
        
        await player.volume(volume)
        await interaction.response.send_message(f"🔊 Set volume to {volume}%!")
    
    @tree.command(name="nowplaying", description="Show information about the currently playing song")
    async def nowplaying(interaction: discord.Interaction):
        """Show now playing information"""
        lavalink_client = getattr(music_func, 'lavalink_client', None)
        if not lavalink_client:
            return await interaction.response.send_message("❌ Music system not properly initialized!", ephemeral=True)
        
        player = lavalink_client.get_player(interaction.guild.id)
        
        if not player.is_connected:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        if not player.current:
            return await interaction.response.send_message("❌ No music is currently playing!", ephemeral=True)
        
        track = player.current
        embed = discord.Embed(title="🎵 Now Playing", color=0x00ff00)
        embed.add_field(name="Title", value=track.title, inline=False)
        
        # Format duration safely
        duration = getattr(track, 'duration', 0)
        if duration > 0:
            minutes = duration // 60000
            seconds = (duration // 1000) % 60
            embed.add_field(name="Duration", value=f"{minutes}:{seconds:02d}", inline=True)
        
        # Add requester if available
        requester = getattr(track, 'requester', None)
        if requester:
            embed.add_field(name="Requested by", value=requester.mention, inline=True)
        
        # Add thumbnail if available
        thumbnail = getattr(track, 'thumbnail', None) or getattr(track, 'artwork_url', None)
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        
        await interaction.response.send_message(embed=embed)

async def on_music_ready():
    """Called when the music system is ready"""
    if music_client:
        await initialize_music_components(music_client)

# Event handlers for voice states
async def on_voice_state_update(member, before, after):
    """Handle voice state updates for the music system"""
    if member.bot:
        return
    
    # Add any music-specific voice state handling here
    pass 