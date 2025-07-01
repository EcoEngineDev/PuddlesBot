"""
Music System Configuration Helper for Replit
This file helps configure the music system settings using environment variables
"""

import os
import json
from typing import Dict, Any

def get_music_config() -> Dict[str, Any]:
    """
    Get music system configuration from environment variables or defaults
    """
    config = {
        "token": os.getenv("DISCORD_TOKEN", ""),
        "client_id": os.getenv("DISCORD_CLIENT_ID", ""),
        "genius_token": os.getenv("GENIUS_TOKEN", ""),
        "mongodb_url": os.getenv("MONGODB_URL", ""),
        "mongodb_name": os.getenv("MONGODB_NAME", "PuddlesBot_Music"),
        "nodes": {
            "DEFAULT": {
                "host": "lavalink.jirayu.net",
                "port": 13592,
                "password": "youshallnotpass",
                "secure": False,
                "identifier": "DEFAULT"
            }   
        },
        "prefix": "?",
        "activity": [
            {"type": "listening", "name": "/play", "status": "online"}
        ],
        "logging": {
            "file": {
                "path": "./logs",
                "enable": True
            },
            "level": {
                "discord": "INFO",
                "vocard": "INFO",
                "ipc_client": "INFO"
            },
            "max-history": 30
        },
        "bot_access_user": [],
        "embed_color": "0x00ff00",
        "default_max_queue": 1000,
        "lyrics_platform": "lrclib",
        "invite_link": f"https://discord.com/oauth2/authorize?client_id={os.getenv('DISCORD_CLIENT_ID', 'YOUR_BOT_ID')}&permissions=8&scope=bot%20applications.commands",
        "server_invite_link": "https://discord.gg/your_server",
        "ipc_client": {
            "host": "127.0.0.1",
            "port": 8000,
            "password": "YOUR_PASSWORD",
            "secure": False,
            "enable": False
        },
        "sources_settings": {
            "youtube": {
                "emoji": "🎵",
                "color": "0xFF0000"
            },
            "youtubemusic": {
                "emoji": "🎵",
                "color": "0xFF0000"
            },
            "spotify": {
                "emoji": "🎧",
                "color": "0x1DB954"
            },
            "soundcloud": {
                "emoji": "🔗",
                "color": "0xFF7700"
            },
            "twitch": {
                "emoji": "📺",
                "color": "0x9B4AFF"
            },
            "bandcamp": {
                "emoji": "🎼",
                "color": "0x6F98A7"
            },
            "vimeo": {
                "emoji": "📹",
                "color": "0x1ABCEA"
            },
            "applemusic": {
                "emoji": "🍎",
                "color": "0xE298C4"
            },
            "reddit": {
                "emoji": "📱",
                "color": "0xFF5700"
            },
            "tiktok": {
                "emoji": "📱",
                "color": "0x74ECE9"
            },
            "others": {
                "emoji": "🔗",
                "color": "0xb3b3b3"
            }
        },
        "default_controller": {
            "embeds": {
                "active": {
                    "description": "**Now Playing: ```[@@track_name@@]```\nLink: [Click Me](@@track_url@@) | Requester: @@track_requester_mention@@**",
                    "footer": {
                        "text": "Queue Length: @@queue_length@@ | Duration: @@track_duration@@ | Volume: @@volume@@%"
                    },
                    "image": "@@track_thumbnail@@",
                    "author": {
                        "name": "Music Controller | @@channel_name@@",
                        "icon_url": "@@bot_icon@@"
                    },
                    "color": "@@track_color@@"
                },
                "inactive": {
                    "title": {
                        "name": "There are no songs playing right now"
                    },
                    "description": "Use `/play` to start playing music!",
                    "color": "@@default_embed_color@@"
                }
            },
            "default_buttons": [
                ["back", "resume", "skip", {"stop": "red"}],
                ["tracks"]
            ],
            "disableButtonText": False
        },
        "cooldowns": {
            "connect": [2, 30],
            "play": [1, 5]
        },
        "aliases": {
            "connect": ["join"],
            "leave": ["stop", "bye"],
            "play": ["p"],
            "view": ["v"]
        }
    }
    
    return config

def update_music_settings():
    """
    Update the music system settings.json file with environment variables
    """
    settings_path = os.path.join(os.path.dirname(__file__), 'MusicSystem', 'settings.json')
    
    # Create MusicSystem directory if it doesn't exist
    music_dir = os.path.join(os.path.dirname(__file__), 'MusicSystem')
    if not os.path.exists(music_dir):
        os.makedirs(music_dir)
    
    config = get_music_config()
    
    try:
        with open(settings_path, 'w') as f:
            json.dump(config, f, indent=4)
        print(f"✅ Music settings updated at {settings_path}")
        return True
    except Exception as e:
        print(f"❌ Failed to update music settings: {e}")
        return False

def validate_music_config() -> bool:
    """
    Validate that required environment variables are set
    """
    required_vars = ["DISCORD_TOKEN"]
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("Please set these variables in your Replit secrets:")
        for var in missing_vars:
            print(f"  - {var}")
        return False
    
    return True

def print_replit_setup_guide():
    """
    Print setup instructions for Replit
    """
    print("\n" + "="*60)
    print("🎵 MUSIC SYSTEM SETUP GUIDE FOR REPLIT")
    print("="*60)
    
    print("\n1. 📝 REQUIRED ENVIRONMENT VARIABLES (Replit Secrets):")
    print("   • DISCORD_TOKEN - Your Discord Bot Token")
    print("   • DISCORD_CLIENT_ID - Your Discord Bot Client ID")
    
    print("\n2. 🔧 OPTIONAL ENVIRONMENT VARIABLES:")
    print("   • MONGODB_URL - MongoDB connection URL (optional, for playlists)")
    print("   • MONGODB_NAME - MongoDB database name (default: PuddlesBot_Music)")
    print("   • GENIUS_TOKEN - Genius API token for lyrics (optional)")
    
    print("\n3. 🎛️ LAVALINK SERVER CONFIGURATION:")
    print("   • Using public Lavalink server: lavalink.jirayu.net:13592")
    print("   • This is already configured and ready to use!")
    
    print("\n4. 🎵 AVAILABLE MUSIC COMMANDS:")
    print("   • /play <song> - Play a song or add to queue")
    print("   • /skip - Skip current song")
    print("   • /stop - Stop music and disconnect")
    print("   • /pause - Pause current song")
    print("   • /resume - Resume paused song")
    print("   • /queue - Show music queue")
    print("   • /volume <0-100> - Set volume")
    print("   • /nowplaying - Show current song info")
    
    print("\n5. 📚 SUPPORTED SOURCES:")
    print("   • YouTube (search and direct links)")
    print("   • Spotify (track/playlist links)")
    print("   • SoundCloud")
    print("   • And more!")
    
    print("\n6. 🚀 TO GET STARTED:")
    print("   1. Set your DISCORD_TOKEN in Replit Secrets")
    print("   2. Set your DISCORD_CLIENT_ID in Replit Secrets")
    print("   3. Run the bot - music system will auto-configure!")
    print("   4. Use /play to start playing music!")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    print_replit_setup_guide()
    if validate_music_config():
        update_music_settings()
        print("✅ Music system configuration completed!")
    else:
        print("❌ Please set the required environment variables first.") 