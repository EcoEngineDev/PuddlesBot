#!/usr/bin/env python3
"""
Music System Setup Script for PuddlesBot
Run this script to configure the music system for Replit deployment
"""

if __name__ == "__main__":
    try:
        from music_config import print_replit_setup_guide, validate_music_config, update_music_settings
        
        print("🎵 PuddlesBot Music System Setup")
        print("=" * 50)
        
        # Print the setup guide
        print_replit_setup_guide()
        
        # Try to configure if environment variables are set
        print("\n" + "=" * 50)
        print("🔧 ATTEMPTING AUTO-CONFIGURATION...")
        print("=" * 50)
        
        if validate_music_config():
            if update_music_settings():
                print("\n✅ SUCCESS!")
                print("🎉 Music system has been configured successfully!")
                print("🚀 You can now run your bot and use music commands!")
            else:
                print("\n❌ FAILED!")
                print("Configuration validation passed but settings update failed.")
        else:
            print("\n⚠️  CONFIGURATION NEEDED!")
            print("Please set the required environment variables in Replit Secrets:")
            print("1. Go to your Replit project")
            print("2. Click on 'Secrets' in the left sidebar")
            print("3. Add the required environment variables shown above")
            print("4. Run this script again")
        
        print("\n" + "=" * 50)
        print("📚 HELPFUL LINKS:")
        print("• Public Lavalink servers: https://lavalink.darrennathanael.com/")
        print("• Vocard documentation: https://docs.vocard.xyz/")
        print("• Discord.py documentation: https://discordpy.readthedocs.io/")
        print("=" * 50)
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure all dependencies are installed:")
        print("pip install -r requirements.txt")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        print("Please check your configuration and try again.") 