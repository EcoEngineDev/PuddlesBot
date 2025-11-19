#!/usr/bin/env python3
"""
Test script to verify command logging is working
"""

import os
import sqlite3
import time
from datetime import datetime

def test_command_logging():
    """Test the command logging system"""
    print("🧪 Testing Command Logging System...")
    
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Test guild ID
    test_guild_id = "123456789"
    
    # Test the log_command function
    try:
        # Import the log_command function
        import sys
        sys.path.append('.')
        from main import log_command
        
        print("✅ Successfully imported log_command function")
        
        # Test logging a command
        print("📝 Testing command logging...")
        log_command(
            command_name="test_command",
            user_id="987654321",
            channel_id="111222333",
            guild_id=test_guild_id,
            success=True
        )
        
        # Check if database was created
        db_path = f"data/commands_{test_guild_id}.db"
        if os.path.exists(db_path):
            print(f"✅ Database created: {db_path}")
            
            # Check if data was inserted
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='command_logs'")
            if cursor.fetchone():
                print("✅ command_logs table exists")
                
                # Check if data was inserted
                cursor.execute("SELECT COUNT(*) FROM command_logs")
                count = cursor.fetchone()[0]
                print(f"✅ Found {count} command log entries")
                
                # Show the data
                cursor.execute("SELECT * FROM command_logs")
                rows = cursor.fetchall()
                for row in rows:
                    print(f"   - {row}")
                
            else:
                print("❌ command_logs table not found")
            
            conn.close()
            
        else:
            print(f"❌ Database not created: {db_path}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Error testing command logging: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_web_ui_detection():
    """Test if web UI can detect the test data"""
    print("\n🧪 Testing Web UI Detection...")
    
    try:
        from web_ui import get_database_stats
        
        # Get stats to see if it picks up our test data
        get_database_stats()
        print("✅ Web UI stats function works")
        
        # Check if test data is in stats
        from web_ui import stats_cache
        if '123456789' in stats_cache.get('server_commands', {}):
            print("✅ Web UI detected test command data")
            print(f"   Server commands: {stats_cache.get('server_commands', {})}")
            return True
        else:
            print("⚠️  Web UI didn't detect test data yet")
            print(f"   Available servers: {list(stats_cache.get('server_commands', {}).keys())}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing web UI detection: {e}")
        import traceback
        traceback.print_exc()
        return False

def cleanup_test_data():
    """Clean up test data"""
    print("\n🧹 Cleaning up test data...")
    
    try:
        # Remove test database
        test_db = 'data/commands_123456789.db'
        if os.path.exists(test_db):
            os.remove(test_db)
            print("✅ Removed test database")
        
        # Remove ping file
        if os.path.exists('data/dashboard_ping.txt'):
            os.remove('data/dashboard_ping.txt')
            print("✅ Removed ping file")
            
    except Exception as e:
        print(f"⚠️  Error cleaning up: {e}")

def main():
    print("🦆 PuddlesBot Command Logging Test")
    print("=" * 40)
    
    # Test 1: Command logging
    logging_success = test_command_logging()
    
    # Test 2: Web UI detection
    webui_success = test_web_ui_detection()
    
    print("\n📋 Test Results:")
    print(f"  Command Logging:  {'✅ PASS' if logging_success else '❌ FAIL'}")
    print(f"  Web UI Detection: {'✅ PASS' if webui_success else '❌ FAIL'}")
    
    if logging_success and webui_success:
        print("\n🎉 All tests passed!")
        print("📊 Command logging system is working properly")
    else:
        print("\n❌ Some tests failed. Check the output above for details.")
        if not logging_success:
            print("💡 Check if main.py can be imported and log_command function works")
        if not webui_success:
            print("💡 Check if web_ui.py can be imported and get_database_stats works")
    
    # Cleanup
    cleanup_test_data()
    
    return 0 if (logging_success and webui_success) else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
