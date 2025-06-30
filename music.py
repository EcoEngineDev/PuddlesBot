import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import yt_dlp
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import re
import functools
from typing import Optional, List, Dict, Any
import os
import tempfile
import aiofiles
from datetime import datetime, timedelta
import traceback
import json
import imageio_ffmpeg as ffmpeg

# Store references
_client = None
music_players = {}  # Guild ID -> MusicPlayer instance

# Spotify setup (you'll need to set these environment variables)
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')

# Initialize Spotify client if credentials are available
spotify = None
if SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET:
    try:
        spotify = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials(
            client_id=SPOTIFY_CLIENT_ID,
            client_secret=SPOTIFY_CLIENT_SECRET
        ))
    except Exception as e:
        print(f"Failed to initialize Spotify client: {e}")

def detect_hosting_environment():
    """Detect what kind of hosting environment we're running in"""
    indicators = []
    
    # Check for common hosting environment indicators
    try:
        import os
        
        # Replit
        if os.environ.get('REPL_ID') or os.environ.get('REPLIT_DB_URL'):
            indicators.append("Replit")
        
        # Heroku  
        if os.environ.get('DYNO') or os.environ.get('HEROKU_APP_NAME'):
            indicators.append("Heroku")
            
        # Railway
        if os.environ.get('RAILWAY_ENVIRONMENT'):
            indicators.append("Railway")
            
        # Glitch
        if os.environ.get('PROJECT_DOMAIN') and 'glitch' in os.environ.get('PROJECT_DOMAIN', ''):
            indicators.append("Glitch")
            
        # GitHub Codespaces
        if os.environ.get('CODESPACES'):
            indicators.append("GitHub Codespaces")
            
        # Check for container environment
        if os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER'):
            indicators.append("Docker Container")
            
        # Check if we're in a restricted environment
        if not os.access('/usr', os.W_OK):
            indicators.append("Restricted Environment")
            
        return indicators if indicators else ["Unknown/Local"]
        
    except Exception:
        return ["Detection Failed"]

def setup_music_system(client):
    """Initialize the music system with client reference"""
    global _client
    _client = client
    
    # Detect hosting environment
    env_info = detect_hosting_environment()
    print(f"🏠 Detected hosting environment: {', '.join(env_info)}")
    
    # Warn about known problematic environments
    problematic = ["Replit", "Heroku", "Railway", "Glitch", "GitHub Codespaces"]
    if any(env in env_info for env in problematic):
        print(f"⚠️ WARNING: {', '.join(env_info)} may not support Discord voice connections")
        print("🔧 Voice features may be limited or non-functional")
    
    # Test FFmpeg availability
    try:
        import subprocess
        result = subprocess.run([FFMPEG_EXECUTABLE, '-version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print(f"✅ FFmpeg is working correctly!")
            print(f"🔧 FFmpeg version: {result.stdout.split()[2] if len(result.stdout.split()) > 2 else 'Unknown'}")
        else:
            print(f"⚠️ FFmpeg test failed with return code: {result.returncode}")
    except Exception as e:
        print(f"⚠️ FFmpeg test error: {e}")
        print("🔧 Music system may not work properly without FFmpeg")

def log_command(func):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        try:
            print(f"🎵 Music command: {func.__name__} by {interaction.user.name}")
            return await func(interaction, *args, **kwargs)
        except Exception as e:
            print(f"❌ Error in music command {func.__name__}: {e}")
            print(traceback.format_exc())
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"❌ An error occurred: {str(e)}", ephemeral=True
                )
            raise
    return wrapper

# yt-dlp configuration
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'cachedir': False,
    'extract_flat': False,
}

# Get FFmpeg executable path
try:
    FFMPEG_EXECUTABLE = ffmpeg.get_ffmpeg_exe()
    print(f"🔧 Using FFmpeg from: {FFMPEG_EXECUTABLE}")
except Exception as e:
    print(f"⚠️ FFmpeg not found via imageio-ffmpeg: {e}")
    FFMPEG_EXECUTABLE = 'ffmpeg'  # Fallback to system FFmpeg

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.5"'
}

# Additional options for discord.py
FFMPEG_EXECUTABLE_OPTIONS = {
    'executable': FFMPEG_EXECUTABLE
}

class Song:
    """Represents a song in the queue"""
    def __init__(self, title: str, url: str, duration: str, thumbnail: str, 
                 requester: discord.Member, source_type: str = "youtube"):
        self.title = title
        self.url = url
        self.duration = duration
        self.thumbnail = thumbnail
        self.requester = requester
        self.source_type = source_type
        self.stream_url = None
        self.requested_at = datetime.now()

    def __str__(self):
        return f"{self.title} - {self.duration}"

