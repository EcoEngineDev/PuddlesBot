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
            "`/alltasks` - **[Admin]** View all active tasks in the server (paginated)\n"
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
    
    # Fun & Utility Commands
    embed.add_field(
        name="🎮 **Fun & Utility**",
        value=(
            "`/quack` - Get a random duck image 🦆\n"
            "`/diceroll [1-100]` - Roll dice and see visual results with statistics\n"
            "`/help` - Show this help message"
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
    
    # Music Commands
    embed.add_field(
        name="🎵 **Music System**",
        value=(
            "`/play <song/url>` - Play a song or add to queue (YouTube/Spotify support)\n"
            "`/pause` - Pause the current song\n"
            "`/resume` - Resume paused music\n"
            "`/skip` - Skip current song (vote skip for multiple users)\n"
            "`/stop` - Stop music and clear queue\n"
            "`/queue` - Show current music queue\n"
            "`/nowplaying` - Show currently playing song\n"
            "`/volume <1-100>` - Set music volume\n"
            "`/loop <off/song/queue>` - Set loop mode\n"
            "`/shuffle` - Shuffle the queue\n"
            "`/remove <position>` - Remove song from queue\n"
            "`/clear` - Clear entire queue\n"
            "`/leave` - Disconnect from voice channel\n"
            "`/search <query>` - Search for songs without playing\n"
            "`/musicstatus` - **[Admin]** Check music system status and diagnostics\n"
            "`/voicetest` - **[Admin]** Test voice connection capability"
        ),
        inline=False
    )
    
    # Admin & System Commands
    embed.add_field(
        name="🔧 **Admin & System**",
        value=(
            "`/fixdb` - **[Admin]** Fix database schema issues\n"
            "`/testpersistence` - **[Admin]** Test the persistence system"
        ),
        inline=False
    )
    
    # Permission Legend
    embed.add_field(
        name="🔑 **Permission Legend**",
        value=(
            "**[Admin]** - Requires Administrator permission\n"
            "**[Staff]** - Requires Manage Messages permission\n"
            "No tag - Available to all users (some may require whitelist)"
        ),
        inline=False
    )
    
    # Additional Info
    embed.add_field(
        name="💡 **Special Features**",
        value=(
            "• **Persistent Views** - Buttons work even after bot restarts\n"
            "• **Task Notifications** - Get DMs when tasks are due soon\n"
            "• **Ticket System** - Create support tickets with custom questions\n"
            "• **Role Management** - Assign/remove roles with buttons\n"
            "• **Invite Tracking** - Track who joins through whose invites\n"
            "• **Music System** - YouTube & Spotify integration with queue management\n"
            "• **Vote Skip** - Democratic music control for multiple users\n"
            "• **Auto-Leave** - Bot leaves voice when inactive (5 min timer)\n"
            "• **Pagination** - Large lists are split into easy-to-read pages\n"
            "• **Ping Support** - Use @everyone/@here in interactive messages"
        ),
        inline=False
    )
    
    embed.set_footer(text="For detailed help with any command, try using it and see the prompts!")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

def setup_help_commands(tree):
    """Add help commands to the command tree"""
    tree.add_command(help_command)
    print("✅ Help commands loaded: /help") 