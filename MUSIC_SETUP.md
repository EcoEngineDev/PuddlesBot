# 🎵 Music System Setup Guide

## 🔧 **Quick Fix for Current Issues**

### **Step 1: Install FFmpeg (Replit)**
1. The `replit.nix` file has been created for you
2. **Restart your Repl** completely to install FFmpeg:
   - Click the "Run" button to stop the current process
   - Click "Run" again to restart with FFmpeg

### **Step 2: Install Python Dependencies**
Run this command in the Shell tab:
```bash
pip install yt-dlp==2024.12.13 PyNaCl==1.5.0 spotipy==2.24.0 aiofiles==24.1.0
```

### **Step 3: Check Setup**
1. Restart your bot
2. Use `/musicdebug` command to verify everything is working
3. Try `/play never gonna give you up` to test

## 🚨 **Common Issues & Solutions**

### **Error: "ffmpeg was not found"**
- **Replit**: Make sure you restarted the Repl after creating `replit.nix`
- **Local**: Download from [ffmpeg.org](https://ffmpeg.org/download.html)

### **Error: "WebSocket closed with 4006"**
This is a Discord voice connection issue:

1. **Check Bot Permissions:**
   - Bot needs `Connect` and `Speak` permissions in voice channels
   - Bot needs `Use Voice Activity` permission

2. **Try These Steps:**
   - Leave and rejoin the voice channel
   - Make sure voice channel isn't full
   - Try a different voice channel
   - Restart the bot

3. **Server Region Issues:**
   - Try changing your Discord server's voice region
   - Some regions have better connectivity

### **Error: "You need to be in a voice channel"**
- Join a voice channel before using music commands
- Make sure the bot can see the voice channel

## 🎵 **Music Commands Quick Reference**

### **Basic Playback:**
- `/play <song>` - Play YouTube videos or Spotify tracks
- `/pause` / `/resume` - Control playback
- `/skip` - Skip current song (vote skip for multiple users)
- `/stop` - Stop and clear queue

### **Queue Management:**
- `/queue` - Show current queue
- `/remove <position>` - Remove specific song
- `/clear` - Clear entire queue
- `/shuffle` - Randomize queue

### **Advanced:**
- `/volume <1-100>` - Set volume
- `/loop <off/song/queue>` - Set loop mode
- `/nowplaying` - Current song info
- `/search <query>` - Search without playing

### **Troubleshooting:**
- `/musicdebug` - Check system status
- `/leave` - Force disconnect

## 🎯 **Supported Sources**

### **YouTube:**
- Direct URLs: `https://www.youtube.com/watch?v=...`
- Playlist URLs: `https://www.youtube.com/playlist?list=...`
- Search queries: `"rick astley never gonna give you up"`

### **Spotify (via YouTube):**
- Track URLs: `https://open.spotify.com/track/...`
- Playlist URLs: `https://open.spotify.com/playlist/...`
- *(Searches YouTube for the actual audio)*

## 🔑 **Optional: Spotify API Setup**

For better Spotify integration:

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
2. Create a new app
3. Add these to your environment variables:
   ```
   SPOTIFY_CLIENT_ID=your_client_id
   SPOTIFY_CLIENT_SECRET=your_client_secret
   ```

*(Music works without this, but Spotify integration will be more accurate)*

## 📞 **Still Having Issues?**

1. Use `/musicdebug` to check system status
2. Check the console logs for detailed error messages
3. Make sure all dependencies are installed
4. Verify bot permissions in voice channels
5. Try restarting the bot completely

The music system should work once FFmpeg is properly installed! 🎵 