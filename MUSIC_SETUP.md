# 🎵 PuddlesBot Music System Setup Guide

This guide will help you integrate the Vocard music system into your PuddlesBot and deploy it on Replit.

## 🚀 Quick Start

1. **Run the setup script:**
   ```bash
   python setup_music.py
   ```

2. **Set required environment variables in Replit Secrets:**
   - `DISCORD_TOKEN` - Your Discord Bot Token
   - `DISCORD_CLIENT_ID` - Your Discord Bot Client ID

3. **Optional environment variables:**
   - `MONGODB_URL` - MongoDB connection URL (for playlists and user data)
   - `MONGODB_NAME` - MongoDB database name (default: PuddlesBot_Music)
   - `GENIUS_TOKEN` - Genius API token for lyrics (optional)

## 🎛️ Lavalink Configuration

The music system is pre-configured to use a public Lavalink server:
- **Host:** `lavalink.jirayu.net`
- **Port:** `13592`
- **Password:** `youshallnotpass`
- **Secure:** `false` (No SSL)

This server provides reliable Lavalink v4 service for music playback.

## 🎵 Available Music Commands

| Command | Description |
|---------|-------------|
| `/play <song>` | Play a song or add to queue |
| `/skip` | Skip current song |
| `/stop` | Stop music and disconnect |
| `/pause` | Pause current song |
| `/resume` | Resume paused song |
| `/queue` | Show music queue |
| `/volume <0-100>` | Set volume |
| `/nowplaying` | Show current song info |

## 📚 Supported Sources

- ✅ **YouTube** (search and direct links)
- ✅ **Spotify** (track/playlist links)
- ✅ **SoundCloud**
- ✅ **Twitch**
- ✅ **Bandcamp**
- ✅ **Vimeo**
- ✅ **Apple Music**
- ✅ **Direct audio/video URLs**

## 🔧 Technical Details

### Architecture
- **Music Library:** Based on Vocard v2.7.1
- **Lavalink Client:** lavaplay.py v1.0.17+
- **Database:** MongoDB (optional, for playlists)
- **Integration:** Modular system integrated with existing PuddlesBot

### File Structure
```
PuddlesBot/
├── main.py                 # Main bot file (updated)
├── music.py               # Music integration module (new)
├── music_config.py        # Configuration helper (new)
├── setup_music.py         # Setup script (new)
├── requirements.txt       # Updated with music dependencies
└── MusicSystem/           # Vocard music system
    ├── settings.json      # Music system configuration
    ├── main.py           # Vocard main file
    ├── function.py       # Core functions
    ├── requirements.txt  # Music system dependencies
    └── ...               # Other Vocard components
```

## 🐛 Troubleshooting

### Common Issues

**1. "Music system not properly initialized" error:**
- Check that `DISCORD_TOKEN` is set in Replit Secrets
- Run `python setup_music.py` to reconfigure
- Check console logs for connection errors

**2. "Failed to connect to Lavalink nodes" error:**
- Public Lavalink server might be down
- Check your internet connection
- Try alternative Lavalink servers from [this list](https://lavalink.darrennathanael.com/)

**3. "No tracks found" error:**
- Check if the search query is valid
- Try different search terms
- Ensure Lavalink server supports the requested source

**4. Bot doesn't join voice channel:**
- Ensure bot has proper permissions in the server
- Check that you're in a voice channel when using commands
- Verify bot has "Connect" and "Speak" permissions

### Alternative Lavalink Servers

If the default server is down, you can use these alternatives:

1. **Free servers:**
   - `lava-v3.ajieblogs.eu.org:443` (SSL)
   - `lava-all.ajieblogs.eu.org:443` (SSL)

2. **To change servers:**
   - Edit `MusicSystem/settings.json`
   - Update the `nodes` section with new server details
   - Restart the bot

## 📝 Environment Variables Reference

```bash
# Required
DISCORD_TOKEN=your_bot_token_here
DISCORD_CLIENT_ID=your_bot_client_id_here

# Optional
MONGODB_URL=mongodb://your_mongodb_url
MONGODB_NAME=PuddlesBot_Music
GENIUS_TOKEN=your_genius_token_for_lyrics
```

## 🔗 Useful Links

- [Vocard GitHub](https://github.com/ChocoMeow/Vocard)
- [Vocard Documentation](https://docs.vocard.xyz/)
- [Free Lavalink Servers](https://lavalink.darrennathanael.com/)
- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [Lavalink Official](https://github.com/freyacodes/Lavalink)

## 📄 License

The music system is based on Vocard, which is licensed under the MIT License. See the [LICENSE](MusicSystem/LICENSE) file for details.

---

**Need help?** Join the [Vocard Discord Server](https://discord.gg/vocard) for community support! 