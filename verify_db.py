#!/usr/bin/env python3
"""
Simple script to verify the created database
"""

import sqlite3
import os

def verify_database():
    db_file = "data/server_1373713234997153891.db"
    
    if not os.path.exists(db_file):
        print(f"❌ Database file not found: {db_file}")
        return
    
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print(f"✅ Database is valid!")
        print(f"📋 Found {len(tables)} tables:")
        
        for table in tables:
            table_name = table[0]
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"  • {table_name}: {count} records")
        
        # Show some sample data
        print(f"\n📄 Sample data:")
        
        # Check tasks
        cursor.execute("SELECT id, name FROM tasks LIMIT 3")
        tasks = cursor.fetchall()
        if tasks:
            print(f"  Tasks:")
            for task in tasks:
                print(f"    • {task[0]}: {task[1][:50]}...")
        
        # Check user levels
        cursor.execute("SELECT user_id, text_level, voice_level FROM user_levels LIMIT 3")
        levels = cursor.fetchall()
        if levels:
            print(f"  User Levels:")
            for level in levels:
                print(f"    • User {level[0]}: Text Lv{level[1]}, Voice Lv{level[2]}")
        
        conn.close()
        print(f"\n🎉 Database is ready for your bot!")
        
    except Exception as e:
        print(f"❌ Error verifying database: {e}")

if __name__ == "__main__":
    verify_database() 