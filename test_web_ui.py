#!/usr/bin/env python3
"""
Simple test script for the PuddlesBot Web UI
Tests basic functionality without requiring the full bot to be running.
"""

import os
import sys
import sqlite3
import json
from datetime import datetime, timedelta

def create_test_data():
    """Create some test data for the web UI"""
    print("🧪 Creating test data...")
    
    # Create data directory
    os.makedirs('data', exist_ok=True)
    
    # Create test command logs
    test_servers = [
        ('123456789', 'Test Server 1'),
        ('987654321', 'Test Server 2'),
        ('555666777', 'Test Server 3')
    ]
    
    commands = ['help', 'task', 'mytasks', 'music', 'dice', 'fun', 'level']
    
    for server_id, server_name in test_servers:
        db_path = f'data/commands_{server_id}.db'
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
        
        # Add test data
        now = datetime.now()
        for i in range(50):  # 50 commands per server
            timestamp = (now - timedelta(hours=i*2)).isoformat()
            command = commands[i % len(commands)]
            user_id = f"user_{i % 10}"
            channel_id = f"channel_{i % 3}"
            
            conn.execute("""
                INSERT INTO command_logs (command_name, user_id, channel_id, guild_id, timestamp, success)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (command, user_id, channel_id, server_id, timestamp, True))
        
        conn.commit()
        conn.close()
        print(f"  ✅ Created test data for {server_name}")
    
    # Create test guild cache
    guild_data = {
        'guilds': [
            {'id': int(server_id), 'name': server_name, 'member_count': 100 + i * 50, 'owner_id': 123}
            for i, (server_id, server_name) in enumerate(test_servers)
        ],
        'total_users': 500,
        'last_updated': datetime.now().isoformat()
    }
    
    with open('guild_cache.json', 'w') as f:
        json.dump(guild_data, f, indent=2)
    
    print("  ✅ Created test guild cache")
    print("✅ Test data creation complete!")

def test_web_ui():
    """Test the web UI functionality"""
    print("🧪 Testing Web UI functionality...")
    
    try:
        # Import the web UI module
        from web_ui import get_database_stats, get_bot_status
        
        # Test database stats
        print("  📊 Testing database statistics...")
        get_database_stats()
        print("  ✅ Database statistics working")
        
        # Test bot status
        print("  🤖 Testing bot status...")
        status = get_bot_status()
        print(f"  📊 Bot running: {status.get('running', False)}")
        print("  ✅ Bot status working")
        
        print("✅ Web UI functionality test complete!")
        return True
        
    except ImportError as e:
        print(f"  ❌ Import error: {e}")
        print("  💡 Try installing Flask: pip install flask==3.0.0")
        return False
    except Exception as e:
        print(f"  ❌ Test error: {e}")
        return False

def cleanup_test_data():
    """Clean up test data"""
    print("🧹 Cleaning up test data...")
    
    # Remove test databases
    data_dir = 'data'
    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            if filename.startswith('commands_') and filename.endswith('.db'):
                os.remove(os.path.join(data_dir, filename))
                print(f"  🗑️ Removed {filename}")
    
    # Remove guild cache
    if os.path.exists('guild_cache.json'):
        os.remove('guild_cache.json')
        print("  🗑️ Removed guild_cache.json")
    
    print("✅ Cleanup complete!")

def main():
    """Main test function"""
    print("🦆 PuddlesBot Web UI Test Suite")
    print("=" * 40)
    
    if len(sys.argv) > 1 and sys.argv[1] == '--cleanup':
        cleanup_test_data()
        return 0
    
    # Create test data
    create_test_data()
    
    # Test functionality
    success = test_web_ui()
    
    if success:
        print("\n🎉 All tests passed!")
        print("🚀 You can now start the web UI with:")
        print("   python start_dashboard.py")
        print("\n🧹 To clean up test data, run:")
        print("   python test_web_ui.py --cleanup")
    else:
        print("\n❌ Some tests failed. Check the output above.")
        cleanup_test_data()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
