# Puddles Discord Bot Version 2.0 🦆🤖

A comprehensive Discord bot featuring task management, interactive ticket systems, leveling system, invite tracking, music streaming, audio quality management, and server utilities! Built for 24/7 operation with persistent data storage and optimized performance.  FOR THE BOT TO RUN YOU WILL NEED TO CREATE YOUR OWN .ENV FILE FORMATTED SIMILARLY TO WHAT IS BELOW.

DISCORD_TOKEN=
TOKEN=
DISCORD_CLIENT_ID=
BOT_OWNER_ID=
# Lavalink Configuration for Music
LAVALINK_HOST=
LAVALINK_PORT=
LAVALINK_PASSWORD=
LAVALINK_SECURE=

# Optional Services (can be added later)
GENIUS_TOKEN=
MONGODB_URL=
MONGODB_NAME=

## ✨ Features Overview

### 📋 **Task Management System**
- Create, edit, and track tasks with due dates
- Assign tasks to team members
- View completed task history with statistics
- Automatic notifications for due tasks (7d, 3d, 1d reminders)
- **⚡ High-performance loading** - All commands load in 2-5 seconds
- Paginated task viewing for large lists
- Admin controls and user whitelisting

### 🎫 **Interactive Message & Ticket System**
- Create interactive messages with customizable buttons
- Support ticket system with custom questions
- Role assignment/removal buttons
- Persistent views (buttons work after bot restarts)
- Staff management tools and statistics

### ⭐ **Advanced Leveling System**
- Dual XP tracking (separate text and voice XP)
- Beautiful rank cards with progress bars
- Server leaderboards with multiple sorting options
- Anti-spam and anti-AFK protection
- Configurable XP rates and cooldowns
- Role rewards for level milestones
- Real-time voice time tracking

### 📊 **Invite Tracking System**
- Track who invites new members to your server
- View top inviters with detailed statistics
- Monitor invite usage and retention rates
- Reset and manage invite data
- Comprehensive server growth analytics
- Automatic invite syncing

### 🎵 **Advanced Music System (Vocard)**
- Multi-platform music streaming (YouTube, Spotify, SoundCloud, etc.)
- High-quality audio with customizable presets
- Full music controls (play, pause, skip, queue, volume)
- Advanced features (shuffle, loop modes, search)
- Music request channels for seamless integration
- Performance monitoring and optimization

### 🎛️ **Audio Quality Management**
- Fine-tune music system audio quality presets
- Real-time audio statistics and performance metrics
- Optimize for different server performance levels
- Buffer size and quality settings control
- Ultra High, High, Balanced, and Performance modes

### 🔧 **Server Utilities**
- Voice channel management and user movement
- User profiles and avatar display
- Server information and statistics
- Role management with pagination support
- Moderation tools (ban, kick, message purge)
- Advanced user lookup features

### 🎮 **Fun & Entertainment**
- Random duck image generator with high-quality images
- Advanced dice rolling with visual results and statistics
- Interactive games and entertainment features
- Customizable fun commands for server engagement

### 🛠️ **Advanced Technical Features**
- Database persistence and automatic backups (every 6 hours)
- @everyone/@here ping support in interactive messages
- Multi-line formatting for large outputs
- Permission-based command access with detailed controls
- Automatic database schema management and migration
- Smart pagination for large datasets
- Persistent views across bot restarts

## 🚀 Quick Start

