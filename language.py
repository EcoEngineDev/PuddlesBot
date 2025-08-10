import discord
from discord import app_commands
import json
import os
import functools
from typing import Callable, Any, Dict, Optional, List
from collections import defaultdict
import traceback
import asyncio

# Store reference to the client
_client = None

# Supported languages
SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "flag": "🇺🇸", "native": "English"},
    "es": {"name": "Spanish", "flag": "🇪🇸", "native": "Español"},
    "fr": {"name": "French", "flag": "🇫🇷", "native": "Français"},
    "de": {"name": "German", "flag": "🇩🇪", "native": "Deutsch"},
    "it": {"name": "Italian", "flag": "🇮🇹", "native": "Italiano"},
    "ja": {"name": "Japanese", "flag": "🇯🇵", "native": "日本語"},
    "ko": {"name": "Korean", "flag": "🇰🇷", "native": "한국어"},
    "zh": {"name": "Chinese", "flag": "🇨🇳", "native": "中文"},
    "ar": {"name": "Arabic", "flag": "🇸🇦", "native": "العربية"},
    "hi": {"name": "Hindi", "flag": "🇮🇳", "native": "हिन्दी"}
}

# Default language
DEFAULT_LANGUAGE = "en"

# Language storage
server_languages = defaultdict(lambda: DEFAULT_LANGUAGE)
user_languages = defaultdict(lambda: DEFAULT_LANGUAGE)

# Command registry for dynamic reinitialization
command_registry = {}

def setup_language_system(client):
    """Initialize the language system with client reference"""
    global _client
    _client = client
    load_language_settings()

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

def get_language_file_path(lang_code: str) -> str:
    """Get the path to a language file"""
    return f"langs/{lang_code}.json"

def load_language_file(lang_code: str) -> Dict:
    """Load a language file"""
    file_path = get_language_file_path(lang_code)
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # Return English as fallback
            return load_language_file("en")
    except Exception as e:
        print(f"Error loading language file {file_path}: {e}")
        return {}

def get_text(key: str, lang_code: str = None, **kwargs) -> str:
    """Get translated text for a key"""
    if lang_code is None:
        lang_code = DEFAULT_LANGUAGE
    
    # Load language file
    lang_data = load_language_file(lang_code)
    
    # Get the text
    text = lang_data.get(key, key)
    
    # Replace placeholders
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", str(v))
    
    return text

def get_server_language(guild_id: int) -> str:
    """Get the language setting for a server"""
    return server_languages.get(str(guild_id), DEFAULT_LANGUAGE)

def get_user_language(user_id: int) -> str:
    """Get the language setting for a user"""
    return user_languages.get(str(user_id), DEFAULT_LANGUAGE)

def set_server_language(guild_id: int, lang_code: str):
    """Set the language for a server"""
    # Validate that the language code is supported
    if lang_code not in SUPPORTED_LANGUAGES:
        print(f"Warning: Attempted to set unsupported language '{lang_code}' for server {guild_id}")
        return False
    
    server_languages[str(guild_id)] = lang_code
    save_language_settings()
    
    # Use a simple sync approach instead of aggressive reinitialization
    if _client:
        asyncio.create_task(simple_command_sync())
    
    return True

def set_user_language(user_id: int, lang_code: str):
    """Set the language for a user"""
    # Validate that the language code is supported
    if lang_code not in SUPPORTED_LANGUAGES:
        print(f"Warning: Attempted to set unsupported language '{lang_code}' for user {user_id}")
        return False
    
    user_languages[str(user_id)] = lang_code
    save_language_settings()
    
    return True

def save_language_settings():
    """Save language settings to file"""
    try:
        settings = {
            "server_languages": dict(server_languages),
            "user_languages": dict(user_languages)
        }
        with open("data/language_settings.json", "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving language settings: {e}")

def load_language_settings():
    """Load language settings from file"""
    try:
        if os.path.exists("data/language_settings.json"):
            with open("data/language_settings.json", "r", encoding="utf-8") as f:
                settings = json.load(f)
                server_languages.update(settings.get("server_languages", {}))
                user_languages.update(settings.get("user_languages", {}))
    except Exception as e:
        print(f"Error loading language settings: {e}")

