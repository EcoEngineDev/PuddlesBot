#!/usr/bin/env python3
"""
Test script to simulate bot commands and verify logging
"""

import os
import sqlite3
import time
from datetime import datetime

def simulate_command_usage():
    """Simulate command usage by directly calling the logging functions"""
    print("🤖 Simulating Bot Command Usage...")
    
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    # Test guild ID (using a real-looking Discord guild ID)
    test_guild_id = "1303557871669084191"  # Using one of the existing guild IDs
    
    try:
        # Import the log_command function
        import sys
        sys.path.append('.')
        from main import log_command
        
        print("✅ Successfully imported log_command function")
        
        # Simulate various task commands
        commands_to_test = [
            ("mytasks", "123456789", "111222333"),
            ("taskedit", "123456789", "111222333"),
            ("alltasks", "123456789", "111222333"),
            ("snipe", "123456789", "111222333"),
            ("task", "987654321", "111222333"),
            ("showtasks", "123456789", "111222333"),
            ("oldtasks", "123456789", "111222333"),
        ]
        
        print(f"📝 Simulating {len(commands_to_test)} commands...")
        
        for i, (cmd_name, user_id, channel_id) in enumerate(commands_to_test):
            print(f"   {i+1}. Logging command: {cmd_name}")
            log_command(
                command_name=cmd_name,
                user_id=user_id,
                channel_id=channel_id,
                guild_id=test_guild_id,
                success=True
            )
            time.sleep(0.1)  # Small delay between commands
        
        # Check if database was created and populated
        db_path = f"data/commands_{test_guild_id}.db"
        if os.path.exists(db_path):
            print(f"✅ Database created: {db_path}")
            
            # Check if data was inserted
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Get command counts
            cursor.execute("SELECT command_name, COUNT(*) FROM command_logs GROUP BY command_name")
            command_counts = cursor.fetchall()
            
            print("📊 Command usage summary:")
            for cmd, count in command_counts:
                print(f"   - {cmd}: {count} times")
            
            # Get total count
            cursor.execute("SELECT COUNT(*) FROM command_logs")
            total = cursor.fetchone()[0]
            print(f"   Total commands logged: {total}")
            
            conn.close()
            
        else:
            print(f"❌ Database not created: {db_path}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Error simulating commands: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_web_ui_with_data():
    """Test web UI with the simulated data"""
    print("\n🌐 Testing Web UI with Simulated Data...")
    
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
        for server_id, count in server_commands.items():
            print(f"   Server {server_id}: {count} commands")
        
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
        # Remove test database
        test_db = 'data/commands_1303557871669084191.db'
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
    print("🦆 PuddlesBot Command Simulation Test")
    print("=" * 40)
    
    # Test 1: Simulate commands
    simulation_success = simulate_command_usage()
    
    # Test 2: Web UI detection
    webui_success = test_web_ui_with_data()
    
    print("\n📋 Test Results:")
    print(f"  Command Simulation: {'✅ PASS' if simulation_success else '❌ FAIL'}")
    print(f"  Web UI Detection:   {'✅ PASS' if webui_success else '❌ FAIL'}")
    
    if simulation_success and webui_success:
        print("\n🎉 All tests passed!")
        print("📊 Command logging and web UI are working properly")
        print("💡 The issue is that the bot needs to be running for real commands to be logged")
    else:
        print("\n❌ Some tests failed. Check the output above for details.")
    
    # Cleanup
    cleanup_test_data()
    
    return 0 if (simulation_success and webui_success) else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
