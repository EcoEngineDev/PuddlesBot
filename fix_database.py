#!/usr/bin/env python3
"""
Quick database fix to add missing columns
"""

import sqlite3
import os

def fix_database():
    """Add missing columns to existing database"""
    
    db_path = os.path.join('data', 'tasks.db')
    
    if not os.path.exists(db_path):
        print("No database file found.")
        return
    
    print(f"Fixing database: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Add missing columns to tickets table
        try:
            cursor.execute("ALTER TABLE tickets ADD COLUMN questions_answers TEXT")
            print("✅ Added questions_answers column to tickets table")
        except sqlite3.OperationalError:
            print("ℹ️  questions_answers column already exists")
        
        # Add missing columns to message_buttons table
        try:
            cursor.execute("ALTER TABLE message_buttons ADD COLUMN ticket_questions TEXT")
            print("✅ Added ticket_questions column to message_buttons table")
        except sqlite3.OperationalError:
            print("ℹ️  ticket_questions column already exists")
        
        try:
            cursor.execute("ALTER TABLE message_buttons ADD COLUMN ticket_visible_roles TEXT")
            print("✅ Added ticket_visible_roles column to message_buttons table")
        except sqlite3.OperationalError:
            print("ℹ️  ticket_visible_roles column already exists")
        
        # Create intmsg_creators table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS intmsg_creators (
                id INTEGER PRIMARY KEY,
                user_id TEXT NOT NULL,
                server_id TEXT NOT NULL,
                added_by TEXT NOT NULL,
                added_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ Created/verified intmsg_creators table")
        
        conn.commit()
        conn.close()
        
        print("🎉 Database fixed successfully!")
        
    except Exception as e:
        print(f"❌ Fix failed: {e}")

if __name__ == "__main__":
    fix_database() 