class MusicPlayer:
    """Music player for a guild"""
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.voice_client: Optional[discord.VoiceClient] = None
        self.queue: List[Song] = []
        self.current_song: Optional[Song] = None
        self.volume = 0.5
        self.loop_mode = "off"  # off, song, queue
        self.is_playing = False
        self.is_paused = False
        self.skip_votes = set()
        self.auto_leave_task = None
        
    async def connect(self, channel: discord.VoiceChannel):
        """Connect to a voice channel using Pycord's improved voice handling"""
        # Check bot permissions first
        permissions = channel.permissions_for(channel.guild.me)
        if not permissions.connect:
            raise discord.errors.ClientException("Bot lacks 'Connect' permission for this voice channel")
        if not permissions.speak:
            raise discord.errors.ClientException("Bot lacks 'Speak' permission for this voice channel")
        
        # Clean up any existing failed connection
        if self.voice_client and not self.voice_client.is_connected():
            try:
                await self.voice_client.disconnect(force=True)
            except:
                pass
            self.voice_client = None
            
        try:
            if self.voice_client and self.voice_client.is_connected():
                if self.voice_client.channel != channel:
                    print(f"🔄 Moving to voice channel: {channel.name}")
                    await self.voice_client.move_to(channel)
                    return
                else:
                    print(f"✅ Already connected to voice channel: {channel.name}")
                    return
            
            print(f"🔗 Attempting to connect to voice channel: {channel.name} (using Pycord)")
            
            # Pycord has better voice connection handling for hosted environments
            try:
                # Use Pycord's improved connection with better timeout handling
                self.voice_client = await channel.connect(
                    timeout=60.0,           # Longer timeout for hosted environments
                    reconnect=True,         # Enable automatic reconnection
                    self_deaf=True,         # Optimize performance by self-deafening
                )
                
                # Verify connection
                if self.voice_client and self.voice_client.is_connected():
                    print(f"✅ Successfully connected to voice channel: {channel.name}")
                    # Small delay to ensure connection is stable
                    await asyncio.sleep(1)
                    return
                else:
                    raise discord.errors.ClientException("Connection established but not properly connected")
                    
            except discord.errors.ClientException as e:
                print(f"⚠️ Pycord voice connection failed: {type(e).__name__}: {e}")
                
                # Check for specific hosting environment issues
                if any(error_code in str(e) for error_code in ["4006", "4014", "Session no longer valid", "Invalid session"]):
                    raise discord.errors.ClientException(
                        "Voice connection failed due to hosting environment limitations. "
                        "This hosting platform may not support Discord voice features."
                    )
                else:
                    # Try one more time with different settings
                    try:
                        print("🔄 Retrying with fallback settings...")
                        await asyncio.sleep(3)
                        
                        self.voice_client = await channel.connect(
                            timeout=30.0,
                            reconnect=False,    # Disable reconnect for second attempt
                            self_deaf=False,    # Don't self-deaf for compatibility
                        )
                        
                        if self.voice_client and self.voice_client.is_connected():
                            print(f"✅ Connected on retry to voice channel: {channel.name}")
                            return
                        else:
                            raise discord.errors.ClientException("Retry connection failed")
                            
                    except Exception as retry_error:
                        print(f"❌ Retry failed: {retry_error}")
                        raise discord.errors.ClientException(f"Voice connection failed: {str(e)}")
                    
        except discord.errors.ClientException:
            raise  # Re-raise client exceptions as-is
        except Exception as e:
            print(f"❌ Unexpected voice connection error: {e}")
            if self.voice_client:
                try:
                    await self.voice_client.disconnect(force=True)
                except:
                    pass
                self.voice_client = None
            raise discord.errors.ClientException(f"Voice connection failed: {str(e)}")
            
    async def disconnect(self):
        """Disconnect from voice channel"""
        if self.voice_client:
            await self.voice_client.disconnect()
            self.voice_client = None
        self.is_playing = False
        self.is_paused = False
        self.current_song = None
        if self.auto_leave_task:
            self.auto_leave_task.cancel()
            
    async def add_song(self, song: Song):
        """Add a song to the queue"""
        self.queue.append(song)
        
    async def play_next(self):
        """Play the next song in queue"""
        if not self.queue and self.loop_mode != "song":
            # No more songs, start auto-leave timer
            await self.start_auto_leave()
            return
            
        if self.loop_mode == "song" and self.current_song:
            # Loop current song
            next_song = self.current_song
        elif self.loop_mode == "queue" and not self.queue:
            # Loop queue - restart from beginning
            if hasattr(self, 'original_queue') and self.original_queue:
                self.queue = self.original_queue.copy()
                next_song = self.queue.pop(0)
            else:
                await self.start_auto_leave()
                return
        else:
            # Normal play
            if not self.queue:
                await self.start_auto_leave()
                return
            next_song = self.queue.pop(0)
            
        self.current_song = next_song
        
        try:
            # Get stream URL
            stream_url = await self.get_stream_url(next_song.url)
            if not stream_url:
                await self.play_next()  # Skip to next song
                return
                
            # Create audio source
            source = discord.FFmpegPCMAudio(
                stream_url, 
                executable=FFMPEG_EXECUTABLE,
                **FFMPEG_OPTIONS
            )
            source = discord.PCMVolumeTransformer(source, volume=self.volume)
            
            # Play the song
            self.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(
                self.play_next(), _client.loop
            ))
            
            self.is_playing = True
            self.is_paused = False
            self.skip_votes.clear()
            
            # Cancel auto-leave if it was running
            if self.auto_leave_task:
                self.auto_leave_task.cancel()
                self.auto_leave_task = None
                
        except Exception as e:
            print(f"Error playing song: {e}")
            await self.play_next()  # Skip to next song
            
    async def get_stream_url(self, video_url: str) -> Optional[str]:
        """Get stream URL from video URL"""
        try:
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(video_url, download=False)
                if 'url' in info:
                    return info['url']
                elif 'entries' in info and info['entries']:
                    return info['entries'][0]['url']
        except Exception as e:
            print(f"Error extracting stream URL: {e}")
        return None
        
    async def start_auto_leave(self, delay: int = 300):  # 5 minutes
        """Start auto-leave timer"""
        if self.auto_leave_task:
            self.auto_leave_task.cancel()
            
        async def auto_leave():
            await asyncio.sleep(delay)
            if not self.is_playing and self.voice_client:
                await self.disconnect()
                
        self.auto_leave_task = asyncio.create_task(auto_leave())
        
    def pause(self):
        """Pause playback"""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            self.is_paused = True
            
    def resume(self):
        """Resume playback"""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            self.is_paused = False
            
    def stop(self):
        """Stop playback"""
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()
        self.is_playing = False
        self.is_paused = False
        
    def skip(self):
        """Skip current song"""
        self.stop()
        
    def set_volume(self, volume: float):
        """Set playback volume (0.0 to 1.0)"""
        self.volume = max(0.0, min(1.0, volume))
        if self.voice_client and hasattr(self.voice_client.source, 'volume'):
            self.voice_client.source.volume = self.volume
            
    def clear_queue(self):
        """Clear the queue"""
        self.queue.clear()
        
    def shuffle_queue(self):
        """Shuffle the queue"""
        import random
        random.shuffle(self.queue)