# Command localization system
def register_command(command_name: str, command_func: Callable, default_name: str, default_description: str):
    """Register a command for content localization"""
    command_registry[command_name] = {
        'func': command_func,
        'default_name': default_name,
        'default_description': default_description,
        'localized_versions': {},
        'original_name': command_name  # Store the original command name
    }
    
    print(f"📝 Registered command '{command_name}' for content localization")

def get_localized_command_info(command_name: str, lang_code: str) -> tuple[str, str]:
    """Get localized name and description for a command"""
    if command_name not in command_registry:
        return command_name, "Command description not found"
    
    # Get the command info
    cmd_info = command_registry[command_name]
    
    # Check if we have a cached version for this language
    if lang_code in cmd_info['localized_versions']:
        return cmd_info['localized_versions'][lang_code]
    
    # Get translated name and description
    name_key = f"cmd_{command_name}_name"
    desc_key = f"cmd_{command_name}_description"
    
    translated_name = get_text(name_key, lang_code) or cmd_info['default_name']
    translated_description = get_text(desc_key, lang_code) or cmd_info['default_description']
    
    # Cache the result
    cmd_info['localized_versions'][lang_code] = (translated_name, translated_description)
    
    return translated_name, translated_description

async def aggressive_command_reinitialization(guild_id: int):
    """DISABLED - This function was causing commands to disappear"""
    print(f"⚠️ Aggressive reinitialization is disabled - it was causing commands to disappear")
    return
    
    try:
        guild = _client.get_guild(guild_id)
        if not guild:
            return
        
        lang_code = get_server_language(guild_id)
        print(f"🚀 AGGRESSIVE reinitialization for server {guild.name} ({guild_id}) with language {lang_code}")
        
        # Get the command tree
        tree = _client.tree
        
        # Step 1: Clear all commands for this guild
        try:
            tree.clear_commands(guild=guild)
            print(f"🗑️ Cleared all commands for {guild.name}")
        except Exception as e:
            print(f"⚠️ Warning clearing commands for {guild.name}: {e}")
        
        # Step 2: Wait for Discord to process
        await asyncio.sleep(2)
        
        # Step 3: Re-add all commands with localized names
        for command_name, cmd_info in command_registry.items():
            try:
                # Get localized name and description
                localized_name, localized_description = get_localized_command_info(command_name, lang_code)
                
                print(f"🔄 Recreating {command_name} as {localized_name} for {guild.name}")
                
                # Create a new command with localized info
                new_command = app_commands.Command(
                    name=localized_name,
                    description=localized_description,
                    callback=cmd_info['func'],
                    parent=None
                )
                
                # Add the new command to the guild
                tree.add_command(new_command, guild=guild)
                
            except Exception as e:
                print(f"❌ Error recreating command {command_name} for {guild.name}: {e}")
        
        # Step 4: Force sync for this guild
        try:
            await tree.sync(guild=guild)
            print(f"✅ Synced localized commands for {guild.name}")
        except Exception as sync_error:
            print(f"⚠️ Sync warning for {guild.name}: {sync_error}")
        
        # Step 5: Force global sync as backup
        try:
            await tree.sync()
            print(f"✅ Global sync completed for {guild.name}")
        except Exception as global_sync_error:
            print(f"⚠️ Global sync warning for {guild.name}: {global_sync_error}")
        
        print(f"🎯 AGGRESSIVE reinitialization completed for {guild.name}")
        
    except Exception as e:
        print(f"❌ Error in aggressive reinitialization for server {guild_id}: {e}")
        import traceback
        traceback.print_exc()

