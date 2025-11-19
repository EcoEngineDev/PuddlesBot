#!/usr/bin/env python3
"""
Test script to verify the ping system works
"""

import os
import time
import sqlite3
from datetime import datetime

def test_ping_system():
    """Test the ping system by simulating a command"""
    print("🧪 Testing Ping System...")
    
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Simulate a command execution
    print("📝 Simulating command execution...")
    
    # Create a test database
    db_path = 'data/commands_test_server.db'
    conn = sqlite3.connect(db_path)
    
    # Create table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS command_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command_name TEXT NOT NULL,
            user_id TEXT NOT NULL,
            channel_id TEXT NOT NULL,
            guild_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            success BOOLEAN NOT NULL DEFAULT 1
        )
    """)
    
    # Insert test command
    conn.execute("""
        INSERT INTO command_logs (command_name, user_id, channel_id, guild_id, timestamp, success)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ('test', '123456789', '987654321', 'test_server', 
          datetime.utcnow().isoformat(), True))
    
    conn.commit()
    conn.close()
    
    # Test the ping function
    print("📡 Testing ping function...")
    
    # Import the ping function from main.py
    try:
        import sys
        sys.path.append('.')
        from main import ping_web_ui
        
        # Call ping function
        ping_web_ui()
        print("✅ Ping function called successfully")
        
        # Check if ping file was created
        ping_file = 'data/dashboard_ping.txt'
        if os.path.exists(ping_file):
            with open(ping_file, 'r') as f:
                ping_time = f.read().strip()
            print(f"✅ Ping file created with timestamp: {ping_time}")
        else:
            print("⚠️  Ping file not created (web UI might not be running)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error testing ping system: {e}")
        return False

def test_web_ui_detection():
    """Test if web UI can detect the ping"""
    print("\n🧪 Testing Web UI Detection...")
    
    try:
        from web_ui import get_database_stats
        
        # Get stats to see if it picks up our test data
        get_database_stats()
        print("✅ Web UI stats function works")
        
        # Check if test data is in stats
        from web_ui import stats_cache
        if 'test_server' in stats_cache.get('server_commands', {}):
            print("✅ Web UI detected test command data")
            return True
        else:
            print("⚠️  Web UI didn't detect test data yet")
            return False
            
    except Exception as e:
        print(f"❌ Error testing web UI detection: {e}")
        return False

def cleanup_test_data():
    """Clean up test data"""
    print("\n🧹 Cleaning up test data...")
    
    try:
        # Remove test database
        if os.path.exists('data/commands_test_server.db'):
            os.remove('data/commands_test_server.db')
            print("✅ Removed test database")
        
        # Remove ping file
        if os.path.exists('data/dashboard_ping.txt'):
            os.remove('data/dashboard_ping.txt')
            print("✅ Removed ping file")
            
    except Exception as e:
        print(f"⚠️  Error cleaning up: {e}")

def main():
    print("🦆 PuddlesBot Ping System Test")
    print("=" * 40)
    
    # Test 1: Ping system
    ping_success = test_ping_system()
    
    # Test 2: Web UI detection
    webui_success = test_web_ui_detection()
    
    print("\n📋 Test Results:")
    print(f"  Ping System:      {'✅ PASS' if ping_success else '❌ FAIL'}")
    print(f"  Web UI Detection: {'✅ PASS' if webui_success else '❌ FAIL'}")
    
    if ping_success and webui_success:
        print("\n🎉 All tests passed!")
        print("📊 Ping system is working properly")
        print("🌐 Dashboard should update when commands are used")
    else:
        print("\n❌ Some tests failed. Check the output above for details.")
        if not ping_success:
            print("💡 Make sure main.py can be imported")
        if not webui_success:
            print("💡 Make sure web_ui.py can be imported")
    
    # Cleanup
    cleanup_test_data()
    
    return 0 if (ping_success and webui_success) else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
