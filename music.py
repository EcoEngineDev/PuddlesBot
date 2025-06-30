import discord
from discord import app_commands
import lavalink
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import asyncio
import functools
import traceback
import logging
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
import os

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('MusicSystem')

# Store reference to the client and lavalink client
_client = None
_lavalink = None

# Spotify configuration
spotify = None
if os.getenv('SPOTIFY_CLIENT_ID') and os.getenv('SPOTIFY_CLIENT_SECRET'):
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=os.getenv('SPOTIFY_CLIENT_ID'),
            client_secret=os.getenv('SPOTIFY_CLIENT_SECRET')
        ))
        logger.info("✅ Spotify integration configured")
    except Exception as e:
        logger.error(f"❌ Spotify configuration failed: {e}")
        spotify = None
else:
    logger.warning("⚠️ Spotify credentials not found. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables.")

def setup_music_system(client):
    """Initialize the music system with Lavalink"""
    global _client, _lavalink
    _client = client
    
    # Initialize Lavalink
    _lavalink = lavalink.Client(client.user.id)
    
    # Add a default node (you can modify these settings)
    _lavalink.add_node(
        host='localhost',  # Change this to your Lavalink server host
        port=2333,         # Change this to your Lavalink server port
        password='youshallnotpass',  # Change this to match your application.yml
        region='us',       # Region identifier
        name='default-node'  # Node name
    )
    
    # Hook the track events
    _lavalink.add_event_hook(track_hook)
    
    logger.info("🎵 Lavalink music system initialized")
    return _lavalink

def log_command(func):
    """Decorator to log command usage"""
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        try:
            logger.info(f"🎵 Music command: {func.__name__} by {interaction.user.name}")
            return await func(interaction, *args, **kwargs)
        except Exception as e:
            logger.error(f"❌ Error in {func.__name__}: {e}")
            logger.error(traceback.format_exc())
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ An error occurred: {str(e)}", ephemeral=True)
            raise
    return wrapper

async def track_hook(event):
    """Handle Lavalink track events"""
    if isinstance(event, lavalink.events.QueueEndEvent):
        # Queue finished, disconnect after 5 minutes
        guild_id = event.player.guild_id
        logger.info(f"Queue ended for guild {guild_id}, starting auto-disconnect timer")
        
        async def auto_disconnect():
            await asyncio.sleep(300)  # 5 minutes
            player = _lavalink.player_manager.get(guild_id)
            if player and not player.is_playing:
                await player.disconnect()
                logger.info(f"Auto-disconnected from guild {guild_id}")
        
        asyncio.create_task(auto_disconnect())
    
    elif isinstance(event, lavalink.events.TrackStartEvent):
        logger.info(f"Track started: {event.track.title} in guild {event.player.guild_id}")
    
    elif isinstance(event, lavalink.events.TrackEndEvent):
        logger.info(f"Track ended: {event.track.title} in guild {event.player.guild_id}")

async def ensure_voice(interaction: discord.Interaction) -> bool:
    """Ensure the bot is connected to a voice channel"""
    player = _lavalink.player_manager.create(interaction.guild.id)
    
    # Check if user is in voice
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ You need to be in a voice channel!", ephemeral=True)
        return False
    
    # Connect to voice if not already connected
    if not player.is_connected:
        permissions = interaction.user.voice.channel.permissions_for(interaction.guild.me)
        if not permissions.connect or not permissions.speak:
            await interaction.response.send_message("❌ I need Connect and Speak permissions!", ephemeral=True)
            return False
        
        player.store('channel', interaction.channel.id)
        await player.connect(interaction.user.voice.channel.id)
        logger.info(f"Connected to voice channel: {interaction.user.voice.channel.name}")
    
    return True

async def search_spotify_track(spotify_url: str) -> Optional[Dict]:
    """Extract track info from Spotify URL"""
    if not spotify:
        return None
    
    try:
        # Extract track ID from URL
        track_match = re.search(r'track/([a-zA-Z0-9]+)', spotify_url)
        if track_match:
            track_id = track_match.group(1)
            track = spotify.track(track_id)
            
            return {
                'title': track['name'],
                'artist': ', '.join([artist['name'] for artist in track['artists']]),
                'duration': track['duration_ms'] // 1000,
                'query': f"{track['name']} {track['artists'][0]['name']}"
            }
    except Exception as e:
        logger.error(f"Spotify track search error: {e}")
    
    return None

def format_duration(milliseconds: int) -> str:
    """Format duration from milliseconds to MM:SS"""
    seconds = milliseconds // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}:{seconds:02d}"

