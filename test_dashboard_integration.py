#!/usr/bin/env python3
"""
Test script to verify the dashboard integration works properly
"""

import subprocess
import os
import sys
import time

def test_dashboard_startup():
    """Test if the dashboard starts properly with bot"""
    print("🧪 Testing Dashboard Integration...")
    
    # Check if main.py exists
    if not os.path.exists('main.py'):
        print("❌ main.py not found")
        return False
    
    # Check if start_dashboard.py exists
    if not os.path.exists('start_dashboard.py'):
        print("❌ start_dashboard.py not found")
        return False
    
    print("✅ Required files found")
    
    # Test the web UI import
    try:
        from web_ui import start_bot, stop_bot, get_bot_status
        print("✅ Web UI functions imported successfully")
    except Exception as e:
        print(f"❌ Failed to import web UI: {e}")
        return False
    
    # Test bot status detection
    try:
        status = get_bot_status()
        print(f"📊 Current bot status: {'Running' if status.get('running') else 'Stopped'}")
    except Exception as e:
        print(f"❌ Failed to get bot status: {e}")
        return False
    
    print("✅ Dashboard integration test passed!")
    return True

def test_bot_start_stop():
    """Test bot start/stop functionality"""
    print("\n🧪 Testing Bot Start/Stop...")
    
    try:
        from web_ui import start_bot, stop_bot, get_bot_status
        
        # Test starting bot
        print("🤖 Testing bot start...")
        start_result = start_bot()
        print(f"Start result: {start_result}")
        
        if start_result:
            print("✅ Bot started successfully")
            
            # Wait a moment
            time.sleep(3)
            
            # Check status
            status = get_bot_status()
            print(f"Bot running: {status.get('running', False)}")
            
            # Test stopping bot
            print("🛑 Testing bot stop...")
            stop_result = stop_bot()
            print(f"Stop result: {stop_result}")
            
            if stop_result:
                print("✅ Bot stopped successfully")
                return True
            else:
                print("❌ Bot stop failed")
                return False
        else:
            print("❌ Bot start failed")
            return False
            
    except Exception as e:
        print(f"❌ Bot start/stop test failed: {e}")
        return False

def main():
    print("🦆 PuddlesBot Dashboard Integration Test")
    print("=" * 50)
    
    # Test 1: Dashboard startup
    startup_success = test_dashboard_startup()
    
    # Test 2: Bot start/stop
    bot_success = test_bot_start_stop()
    
    print("\n📋 Test Results:")
    print(f"  Dashboard Startup: {'✅ PASS' if startup_success else '❌ FAIL'}")
    print(f"  Bot Start/Stop:    {'✅ PASS' if bot_success else '❌ FAIL'}")
    
    if startup_success and bot_success:
        print("\n🎉 All tests passed!")
        print("🚀 You can now run: python start_dashboard.py")
        print("📊 The bot will start automatically and show output in the terminal")
    else:
        print("\n❌ Some tests failed. Check the output above for details.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
