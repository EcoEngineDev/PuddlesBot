# Puddles Discord Bot 🦆🤖

A comprehensive Discord bot featuring task management, interactive ticket systems, role management, and fun utilities! Built for 24/7 operation with persistent data storage.

## ✨ Features Overview

### 📋 **Task Management System**
- Create, edit, and track tasks with due dates
- Assign tasks to team members
- Automatic notifications for due tasks
- Paginated task viewing for large lists
- Admin controls and user whitelisting

### 🎫 **Interactive Message & Ticket System**
- Create interactive messages with customizable buttons
- Support ticket system with custom questions
- Role assignment/removal buttons
- Persistent views (buttons work after bot restarts)
- Staff management tools and statistics

### 🎮 **Fun & Utility Commands**
- Random duck image generator
- Advanced dice rolling with visual results
- Comprehensive help system

### 🔧 **Advanced Features**
- Database persistence and automatic backups
- @everyone/@here ping support in interactive messages
- Multi-line formatting for large outputs
- Permission-based command access
- Automatic database schema management

## 🚀 Quick Start

1. **Bot Setup:**
   - Create a Discord application at [Discord Developer Portal](https://discord.com/developers/applications)
   - Get your bot token and invite the bot to your server
   - Set up hosting (Replit, VPS, etc.)

2. **Environment Setup:**
   - Add your bot token as `TOKEN` in environment variables
   - Install required packages (discord.py, SQLAlchemy, etc.)
   - Run the bot!

3. **First Steps:**
   - Use `/help` to see all available commands
   - Set up task creator whitelist with `/tcw`
   - Create your first interactive message with `/intmsg`

## 📚 Command Reference

### 📋 **Task Management**
- `/task` - Create a new task with assignee and due date
- `/mytasks` - View all your assigned tasks
- `/taskedit` - Edit your existing tasks
- `/showtasks @user` - View tasks assigned to someone
- `/alltasks` - **[Admin]** View all server tasks (paginated)
- `/tcw @user add/remove` - **[Admin]** Manage task creator permissions

### 🎫 **Interactive Messages & Tickets**
- `/intmsg` - Create interactive messages with ticket/role buttons
- `/editintmsg [message_id]` - **[Staff]** Edit existing interactive messages
- `/listmessages` - **[Staff]** List all interactive messages
- `/ticketstats` - **[Staff]** View ticket statistics
- `/imw @user add/remove` - **[Admin]** Manage interactive message permissions

### 🎮 **Fun & Utility**
- `/quack` - Get a random duck image 🦆
- `/diceroll [1-100]` - Roll dice with visual results
- `/help` - Show comprehensive help information

### 🔧 **Admin & System**
- `/fixdb` - **[Admin]** Fix database schema issues
- `/testpersistence` - **[Admin]** Test persistence system

## 🔑 Permission System

- **[Admin]** - Requires Administrator permission
- **[Staff]** - Requires Manage Messages permission
- **Whitelisted** - Users added to specific command whitelists
- **Everyone** - Available to all server members

## 🛠️ Technical Details

### **Database Features:**
- SQLite database with automatic backups
- Persistent view storage for button interactions
- Automatic schema migration and error recovery
- Task scheduling and reminder system

### **Interactive System:**
- Custom ticket creation with dynamic questions
- Role management with add/remove actions
- Multi-button support with different styles
- Persistent across bot restarts

### **Advanced Formatting:**
- Pagination for large lists (5 items per page)
- Visual dice display with proper spacing
- @everyone/@here ping support in embeds
- Multi-line layouts for better readability

## 🚀 Deployment Options

### **Replit (Recommended for beginners):**
1. Create new Replit project
2. Upload bot files
3. Add `TOKEN` to Secrets
4. Use UptimeRobot for 24/7 uptime

### **VPS/Cloud Hosting:**
1. Install Python 3.8+
2. Install dependencies: `pip install -r requirements.txt`
3. Set environment variable: `export TOKEN=your_token_here`
4. Run: `python main.py`

### **Docker:**
```dockerfile
FROM python:3.9-slim
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["python", "main.py"]
```

## 📊 Usage Examples

### **Creating a Support Ticket System:**
1. Run `/intmsg` 
2. Set title: "Support Center"
3. Add description with @everyone for announcements
4. Add ticket button with custom questions
5. Set staff roles for ticket visibility

### **Setting Up Task Management:**
1. Whitelist users with `/tcw @user add`
2. Create tasks with `/task`
3. Track progress with `/mytasks`
4. Review all tasks with `/alltasks`

### **Fun Server Activities:**
1. Roll dice for games: `/diceroll 20`
2. Share duck pics: `/quack`
3. Get help anytime: `/help`

## 🔗 APIs & Credits

- **Duck Images:** [random-d.uk](https://random-d.uk/)
- **Discord Integration:** [discord.py](https://discordpy.readthedocs.io/)
- **Database:** SQLAlchemy with SQLite
- **Hosting:** Compatible with Replit, Heroku, VPS

## 🆘 Support & Troubleshooting

### **Common Issues:**
- **Buttons not working after restart:** Use `/testpersistence` to reload views
- **Database errors:** Run `/fixdb` to fix schema issues
- **Permission errors:** Check role permissions and whitelists
- **Commands not syncing:** Wait 1-2 minutes after bot restart

### **Getting Help:**
- Use `/help` for command information
- Check console logs for detailed error messages
- Ensure bot has proper permissions in your server
- Verify environment variables are set correctly

---

**Made with ❤️ for Discord communities!** 

*Report issues or suggest features by contacting the bot developers.*