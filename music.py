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

# Update music settings BEFORE importing music system components
try:
    from music_config import update_music_settings, validate_music_config
    if validate_music_config():
        update_music_settings()
        print("✅ Music settings updated successfully")
    else:
        print("❌ Music configuration validation failed")
except Exception as e:
    print(f"❌ Failed to update music settings: {e}")

# Add MusicSystem to the path so we can import from it
sys.path.append(os.path.join(os.path.dirname(__file__), 'MusicSystem'))

try:
    import function as music_func
    from addons import Settings
    import voicelink
except ImportError as e:
    print(f"Warning: Could not import music system components: {e}")
    music_func = None
    Settings = None
    voicelink = None

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
            settings_path = os.path.join(os.path.dirname(__file__), 'MusicSystem', 'settings.json')
            if os.path.exists(settings_path):
                # Load settings directly using the path - open_json looks relative to ROOT_DIR
                music_settings = Settings(music_func.open_json("settings.json"))
                music_func.settings = music_settings
                print("✅ Music system settings loaded successfully")
            else:
                print("❌ Music system settings.json not found")
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
        
        # Initialize Voicelink for music playback
        if voicelink and hasattr(music_settings, 'nodes'):
            try:
                # Create nodes from settings
                nodes = []
                for node_name, node_config in music_settings.nodes.items():
                    node = voicelink.Node(
                        host=node_config['host'],
                        port=node_config['port'],
                        password=node_config['password'],
                        secure=node_config.get('secure', False),
                        identifier=node_config.get('identifier', node_name)
                    )
                    nodes.append(node)
                
                # Create node pool with the client
                await voicelink.NodePool.create_pool(client, nodes)
                
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
    if not music_func or not voicelink:
        return
    
    @tree.command(name="play", description="Play music from various sources (YouTube, Spotify, etc.)")
    @app_commands.describe(query="Song name, URL, or search query")
    async def play(interaction: discord.Interaction, query: str):
        """Play music command"""
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ You need to be in a voice channel to use music commands!", ephemeral=True)
        
        # Connect to voice channel if not already connected
        if not interaction.guild.voice_client:
            try:
                await interaction.user.voice.channel.connect(cls=voicelink.Player)
            except Exception as e:
                return await interaction.response.send_message(f"❌ Failed to connect to voice channel: {e}", ephemeral=True)
        
        player = interaction.guild.voice_client
        
        await interaction.response.defer()
        
        try:
            # Search for tracks using Voicelink
            tracks = await voicelink.NodePool.get_node().get_tracks(query, requester=interaction.user)
            
            if not tracks:
                return await interaction.followup.send("❌ No tracks found for your query!")
            
            if isinstance(tracks, voicelink.Playlist):
                # Handle playlist
                for track in tracks.tracks:
                    player.queue.append(track)
                await interaction.followup.send(f"✅ Added playlist **{tracks.name}** with {len(tracks.tracks)} tracks to the queue!")
            else:
                # Handle single track or search results
                track = tracks[0]
                player.queue.append(track)
                await interaction.followup.send(f"✅ Added **{track.title}** to the queue!")
            
            # Start playing if not already playing
            if not player.is_playing() and not player.is_paused():
                await player.play(player.queue.get())
                
        except Exception as e:
            await interaction.followup.send(f"❌ An error occurred: {e}")
    
    @tree.command(name="skip", description="Skip the current song")
    async def skip(interaction: discord.Interaction):
        """Skip the current song"""
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        player = interaction.guild.voice_client
        
        if not player.is_playing():
            return await interaction.response.send_message("❌ No music is currently playing!", ephemeral=True)
        
        await player.skip()
        await interaction.response.send_message("⏭️ Skipped the current song!")
    
    @tree.command(name="stop", description="Stop music and disconnect from voice channel")
    async def stop(interaction: discord.Interaction):
        """Stop music and disconnect"""
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        player = interaction.guild.voice_client
        await player.disconnect()
        await interaction.response.send_message("⏹️ Stopped music and disconnected from voice channel!")
    
    @tree.command(name="pause", description="Pause the current song")
    async def pause(interaction: discord.Interaction):
        """Pause the current song"""
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        player = interaction.guild.voice_client
        
        if not player.is_playing():
            return await interaction.response.send_message("❌ No music is currently playing!", ephemeral=True)
        
        if player.is_paused():
            return await interaction.response.send_message("❌ Music is already paused!", ephemeral=True)
        
        await player.pause()
        await interaction.response.send_message("⏸️ Paused the current song!")
    
    @tree.command(name="resume", description="Resume the paused song")
    async def resume(interaction: discord.Interaction):
        """Resume the paused song"""
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        player = interaction.guild.voice_client
        
        if not player.is_paused():
            return await interaction.response.send_message("❌ Music is not paused!", ephemeral=True)
        
        await player.resume()
        await interaction.response.send_message("▶️ Resumed the current song!")
    
    @tree.command(name="queue", description="Show the current music queue")
    async def queue(interaction: discord.Interaction):
        """Show the current queue"""
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        player = interaction.guild.voice_client
        
        if player.queue.empty():
            return await interaction.response.send_message("❌ The queue is empty!", ephemeral=True)
        
        embed = discord.Embed(title="🎵 Music Queue", color=0x00ff00)
        
        if player.current:
            embed.add_field(name="🎵 Now Playing", value=f"**{player.current.title}**", inline=False)
        
        queue_list = []
        for i, track in enumerate(list(player.queue)[:10], 1):  # Show first 10 tracks
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
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        if not 0 <= volume <= 100:
            return await interaction.response.send_message("❌ Volume must be between 0 and 100!", ephemeral=True)
        
        player = interaction.guild.voice_client
        await player.set_volume(volume)
        await interaction.response.send_message(f"🔊 Set volume to {volume}%!")
    
    @tree.command(name="nowplaying", description="Show information about the currently playing song")
    async def nowplaying(interaction: discord.Interaction):
        """Show now playing information"""
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Bot is not connected to a voice channel!", ephemeral=True)
        
        player = interaction.guild.voice_client
        
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