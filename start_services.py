#!/usr/bin/env python3
"""
Startup script for Replit to run both Lavalink server and Discord bot
"""
import os
import subprocess
import time
import asyncio
import threading
import sys

def start_lavalink():
    """Start the Lavalink server"""
    print("🎵 Starting Lavalink server...")
    
    # Set Java environment
    java_home = os.path.join(os.getcwd(), "java17")
    java_bin = os.path.join(java_home, "bin", "java")
    
    os.environ["JAVA_HOME"] = java_home
    os.environ["PATH"] = f"{os.path.join(java_home, 'bin')}:{os.environ.get('PATH', '')}"
    
    try:
        # Start Lavalink server
        process = subprocess.Popen([
            java_bin, 
            "-jar", 
            "Lavalink.jar"
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        print("✅ Lavalink server started!")
        return process
    except Exception as e:
        print(f"❌ Failed to start Lavalink: {e}")
        return None

def start_bot():
    """Start the Discord bot"""
    print("🤖 Starting Discord bot...")
    time.sleep(10)  # Wait for Lavalink to initialize
    
    try:
        subprocess.run([sys.executable, "main.py"])
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")

def main():
    """Main startup function"""
    print("🚀 Starting services on Replit...")
    
    # Start Lavalink in a separate thread
    lavalink_thread = threading.Thread(target=start_lavalink, daemon=True)
    lavalink_thread.start()
    
    # Start the bot (this will block)
    start_bot()

if __name__ == "__main__":
    main() 