def get_player(guild: discord.Guild) -> MusicPlayer:
    """Get or create music player for guild"""
    if guild.id not in music_players:
        music_players[guild.id] = MusicPlayer(guild)
    return music_players[guild.id]

async def search_youtube(query: str, limit: int = 1) -> List[Dict]:
    """Search YouTube for videos"""
    try:
        with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
            search_results = ydl.extract_info(
                f"ytsearch{limit}:{query}",
                download=False
            )
            
            if 'entries' in search_results:
                return search_results['entries']
    except Exception as e:
        print(f"YouTube search error: {e}")
    return []

async def search_spotify_track(spotify_url: str) -> Optional[Dict]:
    """Extract track info from Spotify URL"""
    if not spotify:
        return None
        
    try:
        # Extract track ID from URL
        track_id_match = re.search(r'track/([a-zA-Z0-9]+)', spotify_url)
        if not track_id_match:
            return None
            
        track_id = track_id_match.group(1)
        track = spotify.track(track_id)
        
        return {
            'name': track['name'],
            'artist': ', '.join([artist['name'] for artist in track['artists']]),
            'duration': track['duration_ms'] // 1000,
            'image': track['album']['images'][0]['url'] if track['album']['images'] else None
        }
    except Exception as e:
        print(f"Spotify search error: {e}")
    return None

async def search_spotify_playlist(spotify_url: str) -> List[Dict]:
    """Extract tracks from Spotify playlist"""
    if not spotify:
        return []
        
    try:
        # Extract playlist ID from URL
        playlist_id_match = re.search(r'playlist/([a-zA-Z0-9]+)', spotify_url)
        if not playlist_id_match:
            return []
            
        playlist_id = playlist_id_match.group(1)
        playlist = spotify.playlist(playlist_id)
        
        tracks = []
        for item in playlist['tracks']['items']:
            if item['track']:
                track = item['track']
                tracks.append({
                    'name': track['name'],
                    'artist': ', '.join([artist['name'] for artist in track['artists']]),
                    'duration': track['duration_ms'] // 1000,
                    'image': track['album']['images'][0]['url'] if track['album']['images'] else None
                })
                
        return tracks
    except Exception as e:
        print(f"Spotify playlist error: {e}")
    return []

def format_duration(seconds: int) -> str:
    """Format duration in seconds to MM:SS or HH:MM:SS"""
    if seconds is None:
        return "Unknown"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    seconds = seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

# Music Commands

