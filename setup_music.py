#!/usr/bin/env python3
"""
Music System Setup Script for PuddlesBot
Run this script to configure the music system for local deployment
"""

import os
import json
from dotenv import load_dotenv

def print_setup_guide():
    """Print the setup guide for local deployment"""
    print("\n📝 REQUIRED ENVIRONMENT VARIABLES:")
    print("=" * 50)
    print("These variables should be set in your .env file:")
    print("\nRequired:")
    print("- DISCORD_TOKEN: Your Discord bot token")
    print("- DISCORD_CLIENT_ID: Your bot's client ID")
    print("\nOptional (for additional features):")
    print("- MONGODB_URL: MongoDB connection URL (for playlists)")
    print("- MONGODB_NAME: MongoDB database name")
    print("- GENIUS_TOKEN: Genius API token (for lyrics)")
    print("- LAVALINK_HOST: Lavalink server host")
    print("- LAVALINK_PORT: Lavalink server port")
    print("- LAVALINK_PASSWORD: Lavalink server password")
    print("- LAVALINK_SECURE: Whether to use SSL (true/false)")

def validate_config():
    """Validate that required environment variables are set"""
    load_dotenv()
    
    required_vars = ['DISCORD_TOKEN', 'DISCORD_CLIENT_ID']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        print("\n❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"- {var}")
        return False
    
    return True

def update_settings():
    """Update settings.json with environment variables"""
    try:
        settings_path = os.path.join(os.path.dirname(__file__), 'MusicSystem', 'settings.json')
        
        # Create default settings if file doesn't exist
        if not os.path.exists(settings_path):
            settings = {
                "token": "",
                "client_id": "",
                "genius_token": "",
                "mongodb_url": "",
                "mongodb_name": "",
                "nodes": {
                    "DEFAULT": {
                        "host": "",
                        "port": 2333,
                        "password": "youshallnotpass",
                        "secure": False,
                        "identifier": "DEFAULT"
                    }
                }
            }
        else:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
        
        # Update settings with environment variables
        settings['token'] = os.getenv('DISCORD_TOKEN', '')
        settings['client_id'] = os.getenv('DISCORD_CLIENT_ID', '')
        settings['genius_token'] = os.getenv('GENIUS_TOKEN', '')
        settings['mongodb_url'] = os.getenv('MONGODB_URL', '')
        settings['mongodb_name'] = os.getenv('MONGODB_NAME', '')
        
        # Update Lavalink node settings if provided
        if os.getenv('LAVALINK_HOST'):
            settings['nodes']['DEFAULT'].update({
                'host': os.getenv('LAVALINK_HOST'),
                'port': int(os.getenv('LAVALINK_PORT', 2333)),
                'password': os.getenv('LAVALINK_PASSWORD', 'youshallnotpass'),
                'secure': os.getenv('LAVALINK_SECURE', 'false').lower() == 'true'
            })
        
        # Save updated settings
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=4)
        
        return True
    except Exception as e:
        print(f"\n❌ Error updating settings: {e}")
        return False

if __name__ == "__main__":
    try:
        print("🎵 PuddlesBot Music System Setup")
        print("=" * 50)
        
        # Print the setup guide
        print_setup_guide()
        
        # Try to configure if environment variables are set
        print("\n" + "=" * 50)
        print("🔧 ATTEMPTING AUTO-CONFIGURATION...")
        print("=" * 50)
        
        if validate_config():
            if update_settings():
                print("\n✅ SUCCESS!")
                print("🎉 Music system has been configured successfully!")
                print("🚀 You can now run your bot and use music commands!")
            else:
                print("\n❌ FAILED!")
                print("Configuration validation passed but settings update failed.")
        else:
            print("\n⚠️  CONFIGURATION NEEDED!")
            print("Please set the required environment variables in your .env file")
            print("Then run this script again")
        
        print("\n" + "=" * 50)
        print("📚 HELPFUL LINKS:")
        print("• Public Lavalink servers: https://lavalink.darrennathanael.com/")
        print("• Vocard documentation: https://docs.vocard.xyz/")
        print("• Discord.py documentation: https://discordpy.readthedocs.io/")
        print("=" * 50)
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        print("Please check your configuration and try again.") 