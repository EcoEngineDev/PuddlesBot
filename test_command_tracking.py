#!/usr/bin/env python3
"""
Test script to verify command tracking is working
"""

import os
import sqlite3
import time
from datetime import datetime, timedelta

def test_command_tracking():
    """Test if command tracking is working"""
    print("🧪 Testing Command Tracking...")
    
    # Check if data directory exists
    if not os.path.exists('data'):
        print("❌ Data directory not found")
        return False
    
    # Look for command log databases
    command_dbs = []
    for filename in os.listdir('data'):
        if filename.startswith('commands_') and filename.endswith('.db'):
            command_dbs.append(filename)
    
    if not command_dbs:
        print("❌ No command log databases found")
        print("💡 Try running some Discord commands first")
        return False
    
    print(f"✅ Found {len(command_dbs)} command log databases")
    
    total_commands = 0
    recent_commands = 0
    
    # Check each database
    for db_file in command_dbs:
        db_path = os.path.join('data', db_file)
        server_id = db_file.replace('commands_', '').replace('.db', '')
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='command_logs'
            """)
            
            if not cursor.fetchone():
                print(f"⚠️  No command_logs table in {db_file}")
                continue
            
            # Get total commands
            cursor.execute("SELECT COUNT(*) FROM command_logs")
            count = cursor.fetchone()[0]
            total_commands += count
            
            # Get recent commands (last 24 hours)
            day_ago = (datetime.now() - timedelta(days=1)).isoformat()
            cursor.execute("""
                SELECT COUNT(*) FROM command_logs 
                WHERE timestamp > ?
            """, (day_ago,))
            recent = cursor.fetchone()[0]
            recent_commands += recent
            
            print(f"  📊 {server_id}: {count} total commands, {recent} recent")
            
            # Show some sample commands
            cursor.execute("""
                SELECT command_name, timestamp, success 
                FROM command_logs 
                ORDER BY timestamp DESC 
                LIMIT 5
            """)
            samples = cursor.fetchall()
            
            if samples:
                print(f"    Recent commands:")
                for cmd, timestamp, success in samples:
                    status = "✅" if success else "❌"
                    print(f"      {status} /{cmd} at {timestamp}")
            
            conn.close()
            
        except Exception as e:
            print(f"❌ Error reading {db_file}: {e}")
            continue
    
    print(f"\n📈 Summary:")
    print(f"  Total commands tracked: {total_commands}")
    print(f"  Commands in last 24h: {recent_commands}")
    
    if total_commands > 0:
        print("✅ Command tracking is working!")
        return True
    else:
        print("❌ No commands found in databases")
        return False

def test_web_ui_stats():
    """Test if web UI can read stats properly"""
    print("\n🧪 Testing Web UI Stats...")
    
    try:
        from web_ui import get_database_stats
        get_database_stats()
        print("✅ Web UI stats function works")
        return True
    except Exception as e:
        print(f"❌ Web UI stats failed: {e}")
        return False

def main():
    print("🦆 PuddlesBot Command Tracking Test")
    print("=" * 40)
    
    # Test 1: Command tracking
    tracking_success = test_command_tracking()
    
    # Test 2: Web UI stats
    webui_success = test_web_ui_stats()
    
    print("\n📋 Test Results:")
    print(f"  Command Tracking: {'✅ PASS' if tracking_success else '❌ FAIL'}")
    print(f"  Web UI Stats:     {'✅ PASS' if webui_success else '❌ FAIL'}")
    
    if tracking_success and webui_success:
        print("\n🎉 All tests passed!")
        print("📊 Command tracking is working properly")
        print("🌐 Web dashboard should show accurate statistics")
    else:
        print("\n❌ Some tests failed. Check the output above for details.")
        if not tracking_success:
            print("💡 Try running some Discord commands to generate data")
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
