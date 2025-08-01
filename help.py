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

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.current_page = 0
        self.pages = [
            self.get_overview_page,
            self.get_task_page,
            self.get_interactive_page,
            self.get_leveling_page,
            self.get_invite_page,
            self.get_music_page,
            self.get_utility_page,
            self.get_fun_page,
            self.get_admin_page,
            self.get_credits_page
        ]
        self.total_pages = len(self.pages)
        self.update_buttons()
    
    def update_buttons(self):
        # Update Previous button
        self.previous_button.disabled = (self.current_page == 0)
        # Update Next button
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
    
    def get_overview_page(self):
        embed = discord.Embed(
            title="🤖 Puddles Bot - Command Overview",
            description="Welcome to PuddlesBot2! Navigate through different command categories using the buttons below.",
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name="📋 Page 2: Task Management",
            value="Create, edit, and manage tasks for your team",
            inline=True
        )
        
        embed.add_field(
            name="🎫 Page 3: Interactive Messages",
            value="Tickets, role buttons, and custom messages",
            inline=True
        )
        
        embed.add_field(
            name="⭐ Page 4: Leveling System",
            value="XP tracking, rankings, and user progression",
            inline=True
        )
        
        embed.add_field(
            name="📊 Page 5: Invite Tracking",
            value="Monitor server growth and invite analytics",
            inline=True
        )
        
        embed.add_field(
            name="🎵 Page 6: Music System",
            value="High-quality music streaming (Vocard)",
            inline=True
        )
        
        embed.add_field(
            name="🔧 Page 7: Server Utilities",
            value="Moderation, user info, and server tools",
            inline=True
        )
        
        embed.add_field(
            name="🎮 Page 8: Fun & Games",
            value="Entertainment commands and mini-games",
            inline=True
        )
        
        embed.add_field(
            name="🛠️ Page 9: Admin & System",
            value="Advanced admin tools and system commands",
            inline=True
        )
        
        embed.add_field(
            name="💝 Page 10: Credits & Info",
            value="Attribution and special thanks",
            inline=True
        )
        
        embed.add_field(
            name="💡 **Key Features**",
            value=(
                "• **Multi-Assignee Tasks** - Assign tasks to multiple users\n"
                "• **Task Sniping** - Claim credit for others' completed tasks\n"
                "• **AI Chat System** - Mention the bot for AI responses\n"
                "• **Persistent Views** - Buttons work after bot restarts\n"
                "• **Dual XP System** - Separate text/voice XP tracking\n"
                "• **High-Quality Music** - Multi-platform streaming\n"
                "• **Smart Pagination** - Easy navigation for large lists"
            ),
            inline=False
        )
        
        embed.add_field(
            name="⚠️ **AI Chat Disclaimer**",
            value=(
                "🤖 **AI responses may contain inaccurate information**\n"
                "• Do not use for medical, legal, or financial advice\n"
                "• Always verify important information from reliable sources\n"
                "• Use for entertainment and general assistance only\n"
                "• By mentioning the bot, you agree to use at your own risk"
            ),
            inline=False
        )
        
        embed.add_field(
            name="📄 **Important Links**",
            value=(
                "📜 **[Privacy Policy](https://github.com/EcoEngineDev/PuddlesBot/blob/main/privacypolicy.md)**\n"
                "📋 **[Terms of Service](https://github.com/EcoEngineDev/PuddlesBot/blob/main/termsofservice.md)**\n"
                "⚠️ **[AI Chat Disclaimer](https://github.com/EcoEngineDev/PuddlesBot/blob/main/DISCLAIMER.md)**\n"
                "💬 **[Support Server](https://discord.gg/PGjXDgu36s)**"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} • Use the buttons to navigate")
        return embed
    
    def get_task_page(self):
        embed = discord.Embed(
            title="📋 Task Management Commands",
            description="Comprehensive task management system with multi-user support",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="**Creating & Managing Tasks**",
            value=(
                "`/task` - Create new task assigned to multiple users\n"
                "• Format: `/task assigned_to: @user1 @user2 @user3`\n"
                "• All assignees get credit when any one completes it\n\n"
                "`/taskedit` - Edit existing tasks or delete them\n"
                "• Change name, due date, description, or assignees\n"
                "• Delete option available for cleanup"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Viewing Tasks**",
            value=(
                "`/mytasks` - View all tasks assigned to you\n"
                "`/showtasks @user` - View tasks assigned to specific user\n"
                "`/alltasks` - View all active server tasks (paginated)\n"
                "`/oldtasks @user` - View completed tasks with stats"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Task Sniping System**",
            value=(
                "`/snipe` - Claim credit for completed tasks\n"
                "• Select from available tasks assigned to others\n"
                "• Requires admin approval in designated channel\n"
                "• Won't be marked as late even if past due date\n"
                "• Shows as 'sniped' in task history\n\n"
                "`/setsnipe #channel` - **[Admin]** Set snipe request channel\n"
                "`/clearsnipes` - **[Admin]** Clear pending snipe requests"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Permissions & Whitelist**",
            value=(
                "`/tcw @user add/remove` - **[Admin]** Manage task creator whitelist\n"
                "• Only admins and whitelisted users can create tasks\n"
                "• Prevents spam and maintains organization"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} • Tasks support multi-assignee workflows!")
        return embed
    
    def get_interactive_page(self):
        embed = discord.Embed(
            title="🎫 Interactive Messages & Tickets",
            description="Create interactive messages with buttons for tickets and role management",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="**Interactive Message Creation**",
            value=(
                "`/intmsg` - Create interactive messages with buttons\n"
                "• Ticket creation buttons with custom questions\n"
                "• Role assignment/removal buttons\n"
                "• Custom embed styling and content\n"
                "• Persistent - works after bot restarts"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Message Management**",
            value=(
                "`/editintmsg [message_id]` - **[Staff]** Edit existing messages\n"
                "`/listmessages` - **[Staff]** List all interactive messages\n"
                "• View message IDs and channels\n"
                "• Quick access to edit existing messages"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Ticket System**",
            value=(
                "`/ticketstats` - **[Staff]** View ticket statistics\n"
                "• Recent ticket activity\n"
                "• Response time analytics\n"
                "• User interaction patterns"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Permissions & Access**",
            value=(
                "`/imw @user add/remove` - **[Admin]** Manage interactive message whitelist\n"
                "• Control who can create interactive messages\n"
                "• Maintain message quality and organization"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} • Create engaging server interactions!")
        return embed
    
    def get_leveling_page(self):
        embed = discord.Embed(
            title="⭐ Leveling System Commands",
            description="Dual XP system tracking both text and voice activity",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="**User Progress & Rankings**",
            value=(
                "`/rank @user` - View detailed rank card\n"
                "• Text and voice XP progress bars\n"
                "• Server ranking position\n"
                "• Visual progress indicators\n\n"
                "`/top` - Display leaderboards\n"
                "• Sort by text XP, voice XP, or total XP\n"
                "• Top users in the server"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**XP Management (Admin)**",
            value=(
                "`/setxp @user` - **[Admin]** Set user's text or voice XP\n"
                "`/setlevel @user` - **[Admin]** Set user's text or voice level\n"
                "`/lvlreset @user` - **[Admin]** Reset user's levels and XP data"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**System Configuration**",
            value=(
                "`/lvlconfig` - **[Admin]** Configure XP system\n"
                "• XP rates and cooldowns\n"
                "• Server-specific settings\n"
                "• Anti-spam protection"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Testing & Debugging**",
            value=(
                "`/testxp @user` - **[Admin]** Manually award XP\n"
                "`/testvoice @user` - **[Admin]** Simulate voice time\n"
                "`/debugxp @user` - **[Admin]** Debug XP system status"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} • Dual XP system with anti-spam protection!")
        return embed
    
    def get_invite_page(self):
        embed = discord.Embed(
            title="📊 Invite Tracking Commands",
            description="Monitor server growth and track invite analytics",
            color=discord.Color.teal()
        )
        
        embed.add_field(
            name="**Invite Statistics**",
            value=(
                "`/topinvite` - Show top 10 inviters in server\n"
                "`/showinvites @user` - Detailed invite stats for user\n"
                "• Total invites, joins, and leaves\n"
                "• Success rate and activity tracking"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Admin Management**",
            value=(
                "`/resetinvites` - **[Admin]** Reset all invite data\n"
                "• Requires confirmation for safety\n\n"
                "`/editinvites @user` - **[Admin]** Edit user invite stats\n"
                "• Adjust invite counts manually"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**System Management**",
            value=(
                "`/invitesync` - **[Admin]** Manually sync invite data\n"
                "`/invitestats` - **[Admin]** Comprehensive server invite stats\n"
                "`/invitereset` - **[Admin]** Reset tracking tables\n"
                "• **Warning:** Deletes all invite data permanently"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Permissions**",
            value=(
                "`/invw @user add/remove` - **[Admin]** Manage invite admin whitelist\n"
                "• Control access to invite management commands"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} • Track server growth effectively!")
        return embed
    
    def get_music_page(self):
        embed = discord.Embed(
            title="🎵 Music System (Vocard)",
            description="High-quality music streaming with multi-platform support",
            color=discord.Color.red()
        )
        
        embed.add_field(
            name="**Playback Controls**",
            value=(
                "`/play [song]` - Play music from multiple platforms\n"
                "• YouTube, Spotify, SoundCloud, Apple Music\n"
                "• Supports playlists and direct links\n\n"
                "`/pause` / `/resume` - Pause or resume current track\n"
                "`/skip` / `/back` - Navigate through queue\n"
                "`/stop` / `/leave` - Stop music and leave channel"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Queue Management**",
            value=(
                "`/queue` - View current music queue\n"
                "`/shuffle` - Shuffle the current queue\n"
                "`/loop [mode]` - Set loop mode (off/track/queue)\n"
                "`/nowplaying` - Show currently playing track"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Audio Quality & Search**",
            value=(
                "`/volume [0-100]` - Adjust music volume\n"
                "`/quality` - **[Manager]** Manage audio quality settings\n"
                "`/audiostats` - Show audio performance metrics\n"
                "`/search [query]` - Search across platforms"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💡 **Music Features**",
            value=(
                "• **Multi-Platform Support** - YouTube, Spotify, SoundCloud & more\n"
                "• **High-Quality Audio** - Configurable quality presets\n"
                "• **Smart Queue** - Playlist support with shuffle\n"
                "• **Performance Metrics** - Real-time audio statistics"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} • Powered by Vocard & Lavalink!")
        return embed
    
    def get_utility_page(self):
        embed = discord.Embed(
            title="🔧 Server Utilities & Moderation",
            description="Essential server management and user utility commands",
            color=discord.Color.orange()
        )
        
        embed.add_field(
            name="**User Information**",
            value=(
                "`/profile @user` - View customizable personal profile\n"
                "`/user @user` - Show user info (ID, join date, etc.)\n"
                "`/avatar @user` - Get user's avatar image\n"
                "`/roles` - List all server roles and member counts"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Server Information**",
            value=(
                "`/server` - Show detailed server information\n"
                "• Member count, channels, creation date\n"
                "• Server features and statistics"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Voice & Movement**",
            value=(
                "`/moveme [channel/user]` - Move yourself to voice channel\n"
                "• Move to specific channel or follow another user"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Moderation Tools**",
            value=(
                "`/ban @user [reason]` - **[Admin]** Ban member from server\n"
                "`/kick @user [reason]` - **[Admin]** Kick member from server\n"
                "`/purge [number] @user` - **[Staff]** Clean up messages\n"
                "• Mass delete messages with optional user filter"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} • Essential server management tools!")
        return embed
    
    def get_fun_page(self):
        embed = discord.Embed(
            title="🎮 Fun & Games Commands",
            description="Entertainment commands and mini-games to brighten your day",
            color=discord.Color.magenta()
        )
        
        embed.add_field(
            name="**Random Fun**",
            value=(
                "`/quack` - Get a random duck image 🦆\n"
                "• Powered by random-d.uk API\n"
                "• Adorable duck photos to brighten your day\n\n"
                "`/meme` - Get a random meme 😂\n"
                "• Fresh memes from Reddit\n"
                "• NSFW content automatically filtered\n"
                "• Shows upvotes, subreddit, and original post"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Games & Chance**",
            value=(
                "`/coinflip` - Flip a coin! Heads or Tails? 🪙\n"
                "• Uses real coin images from collection\n"
                "• Random selection from heads/tails folders\n\n"
                "`/diceroll [1-100]` - Roll dice with visual results\n"
                "• Customizable dice count\n"
                "• Visual dice display with statistics"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**AI Chat System** 🤖",
            value=(
                "`@PuddlesBot [message]` - Chat with AI assistant\n"
                "• Mention the bot followed by your question or message\n"
                "• Casual, friendly Discord-style responses\n"
                "• Remembers recent conversation context\n"
                "• Example: `@PuddlesBot what's Python programming?`\n\n"
                "⚠️ **Important**: AI may provide inaccurate information.\n"
                "Do not use for medical, legal, or financial advice."
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Help & Navigation**",
            value=(
                "`/help` - Show this paginated help system\n"
                "• Navigate through different command categories\n"
                "• Comprehensive command documentation"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💡 **Fun Features**",
            value=(
                "• **Visual Results** - Coinflip shows actual coin images\n"
                "• **Smart Filtering** - Memes are family-friendly\n"
                "• **Rich Information** - Detailed meme metadata\n"
                "• **Random Variety** - Fresh content every time"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} • Have fun and enjoy!")
        return embed
    
    def get_admin_page(self):
        embed = discord.Embed(
            title="🛠️ Admin & System Commands",
            description="Advanced administrative tools and system management",
            color=discord.Color.dark_red()
        )
        
        embed.add_field(
            name="**Messaging & Communication**",
            value=(
                "`/msg #channel` - **[Admin]** Send your next message to any channel\n"
                "• Supports multi-line messages and attachments\n"
                "• Enables @everyone, @here, and role pings\n"
                "• Wait for your next message after running command"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Database Management**",
            value=(
                "`/fixdb` - **[Admin]** Fix database schema issues\n"
                "• Repair corrupted tables\n"
                "• Update schema to latest version\n\n"
                "`/testpersistence` - **[Admin]** Test persistence system\n"
                "• Verify button functionality after restarts"
            ),
            inline=False
        )
        
        embed.add_field(
            name="**Owner-Only Commands**",
            value=(
                "`/multidimensionaltravel` - **[Owner]** Get invites to all bot servers\n"
                "• Access all servers where bot is present\n\n"
                "`/gigaop` - **[Owner]** Grant admin permissions for debugging\n"
                "• Temporary admin access for troubleshooting"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🔑 **Permission Levels**",
            value=(
                "**[Owner]** - Bot owner only (ID: 699995264550961193)\n"
                "**[Admin]** - Requires Administrator permission\n"
                "**[Staff]** - Requires Manage Messages permission\n"
                "**[Manager]** - Requires Manage Server permission"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} • Use admin commands responsibly!")
        return embed
    
    def get_credits_page(self):
        embed = discord.Embed(
            title="💝 Credits & Acknowledgments",
            description="Special thanks to all the amazing projects and services that make PuddlesBot2 possible",
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name="🎵 **Music System**",
            value=(
                "**[Vocard](https://github.com/ChocoMeow/Vocard)** - Advanced music bot framework\n"
                "• Multi-platform music streaming\n"
                "• High-quality audio processing\n\n"
                "**[Lavalink](https://github.com/lavalink-devs/Lavalink)** - Audio delivery node\n"
                "• Efficient audio streaming\n"
                "• Load balancing and performance"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🎮 **Fun Commands APIs**",
            value=(
                "**[Meme API](https://github.com/D3vd/Meme_Api)** - Random memes from Reddit\n"
                "• Fresh meme content with metadata\n"
                "• NSFW filtering and quality control\n\n"
                "**[Random Duck API](https://random-d.uk/)** - Adorable duck images\n"
                "• High-quality duck photography\n"
                "• Instant mood boosters 🦆"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🪙 **Coinflip Images**",
            value=(
                "**Coin Images** - Various online sources\n"
                "• Images sourced from random websites\n"
                "• No ownership claimed - will remove upon request\n"
                "• Contact us if you own any images and want them removed"
            ),
            inline=False
        )
        
        embed.add_field(
            name="🏎️ **Special Thanks**",
            value=(
                "**[EcoEngine](https://ecoengine.net/)** - Supporting Mallard Motorsports\n"
                "• Sponsoring the team and its projects\n"
                "• Enabling continued development and innovation\n"
                "• Thank you for believing in our mission! 🚀"
            ),
            inline=False
        )
        
        embed.add_field(
            name="💻 **Development & Community**",
            value=(
                "• **Discord.py** - Python Discord API wrapper\n"
                "• **SQLAlchemy** - Database ORM framework\n"
                "• **Our amazing community** - Beta testers and feedback providers\n"
                "• **Open source contributors** - Making everything possible"
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1} of {self.total_pages} • Made with ❤️ by the PuddlesBot2 team")
        return embed
    
    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary, disabled=True)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = self.pages[self.current_page]()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed = self.pages[self.current_page]()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    @discord.ui.button(label="🏠 Home", style=discord.ButtonStyle.primary)
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        embed = self.pages[self.current_page]()
        await interaction.response.edit_message(embed=embed, view=self)

@app_commands.command(
    name="help",
    description="Show all available commands with paginated navigation"
)
@log_command
async def help_command(interaction: discord.Interaction):
    """Display comprehensive help information with pagination"""
    view = HelpView()
    embed = view.pages[0]()  # Start with overview page
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

def setup_help_commands(tree):
    """Add help commands to the command tree"""
    tree.add_command(help_command)
    print("✅ Help commands loaded: /help (paginated)") 