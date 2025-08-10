import discord
from discord import app_commands
from discord.ext import commands
from database import get_session, DisabledFeatures
from datetime import datetime
import functools
import traceback

# Store reference to the client
_client = None

# Define available features that can be disabled
DISABLEABLE_FEATURES = {
    "leveling": {
        "name": "Leveling System",
        "description": "XP gain and leveling features",
        "commands": ["rank", "top", "testxp", "testvoice", "voicestatus", "setlevel", "lvlreset", "lvlconfig", "setxp"],
        "systems": ["message_xp", "voice_xp"]
    },
    "ai_chat": {
        "name": "AI Chat System",
        "description": "AI responses when bot is mentioned",
        "systems": ["bot_mention_responses"]
    },
    "openchat": {
        "name": "OpenChat System",
        "description": "Cross-server chat communication",
        "commands": ["openchat"],
        "systems": ["cross_server_chat"]
    },
    "music": {
        "name": "Music System",
        "description": "Music playback and related commands",
        "commands": ["play", "pause", "skip", "queue", "stop", "volume"]
    },
    "tickets": {
        "name": "Ticket System",
        "description": "Support ticket creation and management",
        "commands": ["ticket", "close", "adduser", "removeuser"]
    },
    "tasks": {
        "name": "Task System",
        "description": "Task creation and management",
        "commands": ["task", "tasks", "taskdue", "taskcomplete"]
    },
    "fun": {
        "name": "Fun Commands",
        "description": "Entertainment commands",
        "commands": ["coinflip", "roll", "8ball"]
    }
}

def setup_disable_system(client):
    """Initialize the disable system with client reference"""
    global _client
    _client = client

def log_command(func):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        try:
            print(f"Executing disable command: {func.__name__}")
            print(f"Command called by: {interaction.user.name}")
            return await func(interaction, *args, **kwargs)
        except Exception as e:
            print(f"Error in {func.__name__}:")
            print(traceback.format_exc())
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"An error occurred while processing the command. Error: {str(e)}",
                    ephemeral=True
                )
    return wrapper

async def is_feature_disabled(guild_id: int, feature_name: str) -> bool:
    """Check if a feature is disabled in a guild"""
    session = get_session('global')
    try:
        disabled = session.query(DisabledFeatures).filter_by(
            server_id=str(guild_id),
            feature_name=feature_name
        ).first()
        return bool(disabled)
    finally:
        session.close()

