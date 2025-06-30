# 🎵 Lavalink Music Bot - Replit Setup Guide

This guide will help you set up the music bot with Lavalink on Replit **without using replit.nix**.

## 🚀 Quick Start

### Step 1: Upload Your Files
Upload all your bot files to Replit, including:
- `main.py`
- `music.py` (the new Lavalink version)
- `requirements.txt`
- `setup_replit.sh`
- `start_services.py`
- All other bot modules

### Step 2: Run the Setup Script
In the Replit Shell, run:
```bash
chmod +x setup_replit.sh
./setup_replit.sh
```

This will automatically:
- ✅ Install Java 17
- ✅ Download Lavalink server
- ✅ Create Lavalink configuration
- ✅ Install Python dependencies
- ✅ Set up environment scripts

### Step 3: Start the Services
Once setup is complete, run:
```bash
python start_services.py
```

This will start both:
1. **Lavalink server** (handles music streaming)
2. **Discord bot** (your bot with music commands)

## 🎵 Music Commands Available

- `/play <song/url>` - Play YouTube links, Spotify tracks, or search
- `/pause` - Pause current song
- `/resume` - Resume paused music
- `/skip` - Skip current song
- `/stop` - Stop music and clear queue
- `/disconnect` - Leave voice channel
- `/musicstatus` - Check system status (Admin)

## 🔧 Manual Setup (Alternative)

If the automatic setup doesn't work, run these commands manually:

### Install Java 17:
```bash
wget https://download.oracle.com/java/17/latest/jdk-17_linux-x64_bin.tar.gz
tar -xzf jdk-17_linux-x64_bin.tar.gz
mv jdk-17.* java17
export JAVA_HOME=$PWD/java17
export PATH=$PWD/java17/bin:$PATH
```

### Download Lavalink:
```bash
wget https://github.com/lavalink-devs/Lavalink/releases/latest/download/Lavalink.jar
```

### Install Python dependencies:
```bash
pip install lavalink==5.9.0
```

### Start services:
```bash
python start_services.py
```

## ⚠️ Important Notes

### Replit Limitations
- **Memory**: Lavalink + Bot may hit memory limits on free Replit
- **CPU**: Music processing is CPU-intensive
- **Persistence**: Files may be lost on restart (upgrade to keep files)

### Troubleshooting

**If Java installation fails:**
```bash
# Try alternative Java download
wget https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.9%2B9/OpenJDK17U-jdk_x64_linux_hotspot_17.0.9_9.tar.gz
tar -xzf OpenJDK17U-jdk_x64_linux_hotspot_17.0.9_9.tar.gz
mv jdk-17.* java17
```

**If Lavalink won't start:**
- Check Java version: `java -version`
- Check if port 2333 is available
- Look at Lavalink logs in the console

**If bot can't connect to Lavalink:**
- Make sure Lavalink started successfully
- Check that port 2333 is open
- Verify the password in `music.py` matches `application.yml`

## 🌟 Alternative: Hosted Lavalink

If Replit has issues running Lavalink, you can use a hosted service:

1. **Get a hosted Lavalink node** from:
   - [Lavalink.cloud](https://lavalink.cloud)
   - [FreeLavalink](https://freelavalink.ga)
   - Or any other Lavalink hosting service

2. **Update `music.py`** with the hosted node details:
```python
_lavalink.add_node(
    host='your-hosted-lavalink.com',  # Hosted URL
    port=443,                         # Hosted port  
    password='your-hosted-password',  # Hosted password
    region='us',
    name='hosted-node'
)
```

3. **Run just the bot**:
```bash
python main.py
```

## 🎉 Success!

Once everything is running, you should see:
```
🎵 Lavalink server started!
🤖 Starting Discord bot...
🎵 Lavalink music system initialized
✅ Bot is ready!
```

Your music bot is now ready to use! Test it with `/play never gonna give you up` 🎵 