async def aggressive_command_reinitialization_for_all_guilds():
    """DISABLED - This function was causing commands to disappear"""
    print(f"⚠️ Aggressive reinitialization for all guilds is disabled - it was causing commands to disappear")
    return
    
    try:
        print(f"🚀 Starting AGGRESSIVE reinitialization for ALL {len(_client.guilds)} guilds...")
        
        # Get the command tree
        tree = _client.tree
        
        # Step 1: Clear ALL commands globally
        try:
            tree.clear_commands(guild=None)
            print(f"🗑️ Cleared ALL commands globally")
        except Exception as e:
            print(f"⚠️ Warning clearing all commands: {e}")
        
        # Step 2: Wait for Discord to process
        await asyncio.sleep(2)
        
        # Step 3: Re-add commands for each guild with their specific language
        for guild in _client.guilds:
            try:
                lang_code = get_server_language(guild.id)
                print(f"🔄 Processing guild {guild.name} with language {lang_code}")
                
                # Re-add all commands with localized names for this guild
                for command_name, cmd_info in command_registry.items():
                    try:
                        # Get localized name and description
                        localized_name, localized_description = get_localized_command_info(command_name, lang_code)
                        
                        print(f"   🔄 Recreating {command_name} as {localized_name}")
                        
                        # Create a new command with localized info
                        new_command = app_commands.Command(
                            name=localized_name,
                            description=localized_description,
                            callback=cmd_info['func'],
                            parent=None
                        )
                        
                        # Add the new command to the guild
                        tree.add_command(new_command, guild=guild)
                        
                    except Exception as e:
                        print(f"   ❌ Error recreating command {command_name} for {guild.name}: {e}")
                
            except Exception as e:
                print(f"❌ Error processing guild {guild.name}: {e}")
                continue
        
        # Step 4: Force global sync with timeout
        try:
            print("🔄 Syncing all localized commands...")
            # Add timeout to prevent hanging
            sync_task = asyncio.create_task(tree.sync())
            try:
                await asyncio.wait_for(sync_task, timeout=20.0)  # 20 second timeout
                print(f"✅ Global sync completed for all guilds")
            except asyncio.TimeoutError:
                print(f"⚠️ Global sync timed out after 20 seconds")
                sync_task.cancel()
                # Continue anyway - commands may still work
        except Exception as sync_error:
            print(f"⚠️ Global sync warning: {sync_error}")
        
        print(f"🎯 AGGRESSIVE reinitialization completed for ALL guilds")
        
    except Exception as e:
        print(f"❌ Error in aggressive reinitialization for all guilds: {e}")
        import traceback
        traceback.print_exc()

async def conservative_command_reinitialization():
    """Conservative approach - update commands without clearing everything"""
    if not _client:
        return
    
    try:
        print(f"🔄 Starting CONSERVATIVE reinitialization for {len(_client.guilds)} guilds...")
        
        # Get the command tree
        tree = _client.tree
        
        # Instead of clearing all commands, just update existing ones
        for guild in _client.guilds:
            try:
                lang_code = get_server_language(guild.id)
                print(f"🔄 Updating commands for guild {guild.name} with language {lang_code}")
                
                # Update each registered command
                for command_name, cmd_info in command_registry.items():
                    try:
                        # Get localized name and description
                        localized_name, localized_description = get_localized_command_info(command_name, lang_code)
                        
                        # Check if command already exists with this name
                        existing_command = tree.get_command(localized_name, guild=guild)
                        if existing_command:
                            print(f"   ✅ Command {localized_name} already exists for {guild.name}")
                            continue
                        
                        # Check if command exists with original name
                        original_command = tree.get_command(command_name, guild=guild)
                        if original_command and command_name != localized_name:
                            # Remove the old command
                            tree.remove_command(command_name, guild=guild)
                            print(f"   🗑️ Removed old command {command_name} from {guild.name}")
                        
                        # Create new command with localized info
                        new_command = app_commands.Command(
                            name=localized_name,
                            description=localized_description,
                            callback=cmd_info['func'],
                            parent=None
                        )
                        
                        # Add the new command to the guild
                        tree.add_command(new_command, guild=guild)
                        print(f"   ➕ Added localized command {localized_name} to {guild.name}")
                        
                    except Exception as e:
                        print(f"   ❌ Error updating command {command_name} for {guild.name}: {e}")
                
            except Exception as e:
                print(f"❌ Error processing guild {guild.name}: {e}")
                continue
        
        # Sync with timeout
        try:
            print("🔄 Syncing updated commands...")
            sync_task = asyncio.create_task(tree.sync())
            try:
                await asyncio.wait_for(sync_task, timeout=15.0)  # 15 second timeout
                print(f"✅ Conservative sync completed")
            except asyncio.TimeoutError:
                print(f"⚠️ Conservative sync timed out after 15 seconds")
                sync_task.cancel()
        except Exception as sync_error:
            print(f"⚠️ Conservative sync warning: {sync_error}")
        
        print(f"🎯 CONSERVATIVE reinitialization completed")
        
    except Exception as e:
        print(f"❌ Error in conservative reinitialization: {e}")
        import traceback
        traceback.print_exc()