def setup_disable_commands(tree: app_commands.CommandTree):
    """Setup disable system commands"""
    
    @tree.command(
        name="disable",
        description="Disable bot features for this server (Admin only)"
    )
    @app_commands.describe(
        feature="Feature to disable",
        reason="Optional reason for disabling"
    )
    @app_commands.choices(feature=[
        app_commands.Choice(name=info["name"], value=key)
        for key, info in DISABLEABLE_FEATURES.items()
    ])
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def disable(
        interaction: discord.Interaction,
        feature: str,
        reason: str = None
    ):
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        # Check if user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                language.get_text("disable_admin_only", user_lang),
                ephemeral=True
            )
            return
            
        session = get_session('global')
        try:
            # Check if already disabled
            existing = session.query(DisabledFeatures).filter_by(
                server_id=str(interaction.guild_id),
                feature_name=feature
            ).first()
            
            if existing:
                await interaction.response.send_message(
                    language.get_text("disable_already_disabled", user_lang, feature=DISABLEABLE_FEATURES[feature]['name']),
                    ephemeral=True
                )
                return
                
            # Add to disabled features
            disabled = DisabledFeatures(
                server_id=str(interaction.guild_id),
                feature_name=feature,
                disabled_by=str(interaction.user.id),
                disabled_at=datetime.utcnow(),
                reason=reason
            )
            session.add(disabled)
            session.commit()
            
            # Create response embed
            embed = discord.Embed(
                title=language.get_text("disable_success_title", user_lang),
                description=language.get_text("disable_success_description", user_lang, feature=DISABLEABLE_FEATURES[feature]['name']),
                color=discord.Color.red()
            )
            
            embed.add_field(
                name=language.get_text("disable_details", user_lang),
                value=f"**{language.get_text('disable_feature', user_lang)}:** {DISABLEABLE_FEATURES[feature]['name']}\n"
                      f"**{language.get_text('disable_description', user_lang)}:** {DISABLEABLE_FEATURES[feature]['description']}\n"
                      f"**{language.get_text('disable_disabled_by', user_lang)}:** {interaction.user.mention}\n"
                      f"**{language.get_text('disable_reason', user_lang)}:** {reason or language.get_text('disable_no_reason', user_lang)}",
                inline=False
            )
            
            if "commands" in DISABLEABLE_FEATURES[feature]:
                embed.add_field(
                    name=language.get_text("disable_affected_commands", user_lang),
                    value="• " + "\n• ".join(f"`/{cmd}`" for cmd in DISABLEABLE_FEATURES[feature]["commands"]),
                    inline=False
                )
                
            embed.add_field(
                name=language.get_text("disable_note", user_lang),
                value=language.get_text("disable_enable_note", user_lang),
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(
                language.get_text("disable_error", user_lang, error=str(e)),
                ephemeral=True
            )
        finally:
            session.close()
            
    @tree.command(
        name="enable",
        description="Re-enable previously disabled bot features (Admin only)"
    )
    @app_commands.describe(
        feature="Feature to enable"
    )
    @app_commands.choices(feature=[
        app_commands.Choice(name=info["name"], value=key)
        for key, info in DISABLEABLE_FEATURES.items()
    ])
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def enable(interaction: discord.Interaction, feature: str):
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        # Check if user has administrator permissions
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                language.get_text("enable_admin_only", user_lang),
                ephemeral=True
            )
            return
            
        session = get_session('global')
        try:
            # Check if feature is disabled
            disabled = session.query(DisabledFeatures).filter_by(
                server_id=str(interaction.guild_id),
                feature_name=feature
            ).first()
            
            if not disabled:
                await interaction.response.send_message(
                    language.get_text("enable_not_disabled", user_lang, feature=DISABLEABLE_FEATURES[feature]['name']),
                    ephemeral=True
                )
                return
                
            # Re-enable the feature
            session.delete(disabled)
            session.commit()
            
            embed = discord.Embed(
                title=language.get_text("enable_success_title", user_lang),
                description=language.get_text("enable_success_description", user_lang, feature=DISABLEABLE_FEATURES[feature]['name']),
                color=discord.Color.green()
            )
            
            # Add feature details
            embed.add_field(
                name=language.get_text("disable_details", user_lang),
                value=f"**{language.get_text('disable_feature', user_lang)}:** {DISABLEABLE_FEATURES[feature]['name']}\n"
                      f"**{language.get_text('disable_description', user_lang)}:** {DISABLEABLE_FEATURES[feature]['description']}\n"
                      f"**{language.get_text('disable_disabled_by', user_lang)}:** {interaction.user.mention}",
                inline=False
            )
            
            if "commands" in DISABLEABLE_FEATURES[feature]:
                embed.add_field(
                    name=language.get_text("enable_available_commands", user_lang),
                    value="• " + "\n• ".join(f"`/{cmd}`" for cmd in DISABLEABLE_FEATURES[feature]["commands"]),
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(
                language.get_text("enable_error", user_lang, error=str(e)),
                ephemeral=True
            )
        finally:
            session.close()
            
    @tree.command(
        name="features",
        description="View status of all bot features"
    )
    @log_command
    async def features(interaction: discord.Interaction):
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        session = get_session('global')
        try:
            # Get all disabled features for this server
            disabled = session.query(DisabledFeatures).filter_by(
                server_id=str(interaction.guild_id)
            ).all()
            disabled_features = {d.feature_name: d for d in disabled}
            
            embed = discord.Embed(
                title=language.get_text("features_title", user_lang),
                description=language.get_text("features_description", user_lang, server_name=interaction.guild.name),
                color=discord.Color.blue()
            )
            
            for feature_id, info in DISABLEABLE_FEATURES.items():
                status = language.get_text("features_disabled", user_lang) if feature_id in disabled_features else language.get_text("features_enabled", user_lang)
                value = f"**Status:** {status}\n**Description:** {info['description']}"
                
                if feature_id in disabled_features:
                    disabled_info = disabled_features[feature_id]
                    value += f"\n**{language.get_text('disable_disabled_by', user_lang)}:** <@{disabled_info.disabled_by}>"
                    if disabled_info.reason:
                        value += f"\n**{language.get_text('disable_reason', user_lang)}:** {disabled_info.reason}"
                        
                embed.add_field(
                    name=info["name"],
                    value=value,
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(
                language.get_text("error_general", user_lang, error=str(e)),
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
        name="disabled",
        description="View currently disabled features in this server (Admin only)"
    )
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def disabled(interaction: discord.Interaction):
        """Show list of currently disabled features"""
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                language.get_text("disabled_admin_only", user_lang),
                ephemeral=True
            )
            return
            
        session = get_session('global')
        try:
            # Get all disabled features
            disabled = session.query(DisabledFeatures).filter_by(
                server_id=str(interaction.guild_id)
            ).all()
            
            if not disabled:
                await interaction.response.send_message(
                    language.get_text("disabled_none", user_lang),
                    ephemeral=True
                )
                return
                
            embed = discord.Embed(
                title=language.get_text("disabled_title", user_lang),
                description=language.get_text("disabled_description", user_lang, server_name=interaction.guild.name),
                color=discord.Color.red()
            )
            
            for item in disabled:
                if item.feature_name in DISABLEABLE_FEATURES:
                    feature_info = DISABLEABLE_FEATURES[item.feature_name]
                    value = f"**{language.get_text('disable_description', user_lang)}:** {feature_info['description']}\n"
                    value += f"**{language.get_text('disabled_by', user_lang)}:** <@{item.disabled_by}>\n"
                    if item.reason:
                        value += f"**{language.get_text('disabled_reason', user_lang)}:** {item.reason}\n"
                    if "commands" in feature_info:
                        value += f"**{language.get_text('disable_affected_commands', user_lang)}:**\n• " + "\n• ".join(f"`/{cmd}`" for cmd in feature_info["commands"])
                    
                    embed.add_field(
                        name=feature_info["name"],
                        value=value,
                        inline=False
                    )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(
                language.get_text("error_general", user_lang, error=str(e)),
                ephemeral=True
            )
        finally:
            session.close()

# Function to check if a command should be disabled
async def should_run_command(guild_id: int, command_name: str) -> bool:
    """Check if a command should be allowed to run based on disabled features"""
    session = get_session('global')
    try:
        # Find which feature this command belongs to
        for feature, info in DISABLEABLE_FEATURES.items():
            if "commands" in info and command_name in info["commands"]:
                # Check if feature is disabled
                disabled = session.query(DisabledFeatures).filter_by(
                    server_id=str(guild_id),
                    feature_name=feature
                ).first()
                return not bool(disabled)
        return True  # If command not found in any feature, allow it
    finally:
        session.close()

# Export the setup functions and utility functions
__all__ = [
    'setup_disable_system',
    'setup_disable_commands',
    'is_feature_disabled',
    'should_run_command',
    'DISABLEABLE_FEATURES'
] 