@app_commands.command(name="play", description="Play a song or add to queue")
@app_commands.describe(query="Song name, YouTube URL, or Spotify URL")
@log_command
async def play(interaction: discord.Interaction, query: str):
    """Play a song or add to queue"""
    # Check if user is in voice channel
    if not interaction.user.voice:
        await interaction.response.send_message(
            "❌ You need to be in a voice channel to use music commands!",
            ephemeral=True
        )
        return
        
    await interaction.response.defer()
    
    try:
        player = get_player(interaction.guild)
        voice_channel = interaction.user.voice.channel
        
        # Connect to voice channel
        try:
            await player.connect(voice_channel)
        except discord.errors.ClientException as e:
            # Check if this is a hosting environment limitation
            if "hosting environment limitations" in str(e) or "4006" in str(e):
                embed = discord.Embed(
                    title="🚫 Voice Features Not Available",
                    description=(
                        "**Music playback is not supported on this hosting platform.**\n\n"
                        "This is due to limitations with the current hosting environment that prevent "
                        "Discord voice connections from working properly.\n\n"
                        "**Alternative options:**\n"
                        "• Host the bot on a VPS or dedicated server\n"
                        "• Use a hosting service that supports Discord voice\n"
                        "• Consider using a different music bot for voice features\n\n"
                        "All other bot features (tasks, tickets, invites, etc.) work normally."
                    ),
                    color=discord.Color.red()
                )
                embed.set_footer(text="Error Code: Voice Connection Failed (4006)")
                await interaction.followup.send(embed=embed)
                return
            else:
                embed = discord.Embed(
                    title="❌ Voice Connection Failed",
                    description=(
                        f"**Failed to connect to voice channel: {voice_channel.name}**\n\n"
                        f"**Possible causes:**\n"
                        f"• Bot missing voice permissions (Connect/Speak)\n"
                        f"• Voice channel is full or restricted\n"
                        f"• Temporary Discord voice server issues\n"
                        f"• Network connectivity problems\n\n"
                        f"**Error:** {str(e)}"
                    ),
                    color=discord.Color.red()
                )
                embed.add_field(
                    name="💡 What to try:",
                    value=(
                        "• Check bot permissions in voice channel\n"
                        "• Try a different voice channel\n" 
                        "• Wait a few minutes and try again\n"
                        "• Use `/musicstatus` to check system health"
                    ),
                    inline=False
                )
                await interaction.followup.send(embed=embed)
                return
        except Exception as e:
            await interaction.followup.send(
                f"❌ **Unexpected voice connection error!**\n"
                f"Please try again or contact an administrator.\n\n"
                f"Error: {str(e)}", 
                ephemeral=True
            )
            return
        
        songs_added = []
        
        # Check if it's a Spotify URL
        if 'spotify.com' in query:
            if 'track/' in query:
                # Single track
                spotify_track = await search_spotify_track(query)
                if spotify_track:
                    search_query = f"{spotify_track['artist']} {spotify_track['name']}"
                    youtube_results = await search_youtube(search_query, 1)
                    
                    if youtube_results:
                        result = youtube_results[0]
                        song = Song(
                            title=f"{spotify_track['artist']} - {spotify_track['name']}",
                            url=result['webpage_url'],
                            duration=format_duration(result.get('duration')),
                            thumbnail=spotify_track.get('image', result.get('thumbnail', '')),
                            requester=interaction.user,
                            source_type="spotify"
                        )
                        songs_added.append(song)
                        
            elif 'playlist/' in query:
                # Playlist
                spotify_tracks = await search_spotify_playlist(query)
                for track in spotify_tracks[:20]:  # Limit to 20 tracks
                    search_query = f"{track['artist']} {track['name']}"
                    youtube_results = await search_youtube(search_query, 1)
                    
                    if youtube_results:
                        result = youtube_results[0]
                        song = Song(
                            title=f"{track['artist']} - {track['name']}",
                            url=result['webpage_url'],
                            duration=format_duration(result.get('duration')),
                            thumbnail=track.get('image', result.get('thumbnail', '')),
                            requester=interaction.user,
                            source_type="spotify"
                        )
                        songs_added.append(song)
        else:
            # YouTube search or URL
            if query.startswith(('http://', 'https://')):
                # Direct URL
                try:
                    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                        info = ydl.extract_info(query, download=False)
                        if 'entries' in info:
                            # Playlist
                            for entry in info['entries'][:20]:  # Limit to 20
                                song = Song(
                                    title=entry.get('title', 'Unknown'),
                                    url=entry['webpage_url'],
                                    duration=format_duration(entry.get('duration')),
                                    thumbnail=entry.get('thumbnail', ''),
                                    requester=interaction.user
                                )
                                songs_added.append(song)
                        else:
                            # Single video
                            song = Song(
                                title=info.get('title', 'Unknown'),
                                url=info['webpage_url'],
                                duration=format_duration(info.get('duration')),
                                thumbnail=info.get('thumbnail', ''),
                                requester=interaction.user
                            )
                            songs_added.append(song)
                except Exception as e:
                    await interaction.followup.send(f"❌ Failed to process URL: {str(e)}")
                    return
            else:
                # Search query
                youtube_results = await search_youtube(query, 1)
                if youtube_results:
                    result = youtube_results[0]
                    song = Song(
                        title=result.get('title', 'Unknown'),
                        url=result['webpage_url'],
                        duration=format_duration(result.get('duration')),
                        thumbnail=result.get('thumbnail', ''),
                        requester=interaction.user
                    )
                    songs_added.append(song)
                    
        if not songs_added:
            await interaction.followup.send("❌ No songs found for your query!")
            return
            
        # Add songs to queue
        for song in songs_added:
            await player.add_song(song)
            
        # Start playing if not already playing
        if not player.is_playing and not player.voice_client.is_playing():
            await player.play_next()
            
        # Send response
        if len(songs_added) == 1:
            song = songs_added[0]
            embed = discord.Embed(
                title="🎵 Added to Queue" if player.is_playing else "🎵 Now Playing",
                description=f"**{song.title}**",
                color=discord.Color.green()
            )
            embed.add_field(name="Duration", value=song.duration, inline=True)
            embed.add_field(name="Requested by", value=song.requester.mention, inline=True)
            embed.add_field(name="Queue Position", value=str(len(player.queue) + 1) if player.is_playing else "Now Playing", inline=True)
            
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
                
        else:
            embed = discord.Embed(
                title="🎵 Added Multiple Songs",
                description=f"Added **{len(songs_added)}** songs to the queue",
                color=discord.Color.green()
            )
            
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ An error occurred: {str(e)}")

