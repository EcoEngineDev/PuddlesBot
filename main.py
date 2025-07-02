import discord
from discord import app_commands
from discord.ext import commands
import requests
import os
from keep_alive import keep_alive
from datetime import datetime, timedelta
from dateutil import parser
from database import Task, TaskCreator, get_session
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from typing import Optional, Callable, Any
import traceback
import sys
import functools
from discord.app_commands import checks
import sqlalchemy
import json

# Import the modular systems
import dice
import intmsg
import fun
import help
import inviter
import quality_manager
import tasks
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

# Initialize bot with all intents
class PuddlesBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True  # Needed for member resolution
        
        # Initialize as commands.Bot to work with Vocard
        super().__init__(command_prefix='!', intents=intents)
        self.scheduler = AsyncIOScheduler()
        
        # Initialize Vocard components if available
        if music_func and Settings:
            self.setup_vocard_settings()
    
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
        """Set up Vocard music system"""
        if not music_func or not Settings:
            print("⚠️ Vocard components not available, skipping music setup")
            return
            
        try:
            # Setup languages if available
            if hasattr(music_func, 'langs_setup'):
                music_func.langs_setup()
            
            # Connect to MongoDB (optional)
            await self.connect_music_db()
            
            # Setup IPC client (optional)
            if hasattr(music_func.settings, 'ipc_client') and IPCClient:
                self.ipc = IPCClient(self, **music_func.settings.ipc_client)
                if music_func.settings.ipc_client.get("enable", False):
                    try:
                        await self.ipc.connect()
                        print("✅ IPC client connected")
                    except Exception as e:
                        print(f"⚠️ IPC client connection failed: {e}")
            
            # Setup Voicelink NodePool (using Vocard's approach)
            if voicelink and hasattr(music_func.settings, 'nodes'):
                try:
                    # Import Lavalink components
                    import lavalink
                    
                    # Create a NodePool instance
                    self.voicelink = voicelink.NodePool()
                    
                    # Create nodes using the NodePool's create_node method
                    for node_name, node_config in music_func.settings.nodes.items():
                        try:
                            await self.voicelink.create_node(
                                bot=self,
                                **node_config
                            )
                            print(f"✅ Connected to Lavalink node: {node_name} ({node_config['host']}:{node_config['port']})")
                        except Exception as e:
                            print(f"❌ Failed to connect to node {node_name}: {e}")
                    
                    print("✅ Voicelink NodePool setup completed")
                    
                except Exception as e:
                    print(f"❌ Failed to setup Voicelink NodePool: {e}")
                    print(f"   Full error: {traceback.format_exc()}")
            
            # Load Vocard cogs
            cogs_path = os.path.join(os.path.dirname(__file__), 'MusicSystem', 'cogs')
            if os.path.exists(cogs_path):
                original_cwd = os.getcwd()
                try:
                    # Change to MusicSystem directory context for cog loading
                    music_system_path = os.path.join(os.path.dirname(__file__), 'MusicSystem')
                    os.chdir(music_system_path)
                    
                    for module in os.listdir(cogs_path):
                        if module.endswith('.py') and not module.startswith('__'):
                            try:
                                await self.load_extension(f"cogs.{module[:-3]}")
                                print(f"✅ Loaded Vocard cog: {module[:-3]}")
                            except Exception as e:
                                print(f"❌ Failed to load Vocard cog {module[:-3]}: {e}")
                    
                except Exception as e:
                    print(f"❌ Error loading cogs: {e}")
                finally:
                    # Always restore original directory
                    os.chdir(original_cwd)
            
            print("✅ Vocard music system setup completed")
            
        except Exception as e:
            print(f"❌ Failed to setup Vocard music system: {e}")
            print("Full error:", traceback.format_exc())
        
    async def setup_hook(self):
        print("Setting up bot modules...")
        try:
            # Setup non-music module systems with client references
            dice.setup_dice_system(self)
            intmsg.setup_intmsg_system(self)
            fun.setup_fun_system(self)
            help.setup_help_system(self)
            inviter.setup_inviter_system(self)
            tasks.setup_task_system(self)
            
            # Register commands from non-music modules
            dice.setup_dice_commands(self.tree)
            intmsg.setup_intmsg_commands(self.tree)
            fun.setup_fun_commands(self.tree)
            help.setup_help_commands(self.tree)
            inviter.setup_inviter_commands(self.tree)
            quality_manager.setup_quality_commands(self.tree, self)
            tasks.setup_task_commands(self.tree)
            
            # Initialize Vocard music system
            await self.setup_vocard_music()
            
            print("Syncing commands...")
            await self.tree.sync(guild=None)  # None means global sync
            print("Commands synced successfully!")
            print("✅ All commands registered successfully!")
            print("📋 Task commands: /task, /mytasks, /taskedit, /showtasks, /alltasks, /oldtasks, /tcw")
            print("💬 Interactive message commands: /intmsg, /imw, /editintmsg, /listmessages, /ticketstats, /fixdb, /testpersistence")
            print("🎲 Fun commands: /quack, /diceroll")
            print("📨 Invite tracking commands: /topinvite, /showinvites, /invitesync, /invitestats, /invitereset")
            print("🎵 Music commands: Available through Vocard cogs (/play, /skip, /pause, /resume, /stop, /queue, /volume, etc.)")
            print("🎛️ Audio quality commands: /quality, /audiostats")
            print("❓ Utility commands: /help")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
            print("Full error:", traceback.format_exc())
        
        self.scheduler.start()
        self.scheduler.add_job(self.check_due_tasks, 'interval', hours=1)
        # Add backup job to run every 6 hours
        self.scheduler.add_job(self.backup_database, 'interval', hours=6)
        
        # Removed load_persistent_views from setup_hook - now handled in on_ready with proper timing

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')
        
        # Wait a moment for Discord.py to fully load all data
        print("⏳ Waiting for Discord.py to fully load all guilds and channels...")
        await asyncio.sleep(3)
        
        # Check if all guilds are available
        unavailable_guilds = [g for g in self.guilds if g.unavailable]
        if unavailable_guilds:
            print(f"⚠️ {len(unavailable_guilds)} guilds are unavailable, waiting longer...")
            await asyncio.sleep(5)
        
        print("🔄 Starting persistence system...")
        await self.load_persistent_views()
        
        print("🔄 Initializing invite tracking system...")
        await inviter.on_ready()

    async def check_due_tasks(self):
        session = get_session()
        try:
            three_days_from_now = datetime.utcnow() + timedelta(days=3)
            tasks = session.query(Task).filter(
                Task.due_date <= three_days_from_now,
                Task.due_date > datetime.utcnow(),
                Task.completed == False
            ).all()
            
            for task in tasks:
                user = await self.fetch_user(int(task.assigned_to))
                if user:
                    embed = discord.Embed(
                        title="⚠️ Task Due Soon!",
                        description=f"Task: {task.name}\nDue Date: {task.due_date.strftime('%Y-%m-%d %H:%M UTC')}\n\nDescription:\n{task.description}",
                        color=discord.Color.yellow()
                    )
                    try:
                        await user.send(embed=embed)
                    except discord.Forbidden:
                        pass
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
        """Handle voice state updates - Vocard handles music-related voice events"""
        pass

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
        session = get_session()
        restored_messages = 0
        restored_tickets = 0
        cleaned_messages = 0
        
        print("🔄 Starting persistence restoration...")
        
        # Add debugging information about bot's access
        print(f"🤖 Bot is connected to {len(self.guilds)} guild(s):")
        for guild in self.guilds:
            print(f"   • {guild.name} (ID: {guild.id}) - {len(guild.channels)} channels")
        
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
            print(f"❌ Error loading interactive messages: {e}")
            import traceback
            traceback.print_exc()
        
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
        session = get_session()
        refreshed = 0
        
        try:
            print("🔄 Auto-refreshing interactive messages...")
            interactive_messages = session.query(InteractiveMessage).all()
            print(f"🔍 Found {len(interactive_messages)} messages to potentially refresh")
            
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
            print(f"❌ Error during auto-refresh: {e}")
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
            
        await self.process_commands(message)

# All task-related code moved to tasks.py module

# ============= BOT INITIALIZATION =============

# Initialize the bot
client = PuddlesBot()

# Keep the bot alive
keep_alive()

# Start the bot with the token
client.run(os.getenv('TOKEN')) 