async def ensure_commands_registered():
    """Simple approach - just ensure commands are registered and do a basic sync"""
    if not _client:
        return
    
    try:
        print(f"🔄 Ensuring commands are registered for {len(_client.guilds)} guilds...")
        
        # Get the command tree
        tree = _client.tree
        
        # Just log what commands we have registered
        print(f"📋 Registered commands in registry: {list(command_registry.keys())}")
        
        # Check what commands are in the tree
        tree_commands = list(tree.get_commands())
        print(f"📋 Commands in tree: {[cmd.name for cmd in tree_commands]}")
        
        # Do a simple sync with timeout
        try:
            print("🔄 Performing simple command sync...")
            sync_task = asyncio.create_task(tree.sync())
            try:
                synced = await asyncio.wait_for(sync_task, timeout=10.0)  # 10 second timeout
                print(f"✅ Simple sync completed - {len(synced)} commands synced")
            except asyncio.TimeoutError:
                print(f"⚠️ Simple sync timed out after 10 seconds")
                sync_task.cancel()
                print("⚠️ Continuing without sync - commands may still work")
        except Exception as sync_error:
            print(f"⚠️ Simple sync warning: {sync_error}")
        
        print(f"🎯 Simple command registration completed")
        
    except Exception as e:
        print(f"❌ Error in simple command registration: {e}")
        import traceback
        traceback.print_exc()

async def simple_command_sync():
    """Simple command sync without clearing commands"""
    if not _client:
        return
    
    try:
        print("🔄 Performing simple command sync after language change...")
        
        # Get the command tree
        tree = _client.tree
        
        # Just do a simple sync - don't clear or recreate commands
        try:
            sync_task = asyncio.create_task(tree.sync())
            synced = await asyncio.wait_for(sync_task, timeout=10.0)
            print(f"✅ Language change sync completed - {len(synced)} commands available")
        except asyncio.TimeoutError:
            print(f"⚠️ Language change sync timed out")
        except Exception as sync_error:
            print(f"⚠️ Language change sync warning: {sync_error}")
        
    except Exception as e:
        print(f"❌ Error in simple command sync: {e}")

async def reinitialize_commands_for_server(guild_id: int):
    """Reinitialize commands for a specific server with the server's language"""
    if not _client:
        return
    
    try:
        guild = _client.get_guild(guild_id)
        if not guild:
            return
        
        lang_code = get_server_language(guild_id)
        print(f"🔄 Reinitializing commands for server {guild.name} ({guild_id}) with language {lang_code}")
        
        # Get the command tree
        tree = _client.tree
        
        # Force a complete command sync for this guild
        try:
            # First, sync with Discord to ensure we have the latest state
            await tree.sync(guild=guild)
            print(f"✅ Initial sync completed for {guild.name}")
        except Exception as sync_error:
            print(f"⚠️ Initial sync warning for {guild.name}: {sync_error}")
        
        # Wait a moment for Discord to process
        await asyncio.sleep(1)
        
        # Now force a global sync to ensure all commands are updated
        try:
            await tree.sync()
            print(f"✅ Global sync completed for {guild.name}")
        except Exception as global_sync_error:
            print(f"⚠️ Global sync warning for {guild.name}: {global_sync_error}")
        
        print(f"🎯 Command reinitialization completed for server {guild.name}")
        
    except Exception as e:
        print(f"❌ Error reinitializing commands for server {guild_id}: {e}")
        import traceback
        traceback.print_exc()