@app_commands.command(name="pause", description="Pause the current song")
@log_command
async def pause(interaction: discord.Interaction):
    """Pause the current song"""
    player = get_player(interaction.guild)
    
    if not player.voice_client or not player.is_playing:
        await interaction.response.send_message("❌ Nothing is currently playing!", ephemeral=True)
        return
        
    if player.is_paused:
        await interaction.response.send_message("❌ Music is already paused!", ephemeral=True)
        return
        
    player.pause()
    await interaction.response.send_message("⏸️ **Paused** the current song.")

@app_commands.command(name="resume", description="Resume the paused song")
@log_command
async def resume(interaction: discord.Interaction):
    """Resume the paused song"""
    player = get_player(interaction.guild)
    
    if not player.voice_client or not player.is_paused:
        await interaction.response.send_message("❌ Music is not paused!", ephemeral=True)
        return
        
    player.resume()
    await interaction.response.send_message("▶️ **Resumed** the current song.")

@app_commands.command(name="skip", description="Skip the current song")
@log_command
async def skip(interaction: discord.Interaction):
    """Skip the current song"""
    player = get_player(interaction.guild)
    
    if not player.voice_client or not player.is_playing:
        await interaction.response.send_message("❌ Nothing is currently playing!", ephemeral=True)
        return
        
    # Check if user is in voice channel
    if not interaction.user.voice or interaction.user.voice.channel != player.voice_client.channel:
        await interaction.response.send_message("❌ You need to be in the same voice channel!", ephemeral=True)
        return
        
    # Get number of users in voice channel (excluding bots)
    voice_members = [m for m in player.voice_client.channel.members if not m.bot]
    
    if len(voice_members) <= 2:
        # Auto-skip if 2 or fewer people
        player.skip()
        await interaction.response.send_message("⏭️ **Skipped** the current song.")
    else:
        # Vote skip system
        player.skip_votes.add(interaction.user.id)
        votes_needed = len(voice_members) // 2 + 1
        
        if len(player.skip_votes) >= votes_needed:
            player.skip()
            await interaction.response.send_message("⏭️ **Skipped** the current song.")
        else:
            await interaction.response.send_message(
                f"🗳️ Vote to skip registered! ({len(player.skip_votes)}/{votes_needed} votes needed)"
            )

@app_commands.command(name="stop", description="Stop music and clear queue")
@log_command
async def stop(interaction: discord.Interaction):
    """Stop music and clear queue"""
    player = get_player(interaction.guild)
    
    if not player.voice_client:
        await interaction.response.send_message("❌ Not connected to a voice channel!", ephemeral=True)
        return
        
    # Check if user is in voice channel
    if not interaction.user.voice or interaction.user.voice.channel != player.voice_client.channel:
        await interaction.response.send_message("❌ You need to be in the same voice channel!", ephemeral=True)
        return
        
    player.stop()
    player.clear_queue()
    await interaction.response.send_message("⏹️ **Stopped** music and cleared the queue.")

