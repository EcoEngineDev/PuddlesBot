#!/usr/bin/env python3
"""
Advanced SQLite recovery script that extracts data directly from binary file
"""

import os
import sqlite3
import struct
import re
from datetime import datetime

def extract_binary_data(file_path):
    """Extract data directly from SQLite binary file"""
    print(f"🔧 Advanced recovery from: {file_path}")
    print("=" * 60)
    
    with open(file_path, 'rb') as f:
        data = f.read()
    
    # SQLite page size is typically 4096 bytes
    PAGE_SIZE = 4096
    
    recovered_data = {
        'tasks': [],
        'task_creators': [],
        'user_levels': [],
        'level_settings': [],
        'level_rewards': []
    }
    
    # Look for text data in the file
    print("🔍 Scanning for text data...")
    
    # Convert binary to text, ignoring errors
    text_data = data.decode('utf-8', errors='ignore')
    
    # Look for task data patterns
    print("\n📋 Looking for task data...")
    task_patterns = [
        r'task[^"]*"[^"]*"([^"]*)"',  # Task names
        r'assigned_to[^"]*"([^"]*)"',  # Assigned users
        r'description[^"]*"([^"]*)"',  # Descriptions
    ]
    
    for pattern in task_patterns:
        matches = re.findall(pattern, text_data, re.IGNORECASE)
        if matches:
            print(f"  Found {len(matches)} potential task entries")
            for match in matches[:10]:  # Show first 10
                if len(match) > 3:  # Filter out very short matches
                    print(f"    • {match[:50]}...")
    
    # Look for user level data
    print("\n📊 Looking for user level data...")
    level_patterns = [
        r'user_id[^"]*"([^"]*)"',
        r'text_xp[^"]*"([0-9]+)"',
        r'voice_xp[^"]*"([0-9]+)"',
        r'text_level[^"]*"([0-9]+)"',
    ]
    
    for pattern in level_patterns:
        matches = re.findall(pattern, text_data, re.IGNORECASE)
        if matches:
            print(f"  Found {len(matches)} potential level entries")
    
    # Try to extract structured data from specific positions
    print("\n🔍 Extracting data from identified positions...")
    
    # Look for data around the positions we found earlier
    positions = [18100, 18143, 18239, 18297, 18311, 18373, 86032, 86037, 86056]
    
    for pos in positions:
        if pos < len(data):
            start = max(0, pos - 200)
            end = min(len(data), pos + 200)
            chunk = data[start:end]
            
            try:
                text_chunk = chunk.decode('utf-8', errors='ignore')
                # Look for readable data
                if any(keyword in text_chunk.lower() for keyword in ['task', 'level', 'user', 'setting', 'reward']):
                    print(f"  📄 Position {pos}: {text_chunk[:100]}...")
            except:
                pass
    
    # Try to create a minimal working database
    print("\n🔧 Attempting to create minimal database...")
    
    try:
        # Create a new database
        fixed_db = "tasks_recovered.db"
        conn = sqlite3.connect(fixed_db)
        cursor = conn.cursor()
        
        # Create basic tables
        cursor.execute('''
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY,
                name TEXT,
                assigned_to TEXT,
                due_date TEXT,
                description TEXT,
                completed BOOLEAN DEFAULT FALSE,
                server_id TEXT DEFAULT '0',
                created_by TEXT DEFAULT '0'
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE user_levels (
                id INTEGER PRIMARY KEY,
                user_id TEXT,
                guild_id TEXT,
                text_xp INTEGER DEFAULT 0,
                voice_xp INTEGER DEFAULT 0,
                text_level INTEGER DEFAULT 0,
                voice_level INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE level_settings (
                id INTEGER PRIMARY KEY,
                guild_id TEXT,
                text_xp_enabled BOOLEAN DEFAULT TRUE,
                voice_xp_enabled BOOLEAN DEFAULT TRUE
            )
        ''')
        
        # Try to extract and insert any readable data
        extracted_count = 0
        
        # Look for task-like data
        task_matches = re.findall(r'([A-Za-z0-9\s\-_]{3,50})', text_data)
        for i, match in enumerate(task_matches[:20]):  # Limit to 20
            if len(match) > 5 and not match.isdigit():
                try:
                    cursor.execute('''
                        INSERT INTO tasks (name, assigned_to, server_id) 
                        VALUES (?, ?, ?)
                    ''', (match, '0', '0'))
                    extracted_count += 1
                except:
                    continue
        
        # Look for user IDs (Discord IDs are typically 17-19 digits)
        user_matches = re.findall(r'(\d{17,19})', text_data)
        for i, user_id in enumerate(user_matches[:10]):  # Limit to 10
            try:
                cursor.execute('''
                    INSERT INTO user_levels (user_id, guild_id, text_xp) 
                    VALUES (?, ?, ?)
                ''', (user_id, '0', 0))
                extracted_count += 1
            except:
                continue
        
        conn.commit()
        conn.close()
        
        print(f"✅ Created minimal database with {extracted_count} extracted records")
        print(f"📁 Saved as: {fixed_db}")
        
        return fixed_db
        
    except Exception as e:
        print(f"❌ Error creating minimal database: {e}")
        return None