@app_commands.command(name="play", description="Play a song or add to queue")
@app_commands.describe(query="Song name, YouTube URL, or Spotify URL")
@log_command
async def play(interaction: discord.Interaction, query: str):
    """Play a song or add it to the queue"""
    await interaction.response.defer()
    
    if not await ensure_voice(interaction):
        return
    
    player = _lavalink.player_manager.get(interaction.guild.id)
    
    try:
        # Handle Spotify URLs
        if 'spotify.com' in query and 'track/' in query:
            spotify_track = await search_spotify_track(query)
            if spotify_track:
                query = f"ytsearch:{spotify_track['query']}"
                embed = discord.Embed(
                    title="🎵 Searching from Spotify",
                    description=f"**{spotify_track['title']}** by {spotify_track['artist']}",
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("❌ Failed to get Spotify track info")
                return
        
        # Handle YouTube URLs or search
        if not query.startswith('http'):
            query = f'ytsearch:{query}'
        
        # Search for tracks
        results = await _lavalink.get_tracks(query)
        
        if not results or not results.tracks:
            await interaction.followup.send("❌ No tracks found!")
            return
        
        # Add track to queue
        track = results.tracks[0]
        player.add(requester=interaction.user.id, track=track)
        
        # Create embed
        embed = discord.Embed(color=discord.Color.green())
        
        if player.is_playing:
            embed.title = "🎵 Added to Queue"
            embed.description = f"**[{track.title}]({track.uri})**"
            embed.add_field(name="Duration", value=format_duration(track.duration), inline=True)
            embed.add_field(name="Position in Queue", value=str(len(player.queue)), inline=True)
        else:
            embed.title = "🎵 Now Playing"
            embed.description = f"**[{track.title}]({track.uri})**"
            embed.add_field(name="Duration", value=format_duration(track.duration), inline=True)
            await player.play()
        
        embed.add_field(name="Requested by", value=interaction.user.mention, inline=True)
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        logger.error(f"Play command error: {e}")
        await interaction.followup.send(f"❌ Error playing track: {str(e)}")

@app_commands.command(name="pause", description="Pause the current song")
@log_command
async def pause(interaction: discord.Interaction):
    """Pause the current song"""
    player = _lavalink.player_manager.get(interaction.guild.id)
    
    if not player or not player.is_playing:
        await interaction.response.send_message("❌ Nothing is currently playing!", ephemeral=True)
        return
    
    if player.paused:
        await interaction.response.send_message("❌ Music is already paused!", ephemeral=True)
        return
    
    await player.set_pause(True)
    await interaction.response.send_message("⏸️ Music paused!")

@app_commands.command(name="resume", description="Resume the paused song")
@log_command
async def resume(interaction: discord.Interaction):
    """Resume the paused song"""
    player = _lavalink.player_manager.get(interaction.guild.id)
    
    if not player or not player.is_playing:
        await interaction.response.send_message("❌ Nothing is currently playing!", ephemeral=True)
        return
    
    if not player.paused:
        await interaction.response.send_message("❌ Music is not paused!", ephemeral=True)
        return
    
    await player.set_pause(False)
    await interaction.response.send_message("▶️ Music resumed!")

@app_commands.command(name="skip", description="Skip the current song")
@log_command
async def skip(interaction: discord.Interaction):
    """Skip the current song"""
    player = _lavalink.player_manager.get(interaction.guild.id)
    
    if not player or not player.is_playing:
        await interaction.response.send_message("❌ Nothing is currently playing!", ephemeral=True)
        return
    
    await player.skip()
    await interaction.response.send_message("⏭️ Skipped!")

@app_commands.command(name="stop", description="Stop music and clear queue")
@log_command
async def stop(interaction: discord.Interaction):
    """Stop music and clear queue"""
    player = _lavalink.player_manager.get(interaction.guild.id)
    
    if not player:
        await interaction.response.send_message("❌ No player found!", ephemeral=True)
        return
    
    player.queue.clear()
    await player.stop()
    await interaction.response.send_message("⏹️ Music stopped and queue cleared!")

@app_commands.command(name="disconnect", description="Disconnect from voice channel")
@log_command
async def disconnect(interaction: discord.Interaction):
    """Disconnect from voice channel"""
    player = _lavalink.player_manager.get(interaction.guild.id)
    
    if not player or not player.is_connected:
        await interaction.response.send_message("❌ Not connected to a voice channel!", ephemeral=True)
        return
    
    player.queue.clear()
    await player.disconnect()
    await interaction.response.send_message("👋 Disconnected from voice channel!")

@app_commands.command(name="musicstatus", description="Check music system status (Admin only)")
@app_commands.default_permissions(administrator=True)
@log_command
async def musicstatus(interaction: discord.Interaction):
    """Check music system status"""
    embed = discord.Embed(
        title="🎵 Music System Status",
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    # Lavalink status
    node_count = len(_lavalink.node_manager.nodes)
    available_nodes = len([n for n in _lavalink.node_manager.nodes if n.available])
    
    embed.add_field(
        name="🌐 Lavalink Nodes",
        value=f"Total: {node_count}\nAvailable: {available_nodes}",
        inline=True
    )
    
    # Player status
    active_players = len(_lavalink.player_manager.players)
    playing_players = len([p for p in _lavalink.player_manager.players.values() if p.is_playing])
    
    embed.add_field(
        name="🎵 Players",
        value=f"Active: {active_players}\nPlaying: {playing_players}",
        inline=True
    )
    
    # Spotify status
    spotify_status = "✅ Configured" if spotify else "❌ Not configured"
    embed.add_field(name="🎧 Spotify", value=spotify_status, inline=True)
    
    # Node details
    if _lavalink.node_manager.nodes:
        node_info = []
        for node in _lavalink.node_manager.nodes:
            status = "🟢 Online" if node.available else "🔴 Offline"
            node_info.append(f"{status} {node.name} ({node.region})")
        
        embed.add_field(name="📡 Node Details", value="\n".join(node_info), inline=False)
    else:
        embed.add_field(name="⚠️ Setup Required", value="No Lavalink nodes configured! See setup instructions.", inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

def setup_music_commands(tree):
    """Add music commands to the command tree"""
    tree.add_command(play)
    tree.add_command(pause)
    tree.add_command(resume)
    tree.add_command(skip)
    tree.add_command(stop)
    tree.add_command(disconnect)
    tree.add_command(musicstatus)
    
    print("🎵 Lavalink music commands loaded: /play, /pause, /resume, /skip, /stop, /disconnect, /musicstatus")

# Cleanup function
async def cleanup_music_players():
    """Clean up inactive music players"""
    if _lavalink:
        for player in list(_lavalink.player_manager.players.values()):
            if not player.is_connected:
                await player.disconnect() 