@app_commands.command(name="queue", description="Show the current music queue")
@log_command
async def queue(interaction: discord.Interaction):
    """Show the current music queue"""
    player = get_player(interaction.guild)
    
    if not player.current_song and not player.queue:
        await interaction.response.send_message("❌ The queue is empty!", ephemeral=True)
        return
        
    embed = discord.Embed(
        title="🎵 Music Queue",
        color=discord.Color.blue()
    )
    
    # Current song
    if player.current_song:
        embed.add_field(
            name="🎵 Now Playing",
            value=f"**{player.current_song.title}**\n"
                  f"Duration: {player.current_song.duration}\n"
                  f"Requested by: {player.current_song.requester.mention}",
            inline=False
        )
        
    # Queue
    if player.queue:
        queue_text = ""
        for i, song in enumerate(player.queue[:10], 1):  # Show first 10
            queue_text += f"`{i}.` **{song.title}** - {song.duration}\n"
            
        embed.add_field(
            name=f"📋 Up Next ({len(player.queue)} songs)",
            value=queue_text,
            inline=False
        )
        
        if len(player.queue) > 10:
            embed.add_field(
                name="",
                value=f"... and {len(player.queue) - 10} more songs",
                inline=False
            )
            
    # Loop mode
    if player.loop_mode != "off":
        embed.add_field(
            name="🔄 Loop Mode",
            value=player.loop_mode.title(),
            inline=True
        )
        
    await interaction.response.send_message(embed=embed)

@app_commands.command(name="nowplaying", description="Show currently playing song")
@log_command
async def nowplaying(interaction: discord.Interaction):
    """Show currently playing song"""
    player = get_player(interaction.guild)
    
    if not player.current_song:
        await interaction.response.send_message("❌ Nothing is currently playing!", ephemeral=True)
        return
        
    song = player.current_song
    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"**{song.title}**",
        color=discord.Color.green()
    )
    
    embed.add_field(name="Duration", value=song.duration, inline=True)
    embed.add_field(name="Requested by", value=song.requester.mention, inline=True)
    embed.add_field(name="Volume", value=f"{int(player.volume * 100)}%", inline=True)
    
    if song.source_type == "spotify":
        embed.add_field(name="Source", value="🎵 Spotify", inline=True)
        
    if player.loop_mode != "off":
        embed.add_field(name="Loop", value=f"🔄 {player.loop_mode.title()}", inline=True)
        
    if song.thumbnail:
        embed.set_thumbnail(url=song.thumbnail)
        
    await interaction.response.send_message(embed=embed)

@app_commands.command(name="volume", description="Set the music volume (1-100)")
@app_commands.describe(volume="Volume level from 1 to 100")
@log_command
async def volume(interaction: discord.Interaction, volume: int):
    """Set the music volume"""
    if volume < 1 or volume > 100:
        await interaction.response.send_message("❌ Volume must be between 1 and 100!", ephemeral=True)
        return
        
    player = get_player(interaction.guild)
    
    if not player.voice_client:
        await interaction.response.send_message("❌ Not connected to a voice channel!", ephemeral=True)
        return
        
    player.set_volume(volume / 100)
    await interaction.response.send_message(f"🔊 Volume set to **{volume}%**")

@app_commands.command(name="loop", description="Set loop mode (off/song/queue)")
@app_commands.describe(mode="Loop mode: off, song, or queue")
@log_command
async def loop(interaction: discord.Interaction, mode: str):
    """Set loop mode"""
    if mode.lower() not in ['off', 'song', 'queue']:
        await interaction.response.send_message("❌ Loop mode must be: off, song, or queue", ephemeral=True)
        return
        
    player = get_player(interaction.guild)
    player.loop_mode = mode.lower()
    
    if mode.lower() == "off":
        await interaction.response.send_message("🔄 Loop mode **disabled**")
    elif mode.lower() == "song":
        await interaction.response.send_message("🔄 Now looping the **current song**")
    else:  # queue
        await interaction.response.send_message("🔄 Now looping the **entire queue**")
        # Store original queue for looping
        if player.queue:
            player.original_queue = player.queue.copy()

@app_commands.command(name="shuffle", description="Shuffle the current queue")
@log_command
async def shuffle(interaction: discord.Interaction):
    """Shuffle the current queue"""
    player = get_player(interaction.guild)
    
    if not player.queue:
        await interaction.response.send_message("❌ The queue is empty!", ephemeral=True)
        return
        
    player.shuffle_queue()
    await interaction.response.send_message("🔀 **Shuffled** the queue!")

@app_commands.command(name="remove", description="Remove a song from the queue")
@app_commands.describe(position="Position of the song to remove (1-based)")
@log_command
async def remove(interaction: discord.Interaction, position: int):
    """Remove a song from the queue"""
    player = get_player(interaction.guild)
    
    if not player.queue:
        await interaction.response.send_message("❌ The queue is empty!", ephemeral=True)
        return
        
    if position < 1 or position > len(player.queue):
        await interaction.response.send_message(f"❌ Position must be between 1 and {len(player.queue)}!", ephemeral=True)
        return
        
    removed_song = player.queue.pop(position - 1)
    await interaction.response.send_message(f"🗑️ Removed **{removed_song.title}** from the queue.")