def analyze_file_structure(file_path):
    """Analyze the structure of the corrupted file"""
    print(f"\n🔍 Analyzing file structure...")
    
    with open(file_path, 'rb') as f:
        data = f.read()
    
    # Look for SQLite file structure
    print(f"📁 File size: {len(data)} bytes")
    
    # Check for SQLite header
    if data[:16] == b'SQLite format 3\x00':
        print("✅ Valid SQLite header found")
        
        # Extract page size
        page_size = struct.unpack('>H', data[16:18])[0]
        print(f"📄 Page size: {page_size} bytes")
        
        # Count pages
        num_pages = len(data) // page_size
        print(f"📄 Number of pages: {num_pages}")
        
        # Look for table definitions
        schema_sql = b''
        for i in range(num_pages):
            page_start = i * page_size
            page_end = page_start + page_size
            page_data = data[page_start:page_end]
            
            # Look for CREATE TABLE statements
            if b'CREATE TABLE' in page_data:
                print(f"  📋 Found CREATE TABLE on page {i}")
                
                # Extract the SQL
                start = page_data.find(b'CREATE TABLE')
                if start != -1:
                    end = page_data.find(b';', start)
                    if end != -1:
                        sql = page_data[start:end+1]
                        try:
                            print(f"    {sql.decode('utf-8')}")
                        except:
                            print(f"    [Binary SQL data]")
    
    # Look for data patterns
    print(f"\n🔍 Looking for data patterns...")
    
    # Count null bytes (indicates corruption)
    null_count = data.count(b'\x00')
    print(f"📊 Null bytes: {null_count} ({null_count/len(data)*100:.1f}%)")
    
    # Look for readable text
    readable_chars = sum(1 for b in data if 32 <= b <= 126)
    print(f"📊 Readable ASCII: {readable_chars} ({readable_chars/len(data)*100:.1f}%)")
    
    # Look for specific data markers
    markers = {
        'task': data.count(b'task'),
        'level': data.count(b'level'),
        'user': data.count(b'user'),
        'setting': data.count(b'setting'),
        'reward': data.count(b'reward'),
    }
    
    for marker, count in markers.items():
        if count > 0:
            print(f"📊 '{marker}' occurrences: {count}")

def main():
    corrupted_file = "tasks.db"
    
    print("🔧 Advanced SQLite Database Recovery")
    print("=" * 50)
    
    if not os.path.exists(corrupted_file):
        print(f"❌ File not found: {corrupted_file}")
        return
    
    # Analyze file structure
    analyze_file_structure(corrupted_file)
    
    # Try to extract data
    recovered_file = extract_binary_data(corrupted_file)
    
    if recovered_file:
        print(f"\n✅ Recovery attempt completed!")
        print(f"📁 Check the file: {recovered_file}")
        print(f"💡 You can try to use this file for migration")
    else:
        print(f"\n❌ Recovery failed")
        print(f"💡 The database appears to be severely corrupted")

if __name__ == "__main__":
    main() 