async def reinitialize_all_commands():
    """Reinitialize commands for all servers"""
    if not _client:
        return
    
    try:
        for guild in _client.guilds:
            await reinitialize_commands_for_server(guild.id)
    except Exception as e:
        print(f"Error reinitializing all commands: {e}")

async def force_command_recreation():
    """Force recreation of all commands with current language settings"""
    if not _client:
        return
    
    try:
        print("🚀 Force recreating all commands with current language settings...")
        
        # Get the command tree
        tree = _client.tree
        
        # Clear all existing commands
        tree.clear_commands(guild=None)
        print("🗑️ Cleared all existing commands")
        
        # Wait for Discord to process
        await asyncio.sleep(2)
        
        # Re-add all commands with current language settings
        for guild in _client.guilds:
            lang_code = get_server_language(guild.id)
            print(f"🔄 Recreating commands for {guild.name} with language {lang_code}")
            
            # Re-add commands to the tree
            # This will be handled by the individual command setup functions
            # which should be called again after clearing
        
        # Force a global sync
        await tree.sync()
        print("✅ Force command recreation completed")
        
    except Exception as e:
        print(f"❌ Error in force command recreation: {e}")
        import traceback
        traceback.print_exc()

async def create_localized_commands():
    """Create new commands with localized names and descriptions"""
    if not _client:
        return
    
    try:
        print("🎯 Creating localized commands...")
        
        # Get the command tree
        tree = _client.tree
        
        # For each registered command, create a new command with localized info
        for command_name, cmd_info in command_registry.items():
            try:
                # Get the current language for the first guild (or default to English)
                lang_code = "en"  # Default
                if _client.guilds:
                    lang_code = get_server_language(_client.guilds[0].id)
                
                # Get localized name and description
                localized_name, localized_description = get_localized_command_info(command_name, lang_code)
                
                print(f"🔄 Creating localized command: {command_name} -> {localized_name}")
                
                # Create a new command with the localized name and description
                new_command = app_commands.Command(
                    name=localized_name,
                    description=localized_description,
                    callback=cmd_info['func'],
                    parent=None
                )
                
                # Add the new command to the tree
                tree.add_command(new_command)
                
            except Exception as e:
                print(f"❌ Error creating localized command {command_name}: {e}")
        
        # Sync the commands
        await tree.sync()
        print("✅ Localized commands created and synced")
        
    except Exception as e:
        print(f"❌ Error in create_localized_commands: {e}")
        import traceback
        traceback.print_exc()

class LanguageSelect(discord.ui.Select):
    def __init__(self, is_server_setting: bool = True):
        self.is_server_setting = is_server_setting
        
        options = []
        for code, info in SUPPORTED_LANGUAGES.items():
            options.append(
                discord.SelectOption(
                    label=f"{info['flag']} {info['name']}",
                    description=info['native'],
                    value=code
                )
            )
        
        super().__init__(
            placeholder="Select your preferred language...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        selected_lang = self.values[0]
        
        if self.is_server_setting:
            # Server setting
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message(
                    "❌ Only administrators can change server language settings!",
                    ephemeral=True
                )
                return
            
            set_server_language(interaction.guild_id, selected_lang)
            lang_info = SUPPORTED_LANGUAGES[selected_lang]
            
            embed = discord.Embed(
                title="🌐 Server Language Updated",
                description=f"Server language has been set to **{lang_info['flag']} {lang_info['name']}**",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Note",
                value="This setting affects server-wide messages and features. Commands will be reinitialized with the new language.",
                inline=False
            )
            
        else:
            # User setting
            set_user_language(interaction.user.id, selected_lang)
            lang_info = SUPPORTED_LANGUAGES[selected_lang]
            
            embed = discord.Embed(
                title="🌐 Personal Language Updated",
                description=f"Your language has been set to **{lang_info['flag']} {lang_info['name']}**",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Note",
                value="This setting affects your personal interactions with the bot.",
                inline=False
            )
        
        await interaction.response.edit_message(embed=embed, view=None)

class LanguageView(discord.ui.View):
    def __init__(self, is_server_setting: bool = True):
        super().__init__(timeout=300)
        self.add_item(LanguageSelect(is_server_setting))

@app_commands.command(
    name="language",
    description="Set server language (Admin only)"
)
@log_command
async def language(interaction: discord.Interaction):
    """Set server language - admin only"""
    
    # Check permissions - admin only
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ Only administrators can change server language settings!",
            ephemeral=True
        )
        return
    
    # Get current server language
    current_lang = get_server_language(interaction.guild_id)
    current_lang_info = SUPPORTED_LANGUAGES.get(current_lang, SUPPORTED_LANGUAGES[DEFAULT_LANGUAGE])
    
    embed = discord.Embed(
        title="🌐 Server Language Settings",
        description="Select the language for server-wide messages and features.",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="Current Language",
        value=f"{current_lang_info['flag']} {current_lang_info['name']} ({current_lang_info['native']})",
        inline=False
    )
    
    embed.add_field(
        name="Available Languages",
        value="Select from the dropdown below to change your language preference.",
        inline=False
    )
    
    view = LanguageView(is_server_setting=True)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

