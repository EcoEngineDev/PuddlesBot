import discord
from discord import app_commands
import functools
from typing import Callable, Any
import traceback

# Store reference to the client
_client = None

def setup_help_system(client):
    """Initialize the help system with client reference"""
    global _client
    _client = client

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

@app_commands.command(
    name="help",
    description="Show all available commands and their descriptions"
)
@log_command
async def help_command(interaction: discord.Interaction):
    """Display comprehensive help information"""
    
    embed = discord.Embed(
        title="🤖 Puddles Bot - Command Help",
        description="Here are all the available commands and how to use them:",
        color=discord.Color.blue()
    )
    
    # Task Management Commands
    embed.add_field(
        name="📋 **Task Management**",
        value=(
            "`/task` - Create a new task with name, assignee, due date, and description\n"
            "`/mytasks` - View all tasks assigned to you\n"
            "`/taskedit` - Edit your existing tasks (name, due date, description, assignee)\n"
            "`/showtasks @user` - View tasks assigned to a specific user\n"
            "`/alltasks` - View all active tasks in the server (paginated) ⚡ **Fast loading!**\n"
            "`/oldtasks @user` - View completed tasks for a specific user with statistics\n"
            "`/tcw @user add/remove` - **[Admin]** Manage task creator whitelist"
        ),
        inline=False
    )
    
    # Interactive Message & Ticket System
    embed.add_field(
        name="🎫 **Interactive Messages & Tickets**",
        value=(
            "`/intmsg` - Create interactive messages with ticket/role buttons\n"
            "`/editintmsg [message_id]` - **[Staff]** Edit existing interactive messages\n"
            "`/listmessages` - **[Staff]** List all interactive messages in the server\n"
            "`/ticketstats` - **[Staff]** View ticket statistics and recent activity\n"
            "`/imw @user add/remove` - **[Admin]** Manage interactive message creator whitelist"
        ),
        inline=False
    )
    
    # Leveling System Commands
    embed.add_field(
        name="⭐ **Leveling System**",
        value=(
            "`/rank @user` - View rank card with XP progress bars and server ranking\n"
            "`/top` - Display leaderboard by text, voice, or total XP\n"
            "`/setxp @user` - **[Admin]** Set a user's text or voice XP\n"
            "`/setlevel @user` - **[Admin]** Set a user's text or voice level\n"
            "`/lvlreset @user` - **[Admin]** Reset a user's levels and XP data\n"
            "`/lvlconfig` - **[Admin]** Configure XP rates, cooldowns, and server settings\n"
            "`/testxp @user` - **[Admin]** Test XP system by manually awarding XP\n"
            "`/testvoice @user` - **[Admin]** Test voice XP by simulating voice time\n"
            "`/debugxp @user` - **[Admin]** Debug XP system status for a user"
        ),
        inline=False
    )
    
    # Invite Tracking Commands
    embed.add_field(
        name="📊 **Invite Tracking**",
        value=(
            "`/topinvite` - Show the top 10 inviters in the server\n"
            "`/showinvites @user` - Show detailed invite statistics for a user\n"
            "`/resetinvites` - **[Admin]** Reset all invite data with confirmation\n"
            "`/editinvites @user` - **[Admin]** Edit a user's invite statistics\n"
            "`/invw @user add/remove` - **[Admin]** Manage invite admin whitelist\n"
            "`/invitesync` - **[Admin]** Manually sync invite data\n"
            "`/invitestats` - **[Admin]** Show comprehensive server invite statistics\n"
            "`/invitereset` - **[Admin]** Reset invite tracking tables (deletes all data)"
        ),
        inline=False
    )
    
    # Music System Commands
    embed.add_field(
        name="🎵 **Music System (Vocard)**",
        value=(
            "`/play [song]` - Play music from YouTube, Spotify, SoundCloud, and more\n"
            "`/pause` / `/resume` - Pause or resume the current track\n"
            "`/skip` / `/back` - Skip to next track or go back to previous\n"
            "`/stop` / `/leave` - Stop music and leave voice channel\n"
            "`/queue` - View the current music queue\n"
            "`/volume [0-100]` - Adjust the music volume\n"
            "`/shuffle` - Shuffle the current queue\n"
            "`/loop [mode]` - Set loop mode (off/track/queue)\n"
            "`/nowplaying` - Show currently playing track\n"
            "`/search [query]` - Search for music across platforms"
        ),
        inline=False
    )
    
    # Audio Quality Management Commands
    embed.add_field(
        name="🎛️ **Audio Quality Management**",
        value=(
            "`/quality` - Manage audio quality settings and presets (**[Manager]** required for changes)\n"
            "`/audiostats` - Show detailed audio statistics and performance metrics"
        ),
        inline=False
    )
    
    # Utility Commands
    embed.add_field(
        name="🔧 **Server Utilities**",
        value=(
            "`/moveme [channel/user]` - Move yourself to another voice channel\n"
            "`/profile @user` - View customizable personal profile card\n"
            "`/user @user` - Show user information (ID, join date, etc.)\n"
            "`/avatar @user` - Get a user's avatar image\n"
            "`/server` - Show detailed server information\n"
            "`/roles` - Get a list of all server roles and member counts\n"
            "`/ban @user [reason]` - **[Admin]** Ban a member from the server\n"
            "`/kick @user [reason]` - **[Admin]** Kick a member from the server\n"
            "`/purge [number] @user` - **[Staff]** Clean up channel messages"
        ),
        inline=False
    )
    
    # Fun & Games Commands
    embed.add_field(
        name="🎮 **Fun & Games**",
        value=(
            "`/quack` - Get a random duck image 🦆\n"
            "`/diceroll [1-100]` - Roll dice and see visual results with statistics\n"
            "`/help` - Show this comprehensive help message"
        ),
        inline=False
    )
    
    # Admin & System Commands
    embed.add_field(
        name="🛠️ **Admin & System**",
        value=(
            "`/fixdb` - **[Admin]** Fix database schema issues\n"
            "`/testpersistence` - **[Admin]** Test the persistence system\n"
            "`/multidimensionaltravel` - **[Owner]** Get invites to all bot servers\n"
            "`/gigaop` - **[Owner]** Grant admin permissions for debugging"
        ),
        inline=False
    )
    
    # Permission Legend
    embed.add_field(
        name="🔑 **Permission Legend**",
        value=(
            "**[Owner]** - Bot owner only (user ID: 699995264550961193)\n"
            "**[Admin]** - Requires Administrator permission\n"
            "**[Staff]** - Requires Manage Messages permission\n"
            "**[Manager]** - Requires Manage Server permission\n"
            "No tag - Available to all users (some may require whitelist)"
        ),
        inline=False
    )
    
    # Additional Info
    embed.add_field(
        name="💡 **Special Features**",
        value=(
            "• **🔄 Persistent Views** - Buttons work even after bot restarts\n"
            "• **📬 Task Notifications** - Get DMs when tasks are due soon\n"
            "• **⚡ Optimized Performance** - Task commands load in 2-5 seconds\n"
            "• **🎯 Dual XP System** - Separate text/voice XP with anti-spam protection\n"
            "• **🎫 Smart Tickets** - Support tickets with custom questions\n"
            "• **🎭 Role Management** - Assign/remove roles with interactive buttons\n"
            "• **📈 Invite Analytics** - Track server growth and invite sources\n"
            "• **🎵 High-Quality Music** - Multi-platform support with quality control\n"
            "• **📄 Smart Pagination** - Large lists split into easy-to-read pages\n"
            "• **📢 Ping Support** - Use @everyone/@here in interactive messages\n"
            "• **🗃️ Auto Backups** - Database backups every 6 hours for safety"
        ),
        inline=False
    )
    
    embed.set_footer(text="🚀 Performance optimized! 30+ commands with lightning-fast response • Need help? Contact the bot developers!")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

def setup_help_commands(tree):
    """Add help commands to the command tree"""
    tree.add_command(help_command)
    print("✅ Help commands loaded: /help") 