#!/usr/bin/env python3
"""
Test script to verify the global command logging system works
"""

import os
import sqlite3
import time
from datetime import datetime

def test_global_command_logging():
    """Test the global command logging system"""
    print("🧪 Testing Global Command Logging System...")
    
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    try:
        # Import the log_command function
        import sys
        sys.path.append('.')
        from main import log_command
        
        print("✅ Successfully imported log_command function")
        
        # Test logging various commands from different servers
        test_commands = [
            ("mytasks", "123456789", "111222333", "1303557871669084191", "Test Server 1"),
            ("taskedit", "123456789", "111222333", "1303557871669084191", "Test Server 1"),
            ("alltasks", "987654321", "444555666", "1325899128533680149", "Test Server 2"),
            ("snipe", "987654321", "444555666", "1325899128533680149", "Test Server 2"),
            ("task", "555666777", "777888999", "1373713234997153891", "Test Server 3"),
            ("showtasks", "555666777", "777888999", "1373713234997153891", "Test Server 3"),
        ]
        
        print(f"📝 Logging {len(test_commands)} test commands...")
        
        for i, (cmd_name, user_id, channel_id, guild_id, guild_name) in enumerate(test_commands):
            print(f"   {i+1}. Logging command: {cmd_name} from {guild_name}")
            log_command(
                command_name=cmd_name,
                user_id=user_id,
                channel_id=channel_id,
                guild_id=guild_id,
                success=True
            )
            time.sleep(0.1)  # Small delay between commands
        
        # Check if global database was created and populated
        db_path = "data/commands_global.db"
        if os.path.exists(db_path):
            print(f"✅ Global database created: {db_path}")
            
            # Check if data was inserted
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='command_logs'")
            if cursor.fetchone():
                print("✅ command_logs table exists")
                
                # Get command counts by server
                cursor.execute("""
                    SELECT guild_id, guild_name, COUNT(*) 
                    FROM command_logs 
                    GROUP BY guild_id, guild_name
                """)
                server_counts = cursor.fetchall()
                
                print("📊 Command usage by server:")
                for guild_id, guild_name, count in server_counts:
                    server_key = f"{guild_name} ({guild_id})" if guild_name else guild_id
                    print(f"   - {server_key}: {count} commands")
                
                # Get command counts by command name
                cursor.execute("""
                    SELECT command_name, COUNT(*) 
                    FROM command_logs 
                    GROUP BY command_name
                """)
                command_counts = cursor.fetchall()
                
                print("📊 Command usage by type:")
                for cmd, count in command_counts:
                    print(f"   - {cmd}: {count} times")
                
                # Get total count
                cursor.execute("SELECT COUNT(*) FROM command_logs")
                total = cursor.fetchone()[0]
                print(f"   Total commands logged: {total}")
                
            else:
                print("❌ command_logs table not found")
            
            conn.close()
            
        else:
            print(f"❌ Global database not created: {db_path}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Error testing global command logging: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_web_ui_with_global_data():
    """Test web UI with the global database data"""
    print("\n🌐 Testing Web UI with Global Database...")
    
    try:
        from web_ui import get_database_stats
        
        # Get stats
        get_database_stats()
        print("✅ Web UI stats function works")
        
        # Check if data is in stats
        from web_ui import stats_cache
        server_commands = stats_cache.get('server_commands', {})
        command_usage_24h = stats_cache.get('command_usage_24h', {})
        
        print(f"📊 Web UI detected {len(server_commands)} servers")
        for server_key, count in server_commands.items():
            print(f"   {server_key}: {count} commands")
        
        print(f"📈 24h command usage:")
        for cmd, count in command_usage_24h.items():
            print(f"   - {cmd}: {count} times")
        
        return len(server_commands) > 0
        
    except Exception as e:
        print(f"❌ Error testing web UI: {e}")
        import traceback
        traceback.print_exc()
        return False

def cleanup_test_data():
    """Clean up test data"""
    print("\n🧹 Cleaning up test data...")
    
    try:
        # Remove global database
        global_db = 'data/commands_global.db'
        if os.path.exists(global_db):
            os.remove(global_db)
            print("✅ Removed global database")
        
        # Remove ping file
        if os.path.exists('data/dashboard_ping.txt'):
            os.remove('data/dashboard_ping.txt')
            print("✅ Removed ping file")
            
    except Exception as e:
        print(f"⚠️  Error cleaning up: {e}")

def main():
    print("🦆 PuddlesBot Global Command Logging Test")
    print("=" * 50)
    
    # Test 1: Global command logging
    logging_success = test_global_command_logging()
    
    # Test 2: Web UI detection
    webui_success = test_web_ui_with_global_data()
    
    print("\n📋 Test Results:")
    print(f"  Global Command Logging: {'✅ PASS' if logging_success else '❌ FAIL'}")
    print(f"  Web UI Detection:       {'✅ PASS' if webui_success else '❌ FAIL'}")
    
    if logging_success and webui_success:
        print("\n🎉 All tests passed!")
        print("📊 Global command logging system is working properly")
        print("🌐 Dashboard should now show command data from all servers")
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