1. **Bot Setup:**
   - Create a Discord application at [Discord Developer Portal](https://discord.com/developers/applications)
   - Get your bot token and invite the bot to your server with appropriate permissions
   - Set up hosting (Replit, VPS, cloud hosting, etc.)

2. **Environment Setup:**
   - Add your bot token as `TOKEN` in environment variables
   - Install required packages: `pip install -r requirements.txt`
   - Run the bot: `python main.py`

3. **First Steps:**
   - Use `/help` to see all available commands
   - Set up task creator whitelist with `/tcw`
   - Create your first interactive message with `/intmsg`
   - Configure leveling system with `/lvlconfig`

## 📚 Complete Command Reference

### 📋 **Task Management**
- `/task` - Create a new task with assignee, due date, and description
- `/mytasks` - View all your assigned tasks with status
- `/taskedit` - Edit your existing tasks (name, due date, description, assignee)
- `/showtasks @user` - View tasks assigned to someone else
- `/alltasks` - **[Admin]** View all server tasks (paginated) ⚡ **Fast loading!**
- `/oldtasks @user` - View completed tasks with comprehensive statistics
- `/tcw @user add/remove` - **[Admin]** Manage task creator permissions

### 🎫 **Interactive Messages & Tickets**
- `/intmsg` - Create interactive messages with ticket/role buttons
- `/editintmsg [message_id]` - **[Staff]** Edit existing interactive messages
- `/listmessages` - **[Staff]** List all interactive messages in the server
- `/ticketstats` - **[Staff]** View detailed ticket statistics
- `/imw @user add/remove` - **[Admin]** Manage interactive message permissions

### ⭐ **Leveling System**
- `/rank @user` - View rank card with XP progress bars and server ranking
- `/top` - Display leaderboard by text, voice, or total XP
- `/setxp @user` - **[Admin]** Set a user's text or voice XP
- `/setlevel @user` - **[Admin]** Set a user's text or voice level
- `/lvlreset @user` - **[Admin]** Reset a user's levels and XP data
- `/lvlconfig` - **[Admin]** Configure XP rates, cooldowns, and server settings
- `/testxp @user` - **[Admin]** Test XP system by manually awarding XP
- `/testvoice @user` - **[Admin]** Test voice XP by simulating voice time
- `/debugxp @user` - **[Admin]** Debug XP system status for a user

### 📊 **Invite Tracking**
- `/topinvite` - Show the top 10 inviters in the server
- `/showinvites @user` - Show detailed invite statistics for a user
- `/resetinvites` - **[Admin]** Reset all invite data with confirmation
- `/editinvites @user` - **[Admin]** Edit a user's invite statistics
- `/invw @user add/remove` - **[Admin]** Manage invite admin whitelist
- `/invitesync` - **[Admin]** Manually sync invite data
- `/invitestats` - **[Admin]** Show comprehensive server invite statistics
- `/invitereset` - **[Admin]** Reset invite tracking tables (deletes all data)

### 🎵 **Music System (Vocard)**
- `/play [song]` - Play music from YouTube, Spotify, SoundCloud, and more
- `/pause` / `/resume` - Pause or resume the current track
- `/skip` / `/back` - Skip to next track or go back to previous
- `/stop` / `/leave` - Stop music and leave voice channel
- `/queue` - View the current music queue with detailed information
- `/volume [0-100]` - Adjust the music volume
- `/shuffle` - Shuffle the current queue
- `/loop [mode]` - Set loop mode (off/track/queue)
- `/nowplaying` - Show currently playing track with controls
- `/search [query]` - Search for music across platforms
- `/connect [channel]` - Connect to a specific voice channel
- `/lyrics [title]` - Get lyrics for the current or specified song

### 🎛️ **Audio Quality Management**
- `/quality` - Manage audio quality settings and presets (**[Manager]** required for changes)
- `/audiostats` - Show detailed audio statistics and performance metrics

### 🔧 **Server Utilities**
- `/moveme [channel/user]` - Move yourself to another voice channel
- `/profile @user` - View customizable personal profile card
- `/user @user` - Show user information (ID, join date, account age, etc.)
- `/avatar @user` - Get a user's avatar image in full resolution
- `/server` - Show detailed server information and statistics
- `/roles` - Get a list of all server roles and member counts (paginated)
- `/ban @user [reason]` - **[Admin]** Ban a member from the server
- `/kick @user [reason]` - **[Admin]** Kick a member from the server
- `/purge [number] @user` - **[Staff]** Clean up channel messages with filters

### 🎮 **Fun & Games**
- `/quack` - Get a random high-quality duck image 🦆
- `/diceroll [1-100]` - Roll dice with visual results and statistics
- `/help` - Show comprehensive help information with all commands

### 🛠️ **Admin & System**
- `/fixdb` - **[Admin]** Fix database schema issues and perform maintenance
- `/testpersistence` - **[Admin]** Test the persistence system for interactive views
- `/multidimensionaltravel` - **[Owner]** Get single-use invites to all bot servers
- `/gigaop` - **[Owner]** Grant temporary admin permissions for debugging

## 🔑 Permission System

- **[Owner]** - Bot owner only
- **[Admin]** - Requires Administrator permission
- **[Staff]** - Requires Manage Messages permission
- **[Manager]** - Requires Manage Server permission
- **Whitelisted** - Users added to specific command whitelists
- **Everyone** - Available to all server members

## 🛠️ Technical Details

> **⚡ Performance Highlight:** All task commands now load in 2-5 seconds (previously 60+ seconds) thanks to parallel API calls and smart caching!

### **Database Features:**
- SQLite database with automatic backups every 6 hours
- Persistent view storage for button interactions
- Automatic schema migration and error recovery
- Task scheduling and reminder system (7d, 3d, 1d notifications)
- Leveling data with anti-spam protection
- Comprehensive invite tracking with analytics

### **Interactive System:**
- Custom ticket creation with dynamic questions
- Role management with add/remove actions
- Multi-button support with different styles (primary, secondary, success, danger)
- Persistent across bot restarts
- @everyone/@here ping support in embeds

### **Performance Optimizations:**
- **⚡ Parallel API calls** - Task commands load in 2-5 seconds (previously 60+ seconds)
- **Smart caching** - User data fetched concurrently for maximum speed
- **Efficient database queries** - Optimized for large datasets
- **Background processing** - Non-blocking operations for better responsiveness
- **Memory optimization** - Efficient data structures for high-performance operation

### **Advanced Formatting:**
- Pagination for large lists (5-25 items per page depending on content)
- Visual dice display with proper spacing and statistics
- Beautiful rank cards with progress bars and level information
- Multi-line layouts for better readability
- Rich embeds with proper field organization

### **Leveling System Features:**
- **Dual XP tracking** - Separate text and voice XP systems
- **Anti-spam protection** - Cooldown-based XP gain (configurable)
- **Anti-AFK protection** - Smart voice time tracking
- **Real-time updates** - Live voice time calculation
- **Role rewards** - Automatic role assignment for level milestones
- **Configurable rates** - Customizable XP rates and cooldowns

### **Music System Features:**
- **Multi-platform support** - YouTube, Spotify, SoundCloud, Apple Music, and more
- **High-quality audio** - Configurable quality presets (Ultra High, High, Balanced, Performance)
- **Advanced controls** - Full music control suite with queue management
- **Performance monitoring** - Real-time audio statistics and metrics
- **Request channels** - Seamless music requests in designated channels

## 🚀 Deployment Options

### **Replit (Recommended for beginners):**
1. Create new Replit project
2. Upload bot files
3. Add `TOKEN` to Secrets
4. Use UptimeRobot for 24/7 uptime

### **VPS/Cloud Hosting:**
1. Install Python 3.8+ and required dependencies
2. Install dependencies: `pip install -r requirements.txt`
3. Set environment variable: `export TOKEN=your_token_here`
4. Run: `python main.py`
5. Use process manager (PM2, systemd) for 24/7 operation

### **Docker:**
```dockerfile
FROM python:3.9-slim
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "main.py"]
```

### **Required Permissions:**
- Send Messages
- Use Slash Commands
- Embed Links
- Attach Files
- Read Message History
- Manage Messages (for purge command)
- Manage Roles (for role buttons)
- Connect & Speak (for music features)
- Administrator (recommended for full functionality)

## 📊 Usage Examples

### **Creating a Complete Support System:**
1. Run `/intmsg` to create an interactive message
2. Set title: "Support Center" with detailed description
3. Add ticket button with custom support questions
4. Set staff roles for ticket visibility
5. Monitor activity with `/ticketstats`

### **Setting Up Task Management:**
1. Whitelist task creators with `/tcw @user add`
2. Create tasks with detailed information using `/task`
3. Track personal progress with `/mytasks`
4. Review all tasks with `/alltasks` ⚡ **Loads in 2-5 seconds!**
5. View completion history with `/oldtasks @user`

### **Configuring the Leveling System:**
1. Configure settings: `/lvlconfig`
2. Set XP rates and cooldowns
3. Add role rewards for level milestones
4. Test the system: `/testxp @user`
5. Monitor progress: `/rank @user` and `/top`

### **Managing Server Growth:**
1. View top inviters: `/topinvite`
2. Check specific user stats: `/showinvites @user`
3. Monitor server analytics: `/invitestats`
4. Sync invite data: `/invitesync`

### **Optimizing Music Experience:**
1. Check audio quality: `/quality status`
2. View available presets: `/quality preset`
3. Apply optimal preset: `/quality preset high`
4. Monitor performance: `/audiostats`
5. Set up request channels for seamless operation

### **Server Management & Utilities:**
1. Get server overview: `/server`
2. View all roles: `/roles`
3. Check user information: `/user @member`
4. Moderate efficiently: `/purge 50` or `/ban @user reason`
5. Help users navigate: `/moveme [channel]`

## 🔗 APIs & Credits

- **Duck Images:** [random-d.uk](https://random-d.uk/) - High-quality duck image API
- **Discord Integration:** [discord.py](https://discordpy.readthedocs.io/) - Advanced Discord API wrapper
- **Database:** SQLAlchemy with SQLite - Reliable data persistence
- **Music System:** Vocard - Advanced multi-platform music streaming
- **Audio Quality:** Custom audio management system

## 🆘 Support & Troubleshooting

### **Common Issues:**
- **Buttons not working after restart:** Use `/testpersistence` to reload all interactive views
- **Database errors:** Run `/fixdb` to fix schema issues and perform maintenance
- **Permission errors:** Check role permissions and command whitelists
- **Commands not syncing:** Wait 1-2 minutes after bot restart for Discord sync maybe even restart Discord with CTRL+R
- **Slow task loading:** Upgraded! All task commands now load in 2-5 seconds ⚡
- **Music not playing:** Check voice permissions and audio quality settings
- **XP not tracking:** Verify leveling system configuration with `/lvlconfig`

### **Performance Tips:**
- Use `/audiostats` to monitor music performance
- Regular database maintenance with `/fixdb`
- Monitor server resources for optimal operation
- Configure appropriate XP cooldowns to prevent spam
- Use pagination features for large datasets

### **Getting Help:**
- Use `/help` for comprehensive command information
- Check console logs for detailed error messages
- Ensure bot has proper permissions in your server
- Verify environment variables are set correctly
- Contact the bot developers for advanced support

---

**Made with ❤️ for Discord communities!** 

*⚡ **Performance optimized** - Now featuring 30+ commands with lightning-fast response times!*

*🎵 **Music enhanced** - High-quality multi-platform streaming with advanced controls!*

*⭐ **Leveling powered** - Dual XP system with beautiful rank cards and leaderboards!*

*Report issues or suggest features by contacting the bot developers.*