@app_commands.command(name="clear", description="Clear the entire queue")
@log_command
async def clear(interaction: discord.Interaction):
    """Clear the entire queue"""
    player = get_player(interaction.guild)
    
    if not player.queue:
        await interaction.response.send_message("❌ The queue is already empty!", ephemeral=True)
        return
        
    player.clear_queue()
    await interaction.response.send_message("🗑️ **Cleared** the entire queue!")

@app_commands.command(name="leave", description="Disconnect from voice channel")
@log_command
async def leave(interaction: discord.Interaction):
    """Disconnect from voice channel"""
    player = get_player(interaction.guild)
    
    if not player.voice_client:
        await interaction.response.send_message("❌ Not connected to a voice channel!", ephemeral=True)
        return
        
    # Check if user is in voice channel
    if not interaction.user.voice or interaction.user.voice.channel != player.voice_client.channel:
        await interaction.response.send_message("❌ You need to be in the same voice channel!", ephemeral=True)
        return
        
    await player.disconnect()
    await interaction.response.send_message("👋 **Left** the voice channel.")

@app_commands.command(name="search", description="Search for songs without playing")
@app_commands.describe(query="Search query")
@log_command
async def search(interaction: discord.Interaction, query: str):
    """Search for songs without playing"""
    await interaction.response.defer()
    
    try:
        results = await search_youtube(query, 5)
        
        if not results:
            await interaction.followup.send("❌ No results found!")
            return
            
        embed = discord.Embed(
            title=f"🔍 Search Results for: {query}",
            color=discord.Color.blue()
        )
        
        for i, result in enumerate(results, 1):
            embed.add_field(
                name=f"{i}. {result.get('title', 'Unknown')}",
                value=f"Duration: {format_duration(result.get('duration'))}\n"
                      f"[Watch on YouTube]({result['webpage_url']})",
                inline=False
            )
            
        embed.set_footer(text="Use /play <song name> to add to queue")
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Search failed: {str(e)}")

