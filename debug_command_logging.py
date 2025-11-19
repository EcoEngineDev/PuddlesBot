#!/usr/bin/env python3
"""
Debug script to test command logging in the actual bot
"""

import os
import sqlite3
import time
from datetime import datetime

def check_global_database():
    """Check if global database exists and has data"""
    print("🔍 Checking Global Database...")
    
    db_path = "data/commands_global.db"
    if not os.path.exists(db_path):
        print("❌ Global database does not exist")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='command_logs'")
        if not cursor.fetchone():
            print("❌ command_logs table does not exist")
            return False
        
        # Get total count
        cursor.execute("SELECT COUNT(*) FROM command_logs")
        total = cursor.fetchone()[0]
        print(f"📊 Total commands in database: {total}")
        
        if total > 0:
            # Get recent commands
            cursor.execute("""
                SELECT command_name, guild_id, guild_name, timestamp 
                FROM command_logs 
                ORDER BY timestamp DESC 
                LIMIT 10
            """)
            recent = cursor.fetchall()
            
            print("📝 Recent commands:")
            for cmd, guild_id, guild_name, timestamp in recent:
                server_key = f"{guild_name} ({guild_id})" if guild_name else guild_id
                print(f"   - {cmd} from {server_key} at {timestamp}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

def test_log_command_directly():
    """Test log_command function directly"""
    print("\n🧪 Testing log_command function directly...")
    
    try:
        import sys
        sys.path.append('.')
        from main import log_command
        
        print("✅ Successfully imported log_command function")
        
        # Test logging a command
        print("📝 Logging test command...")
        log_command(
            command_name="debug_test",
            user_id="123456789",
            channel_id="111222333",
            guild_id="999888777",
            success=True
        )
        
        print("✅ Command logged successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error testing log_command: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_web_ui_stats():
    """Check if web UI can read the data"""
    print("\n🌐 Checking Web UI Stats...")
    
    try:
        from web_ui import get_database_stats, stats_cache
        
        # Get stats
        get_database_stats()
        print("✅ Web UI stats function works")
        
        # Check cache
        server_commands = stats_cache.get('server_commands', {})
        command_usage_24h = stats_cache.get('command_usage_24h', {})
        
        print(f"📊 Servers in cache: {len(server_commands)}")
        for server_key, count in server_commands.items():
            print(f"   - {server_key}: {count} commands")
        
        print(f"📈 24h commands: {len(command_usage_24h)}")
        for cmd, count in command_usage_24h.items():
            print(f"   - {cmd}: {count} times")
        
        return len(server_commands) > 0
        
    except Exception as e:
        print(f"❌ Error checking web UI: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🦆 PuddlesBot Command Logging Debug")
    print("=" * 50)
    
    # Check 1: Global database
    db_exists = check_global_database()
    
    # Check 2: Direct log_command test
    direct_test = test_log_command_directly()
    
    # Check 3: Web UI stats
    webui_works = check_web_ui_stats()
    
    print("\n📋 Debug Results:")
    print(f"  Global Database:     {'✅ EXISTS' if db_exists else '❌ MISSING'}")
    print(f"  Direct Logging:      {'✅ WORKS' if direct_test else '❌ FAILED'}")
    print(f"  Web UI Stats:        {'✅ WORKS' if webui_works else '❌ FAILED'}")
    
    if not db_exists:
        print("\n💡 The global database doesn't exist. This means no commands have been logged yet.")
        print("   Try using some Discord commands with the bot running.")
    
    if not direct_test:
        print("\n💡 The log_command function is not working. Check for import errors.")
    
    if not webui_works:
        print("\n💡 The web UI can't read the data. Check the get_database_stats function.")
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
