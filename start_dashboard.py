#!/usr/bin/env python3
"""
PuddlesBot Dashboard Startup Script
Simple script to start the web dashboard.
"""

import os
import sys
import subprocess
import signal
import atexit
import argparse
import time
import threading

def check_requirements():
    """Check if Flask is installed"""
    try:
        import flask
        print("✅ Flask is available")
        return True
    except ImportError:
        print("❌ Flask not found. Installing...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "flask==3.0.0"])
            print("✅ Flask installed successfully")
            return True
        except subprocess.CalledProcessError:
            print("❌ Failed to install Flask. Please install it manually:")
            print("   pip install flask==3.0.0")
            return False

# Global variable to track bot process
bot_process = None

def start_bot():
    """Start the bot process"""
    global bot_process
    try:
        print("🤖 Starting PuddlesBot...")
        
        # Set up environment for Unicode support
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        
        # Try to use start_bot.bat on Windows, otherwise use python main.py
        if os.name == 'nt' and os.path.exists('start_bot.bat'):
            print("📝 Using start_bot.bat for Windows Unicode support")
            bot_process = subprocess.Popen(['start_bot.bat'], env=env, shell=True)
        else:
            print("🐍 Starting with python main.py")
            bot_process = subprocess.Popen([sys.executable, 'main.py'], env=env)
        
        # Give the bot time to start up
        print("⏳ Waiting for bot to initialize...")
        time.sleep(10)
        
        if bot_process.poll() is None:
            print("✅ Bot started successfully!")
            return True
        else:
            print("❌ Bot failed to start")
            return False
            
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        return False

def stop_bot():
    """Stop the bot process"""
    global bot_process
    if bot_process and bot_process.poll() is None:
        try:
            print("🛑 Stopping bot...")
            bot_process.terminate()
            bot_process.wait(timeout=10)
            print("✅ Bot stopped")
        except subprocess.TimeoutExpired:
            print("⚠️  Bot didn't stop gracefully, forcing...")
            bot_process.kill()
            bot_process.wait()
        except Exception as e:
            print(f"❌ Error stopping bot: {e}")

def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    print("\n👋 Shutting down...")
    stop_bot()
    print("👋 Goodbye!")
    sys.exit(0)

def cleanup():
    """Cleanup function for atexit"""
    stop_bot()

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='PuddlesBot Dashboard Launcher')
    parser.add_argument('-start', '--start-bot', action='store_true', 
                       help='Start the bot along with the dashboard')
    args = parser.parse_args()
    
    print("🦆 PuddlesBot Dashboard Launcher")
    print("=" * 40)
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)
    
    # Check if we're in the right directory
    if not os.path.exists('main.py'):
        print("❌ Error: Please run this script from the PuddlesBot directory")
        print("   (The directory containing main.py)")
        return 1
    
    # Check requirements
    if not check_requirements():
        return 1
    
    # Check if data directory exists
    if not os.path.exists('data'):
        print("⚠️  Warning: No data directory found. Creating it...")
        os.makedirs('data', exist_ok=True)
        print("✅ Data directory created")
    
    # Start the bot if requested
    if args.start_bot:
        print("\n🤖 Starting PuddlesBot...")
        if not start_bot():
            print("❌ Failed to start bot. Continuing with dashboard only...")
        else:
            print("✅ Bot is running!")
    
    # Start the web UI
    print("\n🚀 Starting PuddlesBot Web Dashboard...")
    print("📊 Dashboard will be available at: http://localhost:42069")
    if args.start_bot:
        print("🤖 Bot is running alongside the dashboard")
    else:
        print("📈 Monitor bot statistics and performance")
    print("🔄 Press Ctrl+C to stop everything")
    print("=" * 40)
    
    try:
        # Import the web UI
        from web_ui import app
        
        print("\n" + "=" * 40)
        print("🦆 PuddlesBot Dashboard is running!")
        print("📊 Web UI: http://localhost:42069")
        if args.start_bot:
            print("🤖 Bot is running in the background")
        print("🔄 Press Ctrl+C to stop everything")
        print("=" * 40)
        
        # Run the web UI
        app.run(host='0.0.0.0', port=42069, debug=False, use_reloader=False)
        
    except KeyboardInterrupt:
        print("\n👋 Dashboard stopped by user")
        return 0
    except Exception as e:
        print(f"\n❌ Error starting dashboard: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
