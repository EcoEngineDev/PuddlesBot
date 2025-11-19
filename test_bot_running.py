#!/usr/bin/env python3
"""
Test script to check if the bot is running and can log commands
"""

import os
import sqlite3
import time
import subprocess
import psutil
from datetime import datetime

def check_bot_process():
    """Check if the bot process is running"""
    print("🔍 Checking if bot process is running...")
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline and isinstance(cmdline, list):
                cmdline_str = ' '.join(cmdline)
                if 'main.py' in cmdline_str and 'python' in cmdline_str:
                    print(f"✅ Bot process found: PID {proc.info['pid']}")
                    print(f"   Command: {cmdline_str}")
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, TypeError):
            continue
    
    print("❌ No bot process found")
    return False

def check_database_after_delay():
    """Check database after a delay to see if new commands appear"""
    print("⏳ Waiting 10 seconds for potential commands...")
    time.sleep(10)
    
    db_path = "data/commands_global.db"
    if not os.path.exists(db_path):
        print("❌ Global database does not exist")
        return False
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get count before
        cursor.execute("SELECT COUNT(*) FROM command_logs")
        count_before = cursor.fetchone()[0]
        
        print(f"📊 Commands in database: {count_before}")
        
        # Get recent commands (last 5 minutes)
        from datetime import timedelta
        five_minutes_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
        cursor.execute("""
            SELECT command_name, guild_id, guild_name, timestamp 
            FROM command_logs 
            WHERE timestamp > ?
            ORDER BY timestamp DESC
        """, (five_minutes_ago,))
        
        recent = cursor.fetchall()
        print(f"📝 Recent commands (last 5 minutes): {len(recent)}")
        
        for cmd, guild_id, guild_name, timestamp in recent:
            server_key = f"{guild_name} ({guild_id})" if guild_name else guild_id
            print(f"   - {cmd} from {server_key} at {timestamp}")
        
        conn.close()
        return len(recent) > 0
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        return False

def test_web_ui_connection():
    """Test if web UI is accessible"""
    print("🌐 Testing web UI connection...")
    
    try:
        import requests
        response = requests.get('http://localhost:42069', timeout=5)
        if response.status_code == 200:
            print("✅ Web UI is accessible")
            return True
        else:
            print(f"⚠️ Web UI returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Web UI not accessible: {e}")
        return False

def main():
    print("🦆 PuddlesBot Running Status Check")
    print("=" * 50)
    
    # Check 1: Bot process
    bot_running = check_bot_process()
    
    # Check 2: Web UI
    webui_accessible = test_web_ui_connection()
    
    # Check 3: Database activity
    recent_activity = check_database_after_delay()
    
    print("\n📋 Status Results:")
    print(f"  Bot Process:      {'✅ RUNNING' if bot_running else '❌ NOT RUNNING'}")
    print(f"  Web UI:           {'✅ ACCESSIBLE' if webui_accessible else '❌ NOT ACCESSIBLE'}")
    print(f"  Recent Activity:  {'✅ YES' if recent_activity else '❌ NO'}")
    
    if not bot_running:
        print("\n💡 The bot is not running. Start it with:")
        print("   python start_dashboard.py -start")
    
    if not webui_accessible:
        print("\n💡 The web UI is not accessible. Make sure it's running on port 42069")
    
    if not recent_activity:
        print("\n💡 No recent command activity detected.")
        print("   Try using some Discord commands like /mytasks, /alltasks, etc.")
    
    return 0

if __name__ == "__main__":
    import sys
    sys.exit(main())
