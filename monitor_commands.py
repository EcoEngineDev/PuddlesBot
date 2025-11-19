#!/usr/bin/env python3
"""
Monitor command logging in real-time
"""

import os
import sqlite3
import time
from datetime import datetime

def monitor_commands():
    """Monitor command logging in real-time"""
    print("🔍 Monitoring Command Logging...")
    print("Press Ctrl+C to stop")
    print("=" * 50)
    
    db_path = "data/commands_global.db"
    last_count = 0
    
    try:
        while True:
            if os.path.exists(db_path):
                try:
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    # Get current count
                    cursor.execute("SELECT COUNT(*) FROM command_logs")
                    current_count = cursor.fetchone()[0]
                    
                    if current_count > last_count:
                        # New commands detected
                        new_commands = current_count - last_count
                        print(f"\n🆕 {new_commands} new command(s) detected! Total: {current_count}")
                        
                        # Get the latest commands
                        cursor.execute("""
                            SELECT command_name, guild_id, guild_name, timestamp 
                            FROM command_logs 
                            ORDER BY timestamp DESC 
                            LIMIT 5
                        """)
                        
                        recent = cursor.fetchall()
                        print("📝 Latest commands:")
                        for cmd, guild_id, guild_name, timestamp in recent:
                            server_key = f"{guild_name} ({guild_id})" if guild_name else guild_id
                            time_str = datetime.fromisoformat(timestamp).strftime("%H:%M:%S")
                            print(f"   - {cmd} from {server_key} at {time_str}")
                        
                        last_count = current_count
                    else:
                        # No new commands
                        print(f"⏳ Monitoring... (Total: {current_count})", end="\r")
                    
                    conn.close()
                    
                except Exception as e:
                    print(f"\n❌ Error reading database: {e}")
            else:
                print("⏳ Waiting for database to be created...", end="\r")
            
            time.sleep(2)  # Check every 2 seconds
            
    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped")

if __name__ == "__main__":
    monitor_commands()