def setup_language_commands(tree: app_commands.CommandTree):
    """Setup language management commands"""
    tree.add_command(language)
    
    # Register the language command for localization
    register_command("language", language, "language", "Set server language (Admin only)")
    
    print("✅ Language commands loaded: /language")

# Create default language files if they don't exist
def create_default_language_files():
    """Create default language files only if they don't exist"""
    os.makedirs("langs", exist_ok=True)
    
    # Only create English file if it doesn't exist
    if not os.path.exists("langs/en.json"):
        print("📝 Creating default English language file...")
        
        # Basic English translations (minimal set)
        en_translations = {
            "welcome_title": "Welcome to {server_name}!",
            "welcome_description": "Thanks for joining our community!",
            "welcome_language_prompt": "Please select your preferred language:",
            "welcome_setup_complete": "Setup complete! Enjoy your stay!",
            "language_updated": "Language updated successfully!",
            "cooldown_active": "Cooldown active! Try again in {time}",
            "error_occurred": "An error occurred. Please try again!",
            "no_permission": "You don't have permission to do that!",
            "fortune_cookie_title": "🥠 Fortune Cookie",
            "fortune_cookie_footer": "Fortune for {user_name} - don't take these seriously lol",
            "quack_title": "Quack! 🦆",
            "coinflip_title": "🪙 Coin Flip Result",
            "coinflip_description": "🪙 ← **The coin landed on {result}!**",
            "meme_title": "Random Meme",
            "meme_footer": "😂 Enjoy your meme! • Powered by meme-api.com",
            
            # Command localizations
            "cmd_language_name": "language",
            "cmd_language_description": "Set server language (Admin only)",
            "cmd_quack_name": "quack",
            "cmd_quack_description": "Get a random duck image! 🦆",
            "cmd_coinflip_name": "coinflip",
            "cmd_coinflip_description": "Flip a coin! Heads or Tails? 🪙",
            "cmd_meme_name": "meme",
            "cmd_meme_description": "Get a random meme to brighten your day! 😂",
            "cmd_fortunecookie_name": "fortunecookie",
            "cmd_fortunecookie_description": "Get a random fortune from a fortune cookie! 🥠 (3 hour cooldown)",
            "cmd_help_name": "help",
            "cmd_help_description": "Get help with bot commands",
            "cmd_task_name": "task",
            "cmd_task_description": "Create a new task",
            "cmd_mytasks_name": "mytasks",
            "cmd_mytasks_description": "View your assigned tasks",
            "cmd_showtasks_name": "showtasks",
            "cmd_showtasks_description": "Show tasks assigned to a user",
            "cmd_alltasks_name": "alltasks",
            "cmd_alltasks_description": "Show all active tasks in the server",
            "cmd_oldtasks_name": "oldtasks",
            "cmd_oldtasks_description": "Show completed tasks for a user",
            "cmd_snipe_name": "snipe",
            "cmd_snipe_description": "Claim credit for completed tasks",
            "cmd_setsnipe_name": "setsnipe",
            "cmd_setsnipe_description": "Set the snipe request channel (Admin)",
            "cmd_clearsnipes_name": "clearsnipes",
            "cmd_clearsnipes_description": "Clear pending snipe requests (Admin)",
            "cmd_tcw_name": "tcw",
            "cmd_tcw_description": "Manage task creator whitelist (Admin)",
            "cmd_intmsg_name": "intmsg",
            "cmd_intmsg_description": "Create interactive messages with buttons",
            "cmd_editintmsg_name": "editintmsg",
            "cmd_editintmsg_description": "Edit existing interactive messages (Staff)",
            "cmd_listmessages_name": "listmessages",
            "cmd_listmessages_description": "List all interactive messages (Staff)",
            "cmd_ticketstats_name": "ticketstats",
            "cmd_ticketstats_description": "View ticket statistics (Staff)",
            "cmd_imw_name": "imw",
            "cmd_imw_description": "Manage interactive message whitelist (Admin)",
            "cmd_rank_name": "rank",
            "cmd_rank_description": "View user rank card",
            "cmd_top_name": "top",
            "cmd_top_description": "View server leaderboard",
            "cmd_setxp_name": "setxp",
            "cmd_setxp_description": "Set user XP (Admin)",
            "cmd_setlevel_name": "setlevel",
            "cmd_setlevel_description": "Set user level (Admin)",
            "cmd_lvlreset_name": "lvlreset",
            "cmd_lvlreset_description": "Reset user levels (Admin)",
            "cmd_lvlconfig_name": "lvlconfig",
            "cmd_lvlconfig_description": "Configure leveling system (Admin)",
            "cmd_testxp_name": "testxp",
            "cmd_testxp_description": "Test XP assignment (Admin)",
            "cmd_testvoice_name": "testvoice",
            "cmd_testvoice_description": "Test voice XP (Admin)",
            "cmd_debugxp_name": "debugxp",
            "cmd_debugxp_description": "Debug XP system (Admin)",
            "cmd_topinvite_name": "topinvite",
            "cmd_topinvite_description": "Show top inviters",
            "cmd_showinvites_name": "showinvites",
            "cmd_showinvites_description": "Show invite statistics for a user",
            "cmd_resetinvites_name": "resetinvites",
            "cmd_resetinvites_description": "Reset all invite data (Admin)",
            "cmd_editinvites_name": "editinvites",
            "cmd_editinvites_description": "Edit user invite statistics (Admin)",
            "cmd_invitesync_name": "invitesync",
            "cmd_invitesync_description": "Manually sync invite data (Admin)",
            "cmd_invitestats_name": "invitestats",
            "cmd_invitestats_description": "Server invite statistics (Admin)",
            "cmd_invitereset_name": "invitereset",
            "cmd_invitereset_description": "Reset invite tracking tables (Admin)",
            "cmd_invw_name": "invw",
            "cmd_invw_description": "Manage invite admin whitelist (Admin)",
            "cmd_play_name": "play",
            "cmd_play_description": "Play music from various platforms",
            "cmd_pause_name": "pause",
            "cmd_pause_description": "Pause the current track",
            "cmd_resume_name": "resume",
            "cmd_resume_description": "Resume the current track",
            "cmd_skip_name": "skip",
            "cmd_skip_description": "Skip to the next track",
            "cmd_back_name": "back",
            "cmd_back_description": "Go back to the previous track",
            "cmd_stop_name": "stop",
            "cmd_stop_description": "Stop playing and clear the queue",
            "cmd_leave_name": "leave",
            "cmd_leave_description": "Leave the voice channel",
            "cmd_queue_name": "queue",
            "cmd_queue_description": "View the current music queue",
            "cmd_shuffle_name": "shuffle",
            "cmd_shuffle_description": "Shuffle the current queue",
            "cmd_loop_name": "loop",
            "cmd_loop_description": "Set loop mode (off/track/queue)",
            "cmd_nowplaying_name": "nowplaying",
            "cmd_nowplaying_description": "Show the currently playing track",
            "cmd_volume_name": "volume",
            "cmd_volume_description": "Adjust music volume (0-100)",
            "cmd_quality_name": "quality",
            "cmd_quality_description": "Manage audio quality settings (Admin)",
            "cmd_audiostats_name": "audiostats",
            "cmd_audiostats_description": "Show audio performance metrics",
            "cmd_search_name": "search",
            "cmd_search_description": "Search for music across all platforms",
            "cmd_profile_name": "profile",
            "cmd_profile_description": "View your or someone else's profile",
            "cmd_user_name": "user",
            "cmd_user_description": "Show user information",
            "cmd_avatar_name": "avatar",
            "cmd_avatar_description": "Get a user's avatar",
            "cmd_server_name": "server",
            "cmd_server_description": "Show server information",
            "cmd_roles_name": "roles",
            "cmd_roles_description": "List server roles and member counts",
            "cmd_moveme_name": "moveme",
            "cmd_moveme_description": "Move to another voice channel",
            "cmd_ban_name": "ban",
            "cmd_ban_description": "Ban a member (Admin)",
            "cmd_kick_name": "kick",
            "cmd_kick_description": "Kick a member (Admin)",
            "cmd_purge_name": "purge",
            "cmd_purge_description": "Delete messages (Staff)",
            "cmd_disable_name": "disable",
            "cmd_disable_description": "Disable bot features (Admin)",
            "cmd_enable_name": "enable",
            "cmd_enable_description": "Enable bot features (Admin)",
            "cmd_features_name": "features",
            "cmd_features_description": "View feature status",
            "cmd_openchat_name": "openchat",
            "cmd_openchat_description": "Manage OpenChat system",
            "cmd_msg_name": "msg",
            "cmd_msg_description": "Send messages to channels (Admin)",
            "cmd_fixdb_name": "fixdb",
            "cmd_fixdb_description": "Fix database issues (Admin)",
            "cmd_testpersistence_name": "testpersistence",
            "cmd_testpersistence_description": "Test persistence system (Admin)",
            "cmd_diceroll_name": "diceroll",
            "cmd_diceroll_description": "Roll dice with customizable sides",
            "cmd_multidimensionaltravel_name": "multidimensionaltravel",
            "cmd_multidimensionaltravel_description": "Get invites to opted-in servers (Owner only)",
            "cmd_gigaop_name": "gigaop",
            "cmd_gigaop_description": "Grant admin permissions for debugging (Owner only)"
        }
        
        with open("langs/en.json", "w", encoding="utf-8") as f:
            json.dump(en_translations, f, indent=2, ensure_ascii=False)
        print("✅ Created langs/en.json")
    
    # Check for other language files and create minimal versions if they don't exist
    for lang_code in SUPPORTED_LANGUAGES:
        if lang_code != "en" and not os.path.exists(f"langs/{lang_code}.json"):
            print(f"📝 Creating minimal {lang_code}.json file...")
            
            # Create minimal file with just a few basic translations
            minimal_translations = {
                "welcome_title": "Welcome to {server_name}!",
                "welcome_description": "Thanks for joining our community!",
                "language_updated": "Language updated successfully!",
                "error_occurred": "An error occurred. Please try again!",
                "no_permission": "You don't have permission to do that!"
            }
            
            with open(f"langs/{lang_code}.json", "w", encoding="utf-8") as f:
                json.dump(minimal_translations, f, indent=2, ensure_ascii=False)
            print(f"✅ Created langs/{lang_code}.json (minimal)")
    
    print("🌐 Language file initialization complete!")

# Initialize default files
create_default_language_files()

__all__ = [
    'setup_language_system', 
    'setup_language_commands', 
    'get_text', 
    'get_server_language', 
    'get_user_language',
    'set_server_language',
    'set_user_language',
    'SUPPORTED_LANGUAGES',
    'register_command',
    'get_localized_command_info',
    'ensure_commands_registered',
    'simple_command_sync'
] 