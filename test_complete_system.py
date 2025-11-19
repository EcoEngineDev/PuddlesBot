#!/usr/bin/env python3
"""
Complete system test for command logging and web UI
"""

import os
import sqlite3
import time
import requests
from datetime import datetime

def test_database_exists():
    """Test if global database exists"""
    print("🔍 Testing Global Database...")
    
    db_path = "data/commands_global.db"
    if not os.path.exists(db_path):
        print("❌ Global database does not exist")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check table structure
        cursor.execute("PRAGMA table_info(command_logs)")
        columns = cursor.fetchall()
        print(f"✅ Database exists with {len(columns)} columns")
        
        # Check data
        cursor.execute("SELECT COUNT(*) FROM command_logs")
        count = cursor.fetchone()[0]
        print(f"📊 Total commands: {count}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def test_web_ui_api():
    """Test web UI API endpoints"""
    print("\n🌐 Testing Web UI API...")
    
    try:
        # Test status endpoint
        response = requests.get('http://localhost:42069/api/status', timeout=5)
        if response.status_code == 200:
            print("✅ Status API working")
        else:
            print(f"❌ Status API failed: {response.status_code}")
            return False
        
        # Test stats endpoint
        response = requests.get('http://localhost:42069/api/stats', timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Stats API working - {len(data.get('server_commands', {}))} servers")
        else:
            print(f"❌ Stats API failed: {response.status_code}")
            return False
        
        # Test refresh endpoint
        response = requests.post('http://localhost:42069/api/refresh', timeout=5)
        if response.status_code == 200:
            print("✅ Refresh API working")
        else:
            print(f"❌ Refresh API failed: {response.status_code}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Web UI API error: {e}")
        return False

def test_reset_api():
    """Test reset data API"""
    print("\n🗑️ Testing Reset Data API...")
    
    try:
        response = requests.post('http://localhost:42069/api/reset-data', timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                print("✅ Reset API working")
                return True
            else:
                print(f"❌ Reset API failed: {data.get('message')}")
                return False
        else:
            print(f"❌ Reset API failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Reset API error: {e}")
        return False

def test_command_logging():
    """Test command logging directly"""
    print("\n🧪 Testing Command Logging...")
    
    try:
        import sys
        sys.path.append('.')
        from main import log_command
        
        # Test logging
        log_command(
            command_name="system_test",
            user_id="999999999",
            channel_id="888888888",
            guild_id="777777777",
            success=True
        )
        
        # Verify it was logged
        db_path = "data/commands_global.db"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COUNT(*) FROM command_logs 
            WHERE command_name = 'system_test'
        """)
        count = cursor.fetchone()[0]
        
        conn.close()
        
        if count > 0:
            print("✅ Command logging working")
            return True
        else:
            print("❌ Command not found in database")
            return False
            
    except Exception as e:
        print(f"❌ Command logging error: {e}")
        return False

def main():
    print("🦆 PuddlesBot Complete System Test")
    print("=" * 50)
    
    # Test 1: Database
    db_ok = test_database_exists()
    
    # Test 2: Web UI API
    api_ok = test_web_ui_api()
    
    # Test 3: Command logging
    logging_ok = test_command_logging()
    
    # Test 4: Reset API
    reset_ok = test_reset_api()
    
    print("\n📋 Test Results:")
    print(f"  Database:        {'✅ PASS' if db_ok else '❌ FAIL'}")
    print(f"  Web UI API:      {'✅ PASS' if api_ok else '❌ FAIL'}")
    print(f"  Command Logging: {'✅ PASS' if logging_ok else '❌ FAIL'}")
    print(f"  Reset API:       {'✅ PASS' if reset_ok else '❌ FAIL'}")
    
    all_passed = db_ok and api_ok and logging_ok and reset_ok
    
    if all_passed:
        print("\n🎉 All tests passed!")
        print("✅ The system is working correctly")
        print("\n💡 Next steps:")
        print("   1. Use /synccommands in Discord to sync commands")
        print("   2. Use /testlogging in Discord to test logging")
        print("   3. Check the dashboard at http://localhost:42069")
    else:
        print("\n❌ Some tests failed")
        print("💡 Check the error messages above for details")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
