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

def setup_music_system(client):
    """Initialize the music system with client reference"""
    global _client
    _client = client

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

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
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
        """Connect to a voice channel with error handling"""
        try:
            if self.voice_client and self.voice_client.is_connected():
                if self.voice_client.channel != channel:
                    await self.voice_client.move_to(channel)
                    print(f"🔄 Moved to voice channel: {channel.name}")
            else:
                self.voice_client = await channel.connect(timeout=30.0, reconnect=True)
                print(f"🔊 Connected to voice channel: {channel.name}")
        except discord.errors.ClientException as e:
            print(f"❌ Voice connection error: {e}")
            raise Exception(f"Failed to connect to voice channel: {str(e)}")
        except asyncio.TimeoutError:
            print("❌ Voice connection timed out")
            raise Exception("Voice connection timed out. Please try again.")
        except Exception as e:
            print(f"❌ Unexpected voice error: {e}")
            raise Exception(f"Voice connection failed: {str(e)}")
            
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
            try:
                source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
                source = discord.PCMVolumeTransformer(source, volume=self.volume)
            except discord.errors.ClientException as e:
                if "ffmpeg" in str(e).lower():
                    print("❌ FFmpeg not found! Please install FFmpeg to use music features.")
                    print("For Replit: Make sure replit.nix includes ffmpeg-full")
                    print("For local: Download from https://ffmpeg.org/download.html")
                    return
                else:
                    print(f"❌ Audio source error: {e}")
                    await self.play_next()  # Skip to next song
                    return
            
            # Play the song
            def after_playing(error):
                if error:
                    print(f"❌ Player error: {error}")
                asyncio.run_coroutine_threadsafe(self.play_next(), _client.loop)
            
            self.voice_client.play(source, after=after_playing)
            
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

def check_music_requirements() -> tuple[bool, str]:
    """Check if all music requirements are met"""
    import shutil
    
    # Check FFmpeg
    if not shutil.which('ffmpeg'):
        return False, ("❌ **FFmpeg not found!**\n\n"
                      "**To fix this:**\n"
                      "• **Replit**: Create `replit.nix` file with `pkgs.ffmpeg-full`\n"
                      "• **Local Windows**: Download from https://ffmpeg.org/download.html\n"
                      "• **Local Linux**: `sudo apt install ffmpeg`\n"
                      "• **Local macOS**: `brew install ffmpeg`")
    
    # Check PyNaCl for voice
    try:
        import nacl
    except ImportError:
        return False, ("❌ **PyNaCl not found!**\n\n"
                      "Run: `pip install PyNaCl==1.5.0`")
    
    # Check yt-dlp
    try:
        import yt_dlp
    except ImportError:
        return False, ("❌ **yt-dlp not found!**\n\n"
                      "Run: `pip install yt-dlp==2024.12.13`")
    
    return True, "✅ All music requirements are met!"

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
    
    # Check if all music requirements are met
    requirements_ok, requirements_msg = check_music_requirements()
    if not requirements_ok:
        await interaction.followup.send(requirements_msg)
        return
    
    try:
        player = get_player(interaction.guild)
        voice_channel = interaction.user.voice.channel
        
        # Check bot permissions in voice channel
        bot_member = interaction.guild.me
        if not voice_channel.permissions_for(bot_member).connect:
            await interaction.followup.send("❌ I don't have permission to connect to that voice channel!")
            return
        
        if not voice_channel.permissions_for(bot_member).speak:
            await interaction.followup.send("❌ I don't have permission to speak in that voice channel!")
            return
        
        # Connect to voice channel
        try:
            await player.connect(voice_channel)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to connect to voice channel: {str(e)}\n\n"
                                          "**Possible solutions:**\n"
                                          "• Make sure I have `Connect` and `Speak` permissions\n"
                                          "• Try disconnecting and reconnecting to the voice channel\n"
                                          "• Check if the voice channel is full")
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

@app_commands.command(name="musicdebug", description="Check music system requirements and status")
@log_command
async def musicdebug(interaction: discord.Interaction):
    """Debug music system requirements"""
    import shutil
    import sys
    import platform
    
    embed = discord.Embed(
        title="🔍 Music System Debug",
        color=discord.Color.blue()
    )
    
    # System info
    embed.add_field(
        name="🖥️ System Info",
        value=f"**Platform:** {platform.system()} {platform.release()}\n"
              f"**Python:** {sys.version.split()[0]}\n"
              f"**Discord.py:** {discord.__version__}",
        inline=False
    )
    
    # Check requirements
    requirements_ok, requirements_msg = check_music_requirements()
    
    # FFmpeg check
    ffmpeg_path = shutil.which('ffmpeg')
    ffmpeg_status = f"✅ Found at: `{ffmpeg_path}`" if ffmpeg_path else "❌ Not found"
    
    # Library checks
    libs_status = []
    for lib_name, import_name in [("PyNaCl", "nacl"), ("yt-dlp", "yt_dlp"), ("spotipy", "spotipy")]:
        try:
            __import__(import_name)
            libs_status.append(f"✅ {lib_name}")
        except ImportError:
            libs_status.append(f"❌ {lib_name}")
    
    embed.add_field(
        name="📦 Dependencies",
        value=f"**FFmpeg:** {ffmpeg_status}\n" + "\n".join(libs_status),
        inline=False
    )
    
    # Voice status
    player = get_player(interaction.guild)
    voice_status = "Not connected"
    if player.voice_client:
        if player.voice_client.is_connected():
            voice_status = f"✅ Connected to {player.voice_client.channel.name}"
        else:
            voice_status = "❌ Connection failed"
    
    embed.add_field(
        name="🔊 Voice Status",
        value=voice_status,
        inline=False
    )
    
    # Queue status
    queue_status = f"**Current:** {player.current_song.title if player.current_song else 'None'}\n"
    queue_status += f"**Queue:** {len(player.queue)} songs\n"
    queue_status += f"**Playing:** {'Yes' if player.is_playing else 'No'}\n"
    queue_status += f"**Paused:** {'Yes' if player.is_paused else 'No'}"
    
    embed.add_field(
        name="🎵 Playback Status",
        value=queue_status,
        inline=False
    )
    
    if not requirements_ok:
        embed.add_field(
            name="❌ Issues Found",
            value=requirements_msg,
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

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
    tree.add_command(musicdebug)
    print("🎵 Music commands loaded: /play, /pause, /resume, /skip, /stop, /queue, /nowplaying, /volume, /loop, /shuffle, /remove, /clear, /leave, /search, /musicdebug")

# Cleanup function
async def cleanup_music_players():
    """Clean up inactive music players"""
    for guild_id, player in list(music_players.items()):
        if not player.voice_client or not player.voice_client.is_connected():
            del music_players[guild_id]