@app_commands.command(name="musicstatus", description="Check music system status (Admin only)")
@app_commands.default_permissions(administrator=True)
@log_command
async def musicstatus(interaction: discord.Interaction):
    """Check music system status and configuration"""
    embed = discord.Embed(
        title="🎵 Music System Status",
        color=discord.Color.blue()
    )
    
    # FFmpeg status
    try:
        import subprocess
        result = subprocess.run([FFMPEG_EXECUTABLE, '-version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            ffmpeg_status = f"✅ Working (v{result.stdout.split()[2] if len(result.stdout.split()) > 2 else 'Unknown'})"
        else:
            ffmpeg_status = f"❌ Failed (code: {result.returncode})"
    except Exception as e:
        ffmpeg_status = f"❌ Error: {str(e)}"
    
    embed.add_field(name="FFmpeg", value=ffmpeg_status, inline=True)
    embed.add_field(name="FFmpeg Path", value=f"`{FFMPEG_EXECUTABLE}`", inline=False)
    
    # Voice client status
    player = get_player(interaction.guild)
    if player.voice_client:
        voice_status = f"✅ Connected to {player.voice_client.channel.name}"
        if player.current_song:
            voice_status += f"\n🎵 Playing: {player.current_song.title}"
    else:
        voice_status = "❌ Not connected"
    
    embed.add_field(name="Voice Connection", value=voice_status, inline=True)
    
    # Queue status
    queue_status = f"📋 {len(player.queue)} songs in queue"
    if player.loop_mode != "off":
        queue_status += f"\n🔄 Loop: {player.loop_mode}"
    
    embed.add_field(name="Queue", value=queue_status, inline=True)
    
    # Dependencies
    deps_status = ""
    try:
        import yt_dlp
        deps_status += "✅ yt-dlp\n"
    except ImportError:
        deps_status += "❌ yt-dlp\n"
        
    try:
        import spotipy
        deps_status += "✅ spotipy\n"
    except ImportError:
        deps_status += "❌ spotipy\n"
        
    try:
        import imageio_ffmpeg
        deps_status += "✅ imageio-ffmpeg\n"
    except ImportError:
        deps_status += "❌ imageio-ffmpeg\n"
    
    embed.add_field(name="Dependencies", value=deps_status, inline=True)
    
    # Spotify status
    spotify_status = "✅ Configured" if spotify else "❌ Not configured"
    embed.add_field(name="Spotify Integration", value=spotify_status, inline=True)
    
    # Bot & Library Information
    import platform
    bot_info = f"**Pycord Version:** {discord.__version__}\n"
    bot_info += f"**Python Version:** {platform.python_version()}\n"
    bot_info += f"**OS:** {platform.system()} {platform.release()}"
    embed.add_field(name="🤖 System Info", value=bot_info, inline=False)
    
    # Hosting environment
    env_info = detect_hosting_environment()
    env_status = f"🏠 {', '.join(env_info)}"
    problematic = ["Replit", "Heroku", "Railway", "Glitch", "GitHub Codespaces"]
    if any(env in env_info for env in problematic):
        env_status += "\n⚠️ May not support voice"
    embed.add_field(name="Hosting Environment", value=env_status, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.command(name="voicetest", description="Test voice connection capability (Admin only)")
@app_commands.default_permissions(administrator=True)
@log_command
async def voicetest(interaction: discord.Interaction):
    """Test voice connection capability without playing music"""
    if not interaction.user.voice:
        await interaction.response.send_message(
            "❌ You need to be in a voice channel to test voice connectivity!",
            ephemeral=True
        )
        return
        
    await interaction.response.defer()
    
    try:
        voice_channel = interaction.user.voice.channel
        player = get_player(interaction.guild)
        
        embed = discord.Embed(
            title="🧪 Voice Connection Test",
            description=f"Testing connection to **{voice_channel.name}**...",
            color=discord.Color.blue()
        )
        
        test_results = []
        
        # Test 1: Permission check
        permissions = voice_channel.permissions_for(voice_channel.guild.me)
        if permissions.connect and permissions.speak:
            test_results.append("✅ **Permissions:** Connect & Speak permissions available")
        else:
            missing = []
            if not permissions.connect:
                missing.append("Connect")
            if not permissions.speak:
                missing.append("Speak")
            test_results.append(f"❌ **Permissions:** Missing {', '.join(missing)} permission(s)")
        
        # Test 2: Voice connection attempt
        try:
            test_results.append("🔄 **Connection Test:** Attempting to connect...")
            
            # Clean up any existing connection
            if player.voice_client:
                await player.disconnect()
            
            # Try to connect
            await player.connect(voice_channel)
            
            if player.voice_client and player.voice_client.is_connected():
                test_results.append("✅ **Connection Test:** Successfully connected!")
                
                # Test 3: Check connection stability
                await asyncio.sleep(2)
                if player.voice_client.is_connected():
                    test_results.append("✅ **Stability Test:** Connection remained stable")
                else:
                    test_results.append("❌ **Stability Test:** Connection dropped after 2 seconds")
                
                # Clean up
                await player.disconnect()
                test_results.append("🧹 **Cleanup:** Disconnected successfully")
            else:
                test_results.append("❌ **Connection Test:** Failed to establish connection")
                
        except discord.errors.ClientException as e:
            if "hosting environment limitations" in str(e):
                test_results.append("❌ **Connection Test:** Hosting environment does not support voice")
                test_results.append("ℹ️ **Diagnosis:** This hosting platform blocks Discord voice connections")
            else:
                test_results.append(f"❌ **Connection Test:** {str(e)}")
                
        except Exception as e:
            test_results.append(f"❌ **Connection Test:** Unexpected error - {str(e)}")
        
        # Update embed with results
        embed.description = f"**Voice Connection Test Results for {voice_channel.name}:**\n\n" + "\n".join(test_results)
        
        # Determine overall status
        if any("❌" in result for result in test_results):
            embed.color = discord.Color.red()
            embed.add_field(
                name="🔧 Recommendation",
                value="Voice features may not work properly. Check the failed tests above.",
                inline=False
            )
        else:
            embed.color = discord.Color.green()
            embed.add_field(
                name="🎉 Result",
                value="Voice connection should work normally! Try `/play <song>` now.",
                inline=False
            )
            
        await interaction.followup.send(embed=embed)
        
    except Exception as e:
        await interaction.followup.send(
            f"❌ Voice test failed with unexpected error: {str(e)}",
            ephemeral=True
        )

def setup_music_commands(tree):
    """Add music commands to the command tree"""
    tree.add_command(play)
    tree.add_command(pause)
    tree.add_command(resume)
    tree.add_command(skip)
    tree.add_command(stop)
    tree.add_command(queue)
    tree.add_command(nowplaying)
    tree.add_command(volume)
    tree.add_command(loop)
    tree.add_command(shuffle)
    tree.add_command(remove)
    tree.add_command(clear)
    tree.add_command(leave)
    tree.add_command(search)
    tree.add_command(musicstatus)
    tree.add_command(voicetest)
    print("🎵 Music commands loaded: /play, /pause, /resume, /skip, /stop, /queue, /nowplaying, /volume, /loop, /shuffle, /remove, /clear, /leave, /search, /musicstatus, /voicetest")

# Cleanup function
async def cleanup_music_players():
    """Clean up inactive music players"""
    for guild_id, player in list(music_players.items()):
        if not player.voice_client or not player.voice_client.is_connected():
            del music_players[guild_id]
