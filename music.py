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
import logging
import sys

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('music_debug.log', mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger('MusicSystem')

# Store references
_client = None
music_players = {}  # Guild ID -> MusicPlayer instance

# Debug helper functions
def set_debug_level(level_name: str = "DEBUG"):
    """Set logging level for music system debugging"""
    level = getattr(logging, level_name.upper(), logging.DEBUG)
    logger.setLevel(level)
    logging.getLogger().setLevel(level)
    logger.info(f"Music system debug level set to: {level_name.upper()}")

def get_debug_info(guild_id: int = None) -> dict:
    """Get comprehensive debug information"""
    debug_info = {
        "logger_level": logger.level,
        "ffmpeg_path": FFMPEG_EXECUTABLE,
        "client_ready": _client is not None,
        "spotify_configured": spotify is not None,
        "hosting_environment": detect_hosting_environment(),
        "active_players": len(music_players),
    }
    
    if guild_id and guild_id in music_players:
        player = music_players[guild_id]
        debug_info["player_state"] = {
            "voice_client": player.voice_client is not None,
            "is_connected": player.voice_client.is_connected() if player.voice_client else False,
            "current_song": player.current_song.title if player.current_song else None,
            "queue_length": len(player.queue),
            "is_playing": player.is_playing,
            "is_paused": player.is_paused,
            "volume": player.volume,
            "loop_mode": player.loop_mode,
            "_connecting": player._connecting,
        }
    
    return debug_info

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
    
    logger.info("🎵 Initializing Music System...")
    logger.debug(f"Client object: {client}")
    logger.debug(f"Client user: {client.user if hasattr(client, 'user') else 'Not ready'}")
    
    # Detect hosting environment
    env_info = detect_hosting_environment()
    logger.info(f"🏠 Detected hosting environment: {', '.join(env_info)}")
    print(f"🏠 Detected hosting environment: {', '.join(env_info)}")
    
    # Log environment variables for debugging
    logger.debug("Environment variables:")
    for key in ['REPL_ID', 'DYNO', 'RAILWAY_ENVIRONMENT', 'CODESPACES', 'PROJECT_DOMAIN']:
        value = os.environ.get(key)
        if value:
            logger.debug(f"  {key}={value}")
    
    # Warn about known problematic environments
    problematic = ["Replit", "Heroku", "Railway", "Glitch", "GitHub Codespaces"]
    if any(env in env_info for env in problematic):
        logger.warning(f"⚠️ WARNING: {', '.join(env_info)} may not support Discord voice connections")
        print(f"⚠️ WARNING: {', '.join(env_info)} may not support Discord voice connections")
        print("🔧 Voice features may be limited or non-functional")
    
    # Test FFmpeg availability with extensive debugging
    logger.info("🔧 Testing FFmpeg availability...")
    try:
        import subprocess
        logger.debug(f"FFmpeg executable path: {FFMPEG_EXECUTABLE}")
        
        result = subprocess.run([FFMPEG_EXECUTABLE, '-version'], 
                              capture_output=True, text=True, timeout=10)
        
        logger.debug(f"FFmpeg test return code: {result.returncode}")
        logger.debug(f"FFmpeg stdout: {result.stdout[:500]}...")  # First 500 chars
        if result.stderr:
            logger.debug(f"FFmpeg stderr: {result.stderr[:500]}...")
            
        if result.returncode == 0:
            logger.info("✅ FFmpeg is working correctly!")
            version = result.stdout.split()[2] if len(result.stdout.split()) > 2 else 'Unknown'
            logger.info(f"🔧 FFmpeg version: {version}")
            print(f"✅ FFmpeg is working correctly!")
            print(f"🔧 FFmpeg version: {version}")
        else:
            logger.error(f"⚠️ FFmpeg test failed with return code: {result.returncode}")
            logger.error(f"FFmpeg stderr: {result.stderr}")
            print(f"⚠️ FFmpeg test failed with return code: {result.returncode}")
            
    except FileNotFoundError as e:
        logger.error(f"❌ FFmpeg executable not found: {e}")
        logger.error(f"Tried path: {FFMPEG_EXECUTABLE}")
        print(f"⚠️ FFmpeg not found: {e}")
        print("🔧 Music system may not work properly without FFmpeg")
    except subprocess.TimeoutExpired:
        logger.error("❌ FFmpeg test timed out after 10 seconds")
        print("⚠️ FFmpeg test timed out")
    except Exception as e:
        logger.error(f"❌ FFmpeg test error: {e}")
        logger.error(f"Full traceback: {traceback.format_exc()}")
        print(f"⚠️ FFmpeg test error: {e}")
        print("🔧 Music system may not work properly without FFmpeg")
    
    # Test Discord.py voice support
    logger.info("🎤 Testing Discord.py voice support...")
    try:
        import discord.voice_client
        logger.info("✅ Discord voice client module available")
        
        # Test PyNaCl availability
        try:
            import nacl
            logger.info("✅ PyNaCl (voice encryption) available")
        except ImportError:
            logger.error("❌ PyNaCl not available - voice will not work!")
            
    except ImportError as e:
        logger.error(f"❌ Discord voice support not available: {e}")
    
    # Test dependencies
    logger.info("📦 Testing dependencies...")
    deps = ['yt_dlp', 'spotipy', 'aiofiles', 'imageio_ffmpeg']
    for dep in deps:
        try:
            __import__(dep)
            logger.info(f"✅ {dep} available")
        except ImportError as e:
            logger.error(f"❌ {dep} not available: {e}")
    
    logger.info("🎵 Music System initialization complete!")

def log_command(func):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        command_start = datetime.now()
        guild_id = interaction.guild.id if interaction.guild else "DM"
        user_info = f"{interaction.user.name} ({interaction.user.id})"
        
        logger.info(f"[Guild {guild_id}] Music command '{func.__name__}' called by {user_info}")
        logger.debug(f"[Guild {guild_id}] Command args: {args}")
        logger.debug(f"[Guild {guild_id}] Command kwargs: {kwargs}")
        logger.debug(f"[Guild {guild_id}] User voice state: {getattr(interaction.user, 'voice', None)}")
        
        print(f"🎵 Music command: {func.__name__} by {interaction.user.name}")
        
        try:
            result = await func(interaction, *args, **kwargs)
            
            command_end = datetime.now()
            duration = (command_end - command_start).total_seconds()
            logger.info(f"[Guild {guild_id}] Command '{func.__name__}' completed successfully in {duration:.2f} seconds")
            
            return result
            
        except discord.errors.NotFound as e:
            logger.error(f"[Guild {guild_id}] Discord NotFound error in command {func.__name__}: {e}")
            logger.error(f"[Guild {guild_id}] Command error traceback: {traceback.format_exc()}")
            print(f"❌ Discord NotFound error in music command {func.__name__}: {e}")
            # Don't try to respond if interaction is not found
            raise
            
        except discord.errors.InteractionResponded as e:
            logger.error(f"[Guild {guild_id}] Interaction already responded in command {func.__name__}: {e}")
            logger.error(f"[Guild {guild_id}] Command error traceback: {traceback.format_exc()}")
            print(f"❌ Interaction already responded in music command {func.__name__}: {e}")
            raise
            
        except Exception as e:
            command_end = datetime.now()
            duration = (command_end - command_start).total_seconds()
            
            logger.error(f"[Guild {guild_id}] Error in music command {func.__name__} after {duration:.2f} seconds: {e}")
            logger.error(f"[Guild {guild_id}] Command error traceback: {traceback.format_exc()}")
            print(f"❌ Error in music command {func.__name__}: {e}")
            print(traceback.format_exc())
            
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        f"❌ An error occurred: {str(e)}\n\n"
                        f"**Debug Info:**\n"
                        f"Command: `{func.__name__}`\n"
                        f"Error Type: `{type(e).__name__}`\n"
                        f"Check the bot logs for detailed information.", 
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        f"❌ An error occurred: {str(e)}\n\n"
                        f"**Debug Info:**\n"
                        f"Command: `{func.__name__}`\n"
                        f"Error Type: `{type(e).__name__}`\n"
                        f"Check the bot logs for detailed information.", 
                        ephemeral=True
                    )
            except Exception as response_error:
                logger.error(f"[Guild {guild_id}] Failed to send error response: {response_error}")
                
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
        self._connecting = False  # Track if connection is in progress
        
    async def _safe_disconnect(self, force: bool = True, full_cleanup: bool = True):
        """Safely disconnect from voice channel with proper cleanup"""
        logger.debug(f"[Guild {self.guild.id}] _safe_disconnect called: force={force}, full_cleanup={full_cleanup}")
        
        if self.voice_client:
            logger.debug(f"[Guild {self.guild.id}] Voice client exists: {type(self.voice_client)}")
            logger.debug(f"[Guild {self.guild.id}] Voice client channel: {getattr(self.voice_client, 'channel', 'None')}")
            
            try:
                # Check if voice client is in a valid state
                is_connected = hasattr(self.voice_client, 'is_connected') and self.voice_client.is_connected()
                logger.debug(f"[Guild {self.guild.id}] Voice client is_connected: {is_connected}")
                
                if is_connected:
                    logger.info(f"[Guild {self.guild.id}] Disconnecting from voice channel (force={force})")
                    await self.voice_client.disconnect(force=force)
                    logger.info(f"[Guild {self.guild.id}] Voice disconnect completed")
                else:
                    # Voice client exists but not connected, force cleanup
                    logger.debug(f"[Guild {self.guild.id}] Voice client not connected, attempting cleanup")
                    if hasattr(self.voice_client, 'cleanup'):
                        logger.debug(f"[Guild {self.guild.id}] Calling voice client cleanup")
                        self.voice_client.cleanup()
                    else:
                        logger.debug(f"[Guild {self.guild.id}] Voice client has no cleanup method")
                        
            except Exception as e:
                logger.error(f"[Guild {self.guild.id}] Error during voice disconnect: {e}")
                logger.error(f"[Guild {self.guild.id}] Disconnect error traceback: {traceback.format_exc()}")
                print(f"Warning: Error during voice disconnect: {e}")
            finally:
                logger.debug(f"[Guild {self.guild.id}] Setting voice_client to None")
                self.voice_client = None
        else:
            logger.debug(f"[Guild {self.guild.id}] No voice client to disconnect")
        
        if full_cleanup:
            logger.debug(f"[Guild {self.guild.id}] Performing full cleanup")
            # Reset playback state
            self.is_playing = False
            self.is_paused = False
            if self.auto_leave_task:
                logger.debug(f"[Guild {self.guild.id}] Cancelling auto-leave task")
                self.auto_leave_task.cancel()
                self.auto_leave_task = None
            # Reset connection state
            self._connecting = False
            logger.debug(f"[Guild {self.guild.id}] Full cleanup completed")
        
    async def connect(self, channel: discord.VoiceChannel):
        """Connect to a voice channel with enhanced retry logic and permission checking"""
        logger.info(f"[Guild {self.guild.id}] Connect requested to channel: {channel.name} (ID: {channel.id})")
        logger.debug(f"[Guild {self.guild.id}] Channel type: {type(channel)}")
        logger.debug(f"[Guild {self.guild.id}] Channel members: {[m.name for m in channel.members]}")
        logger.debug(f"[Guild {self.guild.id}] Current connection state - _connecting: {self._connecting}")
        logger.debug(f"[Guild {self.guild.id}] Current voice_client: {self.voice_client}")
        
        # Prevent concurrent connection attempts
        if self._connecting:
            logger.warning(f"[Guild {self.guild.id}] Connection already in progress for {channel.name}, waiting...")
            print(f"⏳ Connection already in progress for {channel.name}, waiting...")
            
            # Wait for up to 45 seconds for the current connection attempt to finish
            for wait_time in range(45):
                await asyncio.sleep(1)
                if not self._connecting:
                    logger.debug(f"[Guild {self.guild.id}] Previous connection attempt finished after {wait_time + 1} seconds")
                    break
                if wait_time % 10 == 9:  # Log every 10 seconds
                    logger.debug(f"[Guild {self.guild.id}] Still waiting for connection... ({wait_time + 1}/45 seconds)")
            
            # If still connecting after 45 seconds, something went wrong
            if self._connecting:
                logger.error(f"[Guild {self.guild.id}] Connection attempt timed out after 45 seconds, resetting connection state")
                print(f"❌ Connection attempt timed out, resetting connection state")
                self._connecting = False
                await self._safe_disconnect(force=True, full_cleanup=False)
        
        # Check if we're already connected to the target channel
        if self.voice_client and self.voice_client.is_connected():
            current_channel = getattr(self.voice_client, 'channel', None)
            logger.debug(f"[Guild {self.guild.id}] Already have voice client connected to: {current_channel}")
            
            if current_channel == channel:
                logger.info(f"[Guild {self.guild.id}] Already connected to target channel: {channel.name}")
                print(f"✅ Already connected to voice channel: {channel.name}")
                return
            else:
                logger.info(f"[Guild {self.guild.id}] Moving from {current_channel} to {channel.name}")
                print(f"🔄 Moving to voice channel: {channel.name}")
                try:
                    await self.voice_client.move_to(channel)
                    logger.info(f"[Guild {self.guild.id}] Successfully moved to {channel.name}")
                    return
                except Exception as e:
                    logger.error(f"[Guild {self.guild.id}] Failed to move to voice channel: {e}")
                    logger.error(f"[Guild {self.guild.id}] Move error traceback: {traceback.format_exc()}")
                    print(f"❌ Failed to move to voice channel: {e}")
                    # Continue to normal connection logic
        
        # Set connection flag
        logger.debug(f"[Guild {self.guild.id}] Setting _connecting flag to True")
        self._connecting = True
        
        try:
            # Check bot permissions first
            logger.debug(f"[Guild {self.guild.id}] Checking bot permissions for channel {channel.name}")
            permissions = channel.permissions_for(channel.guild.me)
            logger.debug(f"[Guild {self.guild.id}] Bot permissions: connect={permissions.connect}, speak={permissions.speak}")
            logger.debug(f"[Guild {self.guild.id}] All channel permissions: {[perm for perm, value in permissions if value]}")
            
            if not permissions.connect:
                logger.error(f"[Guild {self.guild.id}] Bot lacks 'Connect' permission for voice channel")
                raise discord.errors.ClientException("Bot lacks 'Connect' permission for this voice channel")
            if not permissions.speak:
                logger.error(f"[Guild {self.guild.id}] Bot lacks 'Speak' permission for voice channel")
                raise discord.errors.ClientException("Bot lacks 'Speak' permission for this voice channel")
            
            logger.info(f"[Guild {self.guild.id}] Bot has required permissions (Connect & Speak)")
            
            # Clean up any existing failed connection
            logger.debug(f"[Guild {self.guild.id}] Cleaning up any existing failed connections")
            await self._safe_disconnect(force=True, full_cleanup=False)
            
            # Enhanced connection strategy for hosted environments
            logger.info(f"[Guild {self.guild.id}] Starting connection attempt to {channel.name}")
            print(f"🔗 Attempting to connect to voice channel: {channel.name}")
            
            # Direct connection with extended verification
            for attempt in range(1):  # Reduced to single attempt with better verification
                try:
                    logger.info(f"[Guild {self.guild.id}] Connection attempt {attempt + 1}/1 starting")
                    print(f"📡 Voice connection attempt {attempt + 1}/1...")
                    
                    # Check if we somehow already have a working connection before attempting
                    if self.voice_client and hasattr(self.voice_client, 'is_connected') and self.voice_client.is_connected():
                        logger.info(f"[Guild {self.guild.id}] Connection already established, skipping attempt")
                        print(f"✅ Connection already established")
                        return
                    
                    # Log connection parameters
                    logger.debug(f"[Guild {self.guild.id}] Connection parameters: timeout=30.0, reconnect=True, outer_timeout=45.0")
                    logger.debug(f"[Guild {self.guild.id}] Discord.py version: {discord.__version__}")
                    
                    # Use a longer timeout for hosted environments
                    logger.debug(f"[Guild {self.guild.id}] Calling channel.connect()...")
                    connection_start_time = datetime.now()
                    
                    self.voice_client = await asyncio.wait_for(
                        channel.connect(timeout=30.0, reconnect=True), 
                        timeout=45.0
                    )
                    
                    connection_end_time = datetime.now()
                    connection_duration = (connection_end_time - connection_start_time).total_seconds()
                    logger.info(f"[Guild {self.guild.id}] channel.connect() completed in {connection_duration:.2f} seconds")
                    
                    # Verify connection with multiple checks
                    if self.voice_client:
                        logger.info(f"[Guild {self.guild.id}] Voice client created: {type(self.voice_client)}")
                        logger.debug(f"[Guild {self.guild.id}] Voice client attributes: {dir(self.voice_client)}")
                        print(f"🔍 Voice client created, verifying connection...")
                        
                        # Give Discord time to fully establish the connection
                        for check_attempt in range(5):  # Check up to 5 times
                            logger.debug(f"[Guild {self.guild.id}] Connection verification attempt {check_attempt + 1}/5")
                            await asyncio.sleep(1)  # Wait 1 second between checks
                            
                            # Detailed connection state logging
                            has_is_connected = hasattr(self.voice_client, 'is_connected')
                            is_connected = has_is_connected and self.voice_client.is_connected()
                            voice_channel = getattr(self.voice_client, 'channel', None)
                            
                            logger.debug(f"[Guild {self.guild.id}] Check {check_attempt + 1}: has_is_connected={has_is_connected}, is_connected={is_connected}, channel={voice_channel}")
                            
                            if has_is_connected and is_connected:
                                logger.info(f"[Guild {self.guild.id}] Connection verified successfully after {check_attempt + 1} checks")
                                logger.info(f"[Guild {self.guild.id}] Connected to voice channel: {voice_channel}")
                                print(f"✅ Successfully connected to voice channel: {channel.name}")
                                return
                            elif check_attempt < 4:  # Don't print on last attempt
                                logger.debug(f"[Guild {self.guild.id}] Connection not ready, waiting...")
                                print(f"🔄 Connection check {check_attempt + 1}/5, waiting...")
                        
                        # If we get here, connection verification failed
                        logger.error(f"[Guild {self.guild.id}] Connection verification failed after 5 seconds")
                        logger.error(f"[Guild {self.guild.id}] Final voice client state: {self.voice_client}")
                        print(f"❌ Connection verification failed after 5 seconds")
                        raise discord.errors.ClientException("Connection established but verification failed")
                    else:
                        logger.error(f"[Guild {self.guild.id}] channel.connect() returned None")
                        raise discord.errors.ClientException("Failed to create voice client")
                        
                except (asyncio.TimeoutError, discord.errors.ConnectionClosed, discord.errors.ClientException) as e:
                    logger.error(f"[Guild {self.guild.id}] Voice connection attempt {attempt + 1} failed: {type(e).__name__}: {e}")
                    logger.error(f"[Guild {self.guild.id}] Connection error traceback: {traceback.format_exc()}")
                    print(f"⚠️ Voice connection attempt {attempt + 1} failed: {type(e).__name__}: {e}")
                    
                    # Check if we actually have a working connection despite the exception
                    if self.voice_client and hasattr(self.voice_client, 'is_connected') and self.voice_client.is_connected():
                        logger.warning(f"[Guild {self.guild.id}] Exception occurred but connection appears to be working, verifying...")
                        print(f"🔍 Exception occurred but connection appears to be working, verifying...")
                        await asyncio.sleep(2)  # Give it more time
                        if self.voice_client.is_connected():
                            logger.info(f"[Guild {self.guild.id}] Connection verified despite exception")
                            print(f"✅ Connection verified despite exception")
                            return
                        else:
                            logger.warning(f"[Guild {self.guild.id}] Connection lost during verification")
                    
                    # Clean up failed connection
                    logger.debug(f"[Guild {self.guild.id}] Cleaning up failed connection")
                    await self._safe_disconnect(force=True, full_cleanup=False)
                    
                    if attempt == 0:  # Only attempt
                        # Check if this is a hosting environment limitation
                        error_str = str(e)
                        logger.error(f"[Guild {self.guild.id}] Analyzing error: {error_str}")
                        
                        if "4006" in error_str or "Session no longer valid" in error_str:
                            logger.error(f"[Guild {self.guild.id}] Detected hosting environment limitation (4006 error)")
                            raise discord.errors.ClientException(
                                "Voice connection failed due to hosting environment limitations. "
                                "This bot may not support voice features on this hosting platform."
                            )
                        else:
                            logger.error(f"[Guild {self.guild.id}] Connection failed with non-4006 error")
                            raise discord.errors.ClientException(f"Voice connection failed: {e}")
                    
        except discord.errors.ClientException:
            logger.error(f"[Guild {self.guild.id}] ClientException in connect method")
            raise  # Re-raise client exceptions as-is
        except Exception as e:
            logger.error(f"[Guild {self.guild.id}] Unexpected voice connection error: {e}")
            logger.error(f"[Guild {self.guild.id}] Unexpected error traceback: {traceback.format_exc()}")
            print(f"❌ Unexpected voice connection error: {e}")
            await self._safe_disconnect(force=True, full_cleanup=False)
            raise discord.errors.ClientException(f"Voice connection failed: {str(e)}")
        finally:
            # Always clear the connection flag
            logger.debug(f"[Guild {self.guild.id}] Clearing _connecting flag in finally block")
            self._connecting = False
            
    async def disconnect(self):
        """Disconnect from voice channel"""
        await self._safe_disconnect(force=False, full_cleanup=True)
        self.current_song = None
            
    async def add_song(self, song: Song):
        """Add a song to the queue"""
        self.queue.append(song)
        
    async def play_next(self):
        """Play the next song in queue"""
        logger.info(f"[Guild {self.guild.id}] play_next called")
        logger.debug(f"[Guild {self.guild.id}] Queue length: {len(self.queue)}")
        logger.debug(f"[Guild {self.guild.id}] Loop mode: {self.loop_mode}")
        logger.debug(f"[Guild {self.guild.id}] Current song: {self.current_song}")
        logger.debug(f"[Guild {self.guild.id}] Voice client: {self.voice_client}")
        logger.debug(f"[Guild {self.guild.id}] Is playing: {self.is_playing}")
        
        if not self.queue and self.loop_mode != "song":
            # No more songs, start auto-leave timer
            logger.info(f"[Guild {self.guild.id}] No more songs in queue, starting auto-leave timer")
            await self.start_auto_leave()
            return
            
        if self.loop_mode == "song" and self.current_song:
            # Loop current song
            logger.info(f"[Guild {self.guild.id}] Looping current song: {self.current_song.title}")
            next_song = self.current_song
        elif self.loop_mode == "queue" and not self.queue:
            # Loop queue - restart from beginning
            logger.info(f"[Guild {self.guild.id}] Looping queue - restarting from beginning")
            if hasattr(self, 'original_queue') and self.original_queue:
                logger.debug(f"[Guild {self.guild.id}] Restoring original queue: {len(self.original_queue)} songs")
                self.queue = self.original_queue.copy()
                next_song = self.queue.pop(0)
            else:
                logger.warning(f"[Guild {self.guild.id}] Queue loop requested but no original_queue found")
                await self.start_auto_leave()
                return
        else:
            # Normal play
            if not self.queue:
                logger.info(f"[Guild {self.guild.id}] Normal play but queue is empty, starting auto-leave")
                await self.start_auto_leave()
                return
            next_song = self.queue.pop(0)
            logger.info(f"[Guild {self.guild.id}] Playing next song from queue: {next_song.title}")
            
        self.current_song = next_song
        logger.debug(f"[Guild {self.guild.id}] Set current_song to: {next_song.title}")
        
        try:
            # Get stream URL
            logger.debug(f"[Guild {self.guild.id}] Getting stream URL for: {next_song.url}")
            stream_url = await self.get_stream_url(next_song.url)
            
            if not stream_url:
                logger.error(f"[Guild {self.guild.id}] Failed to get stream URL for: {next_song.title}")
                logger.info(f"[Guild {self.guild.id}] Skipping to next song")
                await self.play_next()  # Skip to next song
                return
            
            logger.debug(f"[Guild {self.guild.id}] Stream URL obtained: {stream_url[:100]}...")
                
            # Create audio source
            logger.debug(f"[Guild {self.guild.id}] Creating FFmpeg audio source")
            logger.debug(f"[Guild {self.guild.id}] FFmpeg executable: {FFMPEG_EXECUTABLE}")
            logger.debug(f"[Guild {self.guild.id}] FFmpeg options: {FFMPEG_OPTIONS}")
            
            try:
                source = discord.FFmpegPCMAudio(
                    stream_url, 
                    executable=FFMPEG_EXECUTABLE,
                    **FFMPEG_OPTIONS
                )
                logger.debug(f"[Guild {self.guild.id}] FFmpeg audio source created successfully")
            except Exception as ffmpeg_error:
                logger.error(f"[Guild {self.guild.id}] FFmpeg source creation failed: {ffmpeg_error}")
                logger.error(f"[Guild {self.guild.id}] FFmpeg error traceback: {traceback.format_exc()}")
                raise
            
            try:
                source = discord.PCMVolumeTransformer(source, volume=self.volume)
                logger.debug(f"[Guild {self.guild.id}] Volume transformer applied (volume: {self.volume})")
            except Exception as volume_error:
                logger.error(f"[Guild {self.guild.id}] Volume transformer failed: {volume_error}")
                raise
            
            # Play the song with voice client validation
            logger.debug(f"[Guild {self.guild.id}] Validating voice client for playback")
            voice_client_valid = (self.voice_client and 
                                hasattr(self.voice_client, 'is_connected') and 
                                self.voice_client.is_connected())
            
            logger.debug(f"[Guild {self.guild.id}] Voice client validation: {voice_client_valid}")
            
            if not voice_client_valid:
                logger.error(f"[Guild {self.guild.id}] Voice client not available for playback")
                logger.error(f"[Guild {self.guild.id}] Voice client state: {self.voice_client}")
                print("Voice client not available for playback")
                await self.play_next()  # Skip to next song
                return
            
            logger.info(f"[Guild {self.guild.id}] Starting audio playback for: {next_song.title}")
            
            try:
                self.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(
                    self.play_next(), _client.loop
                ))
                logger.info(f"[Guild {self.guild.id}] Audio playback started successfully")
            except Exception as play_error:
                logger.error(f"[Guild {self.guild.id}] Failed to start audio playback: {play_error}")
                logger.error(f"[Guild {self.guild.id}] Playback error traceback: {traceback.format_exc()}")
                raise
            
            self.is_playing = True
            self.is_paused = False
            self.skip_votes.clear()
            
            logger.debug(f"[Guild {self.guild.id}] Playback state updated: playing=True, paused=False")
            
            # Cancel auto-leave if it was running
            if self.auto_leave_task:
                logger.debug(f"[Guild {self.guild.id}] Cancelling auto-leave task")
                self.auto_leave_task.cancel()
                self.auto_leave_task = None
                
        except Exception as e:
            logger.error(f"[Guild {self.guild.id}] Error playing song: {e}")
            logger.error(f"[Guild {self.guild.id}] Play error traceback: {traceback.format_exc()}")
            print(f"Error playing song: {e}")
            logger.info(f"[Guild {self.guild.id}] Skipping to next song due to error")
            await self.play_next()  # Skip to next song
            
    async def get_stream_url(self, video_url: str) -> Optional[str]:
        """Get stream URL from video URL"""
        logger.debug(f"[Guild {self.guild.id}] get_stream_url called for: {video_url}")
        
        try:
            logger.debug(f"[Guild {self.guild.id}] yt-dlp options: {YDL_OPTIONS}")
            
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                logger.debug(f"[Guild {self.guild.id}] Extracting info from yt-dlp...")
                extraction_start = datetime.now()
                
                info = ydl.extract_info(video_url, download=False)
                
                extraction_end = datetime.now()
                extraction_duration = (extraction_end - extraction_start).total_seconds()
                logger.debug(f"[Guild {self.guild.id}] yt-dlp extraction completed in {extraction_duration:.2f} seconds")
                
                if not info:
                    logger.error(f"[Guild {self.guild.id}] yt-dlp returned no info")
                    return None
                
                logger.debug(f"[Guild {self.guild.id}] yt-dlp info keys: {list(info.keys())}")
                
                if 'url' in info:
                    stream_url = info['url']
                    logger.info(f"[Guild {self.guild.id}] Direct stream URL found: {stream_url[:100]}...")
                    return stream_url
                elif 'entries' in info and info['entries']:
                    logger.debug(f"[Guild {self.guild.id}] Entries found: {len(info['entries'])}")
                    first_entry = info['entries'][0]
                    if 'url' in first_entry:
                        stream_url = first_entry['url']
                        logger.info(f"[Guild {self.guild.id}] Stream URL from first entry: {stream_url[:100]}...")
                        return stream_url
                    else:
                        logger.error(f"[Guild {self.guild.id}] First entry has no URL: {list(first_entry.keys())}")
                else:
                    logger.error(f"[Guild {self.guild.id}] No URL or entries found in yt-dlp info")
                    
        except yt_dlp.DownloadError as e:
            logger.error(f"[Guild {self.guild.id}] yt-dlp download error: {e}")
            print(f"yt-dlp download error: {e}")
        except Exception as e:
            logger.error(f"[Guild {self.guild.id}] Error extracting stream URL: {e}")
            logger.error(f"[Guild {self.guild.id}] Stream extraction traceback: {traceback.format_exc()}")
            print(f"Error extracting stream URL: {e}")
            
        logger.warning(f"[Guild {self.guild.id}] Failed to extract stream URL from: {video_url}")
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
        try:
            if self.voice_client and hasattr(self.voice_client, 'is_playing') and self.voice_client.is_playing():
                self.voice_client.pause()
                self.is_paused = True
                return True
        except Exception as e:
            print(f"Warning: Error pausing playback: {e}")
        return False
            
    def resume(self):
        """Resume playback"""
        try:
            if self.voice_client and hasattr(self.voice_client, 'is_paused') and self.voice_client.is_paused():
                self.voice_client.resume()
                self.is_paused = False
                return True
        except Exception as e:
            print(f"Warning: Error resuming playback: {e}")
        return False
            
    def stop(self):
        """Stop playback"""
        try:
            if self.voice_client and hasattr(self.voice_client, 'is_playing'):
                if self.voice_client.is_playing() or (hasattr(self.voice_client, 'is_paused') and self.voice_client.is_paused()):
                    self.voice_client.stop()
        except Exception as e:
            print(f"Warning: Error stopping playback: {e}")
        finally:
            self.is_playing = False
            self.is_paused = False
        
    def skip(self):
        """Skip current song"""
        self.stop()
        
    def set_volume(self, volume: float):
        """Set playback volume (0.0 to 1.0)"""
        self.volume = max(0.0, min(1.0, volume))
        try:
            if (self.voice_client and 
                hasattr(self.voice_client, 'source') and 
                self.voice_client.source and 
                hasattr(self.voice_client.source, 'volume')):
                self.voice_client.source.volume = self.volume
                return True
        except Exception as e:
            print(f"Warning: Error setting volume: {e}")
        return False
            
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
    
    # Hosting environment
    env_info = detect_hosting_environment()
    env_status = f"🏠 {', '.join(env_info)}"
    problematic = ["Replit", "Heroku", "Railway", "Glitch", "GitHub Codespaces"]
    if any(env in env_info for env in problematic):
        env_status += "\n⚠️ May not support voice"
    embed.add_field(name="Hosting Environment", value=env_status, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.command(name="musicdebug", description="Get detailed debug information (Admin only)")
@app_commands.default_permissions(administrator=True)
@log_command
async def musicdebug(interaction: discord.Interaction):
    """Get comprehensive debug information about the music system"""
    await interaction.response.defer()
    
    try:
        debug_info = get_debug_info(interaction.guild.id)
        
        embed = discord.Embed(
            title="🔧 Music System Debug Information",
            color=discord.Color.blue()
        )
        
        # System Info
        system_info = f"**Logger Level:** {logging.getLevelName(debug_info['logger_level'])}\n"
        system_info += f"**FFmpeg Path:** `{debug_info['ffmpeg_path']}`\n"
        system_info += f"**Client Ready:** {debug_info['client_ready']}\n"
        system_info += f"**Spotify Configured:** {debug_info['spotify_configured']}\n"
        system_info += f"**Active Players:** {debug_info['active_players']}\n"
        system_info += f"**Hosting Environment:** {', '.join(debug_info['hosting_environment'])}"
        
        embed.add_field(name="📊 System Status", value=system_info, inline=False)
        
        # Player State (if exists)
        if "player_state" in debug_info:
            state = debug_info["player_state"]
            player_info = f"**Voice Client:** {state['voice_client']}\n"
            player_info += f"**Is Connected:** {state['is_connected']}\n"
            player_info += f"**Current Song:** {state['current_song'] or 'None'}\n"
            player_info += f"**Queue Length:** {state['queue_length']}\n"
            player_info += f"**Is Playing:** {state['is_playing']}\n"
            player_info += f"**Is Paused:** {state['is_paused']}\n"
            player_info += f"**Volume:** {int(state['volume'] * 100)}%\n"
            player_info += f"**Loop Mode:** {state['loop_mode']}\n"
            player_info += f"**Connecting:** {state['_connecting']}"
            
            embed.add_field(name="🎵 Player State", value=player_info, inline=False)
        else:
            embed.add_field(name="🎵 Player State", value="No active player for this guild", inline=False)
        
        # Log file info
        embed.add_field(
            name="📝 Debug Logs", 
            value="Check `music_debug.log` file for detailed logs\nUse `/musicstatus` for additional diagnostics", 
            inline=False
        )
        
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    except Exception as e:
        await interaction.followup.send(f"❌ Error getting debug info: {str(e)}", ephemeral=True)

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
    tree.add_command(musicdebug)
    tree.add_command(voicetest)
    print("🎵 Music commands loaded: /play, /pause, /resume, /skip, /stop, /queue, /nowplaying, /volume, /loop, /shuffle, /remove, /clear, /leave, /search, /musicstatus, /musicdebug, /voicetest")

# Cleanup function
async def cleanup_music_players():
    """Clean up inactive music players"""
    for guild_id, player in list(music_players.items()):
        if not player.voice_client or not player.voice_client.is_connected():
            del music_players[guild_id]
