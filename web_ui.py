#!/usr/bin/env python3
"""
Flask Web UI for PuddlesBot
A simple web interface for monitoring and controlling the bot.
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for
import os
import sys
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
import psutil
import subprocess
import signal
from collections import defaultdict, Counter

app = Flask(__name__)

# Bot process tracking
bot_process = None
bot_thread = None
bot_running = False

# Statistics cache
stats_cache = {
    'last_updated': None,
    'server_commands': {},
    'command_usage_24h': {},
    'command_usage_month': {},
    'total_servers': 0,
    'total_users': 0,
    'uptime': None
}

def get_database_stats():
    """Get command statistics from the global database"""
    global stats_cache
    
    try:
        # Check if global command database exists
        db_path = 'data/commands_global.db'
        if not os.path.exists(db_path):
            print("No global command database found")
            return
            
        server_commands = defaultdict(int)
        command_usage_24h = Counter()
        command_usage_month = Counter()
        
        # Time boundaries
        now = datetime.now()
        day_ago = now - timedelta(days=1)
        month_ago = now - timedelta(days=30)
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Check if command_logs table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='command_logs'
            """)
            
            if cursor.fetchone():
                # Get total commands per server
                cursor.execute("""
                    SELECT guild_id, guild_name, COUNT(*) 
                    FROM command_logs 
                    GROUP BY guild_id, guild_name
                """)
                
                for guild_id, guild_name, count in cursor.fetchall():
                    server_key = f"{guild_name} ({guild_id})" if guild_name else guild_id
                    server_commands[server_key] = count
                
                # Get commands from last 24 hours
                cursor.execute("""
                    SELECT command_name, COUNT(*) FROM command_logs 
                    WHERE timestamp > ? 
                    GROUP BY command_name
                """, (day_ago.isoformat(),))
                
                for cmd, count in cursor.fetchall():
                    command_usage_24h[cmd] += count
                
                # Get commands from last month
                cursor.execute("""
                    SELECT command_name, COUNT(*) FROM command_logs 
                    WHERE timestamp > ? 
                    GROUP BY command_name
                """, (month_ago.isoformat(),))
                
                for cmd, count in cursor.fetchall():
                    command_usage_month[cmd] += count
            
            conn.close()
            
        except Exception as e:
            print(f"Error reading global command database: {e}")
            return
        
        # Get server count from guild cache if available
        total_servers = 0
        total_users = 0
        try:
            if os.path.exists('guild_cache.json'):
                with open('guild_cache.json', 'r') as f:
                    guild_data = json.load(f)
                    total_servers = len(guild_data.get('guilds', []))
                    total_users = guild_data.get('total_users', 0)
        except Exception as e:
            print(f"Error reading guild cache: {e}")
        
        # Update cache
        stats_cache.update({
            'last_updated': datetime.now(),
            'server_commands': dict(server_commands),
            'command_usage_24h': dict(command_usage_24h),
            'command_usage_month': dict(command_usage_month),
            'total_servers': total_servers,
            'total_users': total_users
        })
        
    except Exception as e:
        print(f"Error getting database stats: {e}")

def get_bot_status():
    """Get current bot status"""
    global bot_process, bot_running
    
    # Check if main.py process is running
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info['cmdline']
            if cmdline:
                # Check if this is a Python process running main.py
                cmdline_str = ' '.join(cmdline).lower()
                if ('python' in cmdline_str or 'python3' in cmdline_str) and 'main.py' in cmdline_str:
                    bot_running = True
                    bot_process = proc.info['pid']
                    return {
                        'running': True,
                        'pid': proc.info['pid'],
                        'memory_mb': round(proc.memory_info().rss / 1024 / 1024, 1),
                        'cpu_percent': proc.cpu_percent(),
                        'uptime': time.time() - proc.create_time()
                    }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    bot_running = False
    bot_process = None
    return {'running': False}


# Background thread to update stats
def stats_updater():
    """Background thread to update statistics"""
    last_ping_time = 0
    while True:
        # Check for ping file
        ping_file = 'data/dashboard_ping.txt'
        if os.path.exists(ping_file):
            try:
                with open(ping_file, 'r') as f:
                    ping_time = float(f.read().strip())
                if ping_time > last_ping_time:
                    last_ping_time = ping_time
                    print(f"📊 Command detected, updating dashboard...")
                    get_database_stats()
            except Exception as e:
                print(f"Error reading ping file: {e}")
        
        get_database_stats()
        time.sleep(5)  # Check every 5 seconds for faster updates

# Start stats updater thread
stats_thread = threading.Thread(target=stats_updater, daemon=True)
stats_thread.start()

@app.route('/')
def index():
    """Main dashboard"""
    bot_status = get_bot_status()
    
    # Get server names from guilds if possible
    server_names = {}
    try:
        # Try to read guild info from a cache file if it exists
        if os.path.exists('guild_cache.json'):
            with open('guild_cache.json', 'r') as f:
                guild_data = json.load(f)
                server_names = {str(g['id']): g['name'] for g in guild_data.get('guilds', [])}
    except:
        pass
    
    return render_template('dashboard.html', 
                         bot_status=bot_status,
                         stats=stats_cache,
                         server_names=server_names)

@app.route('/api/status')
def api_status():
    """API endpoint for bot status"""
    return jsonify(get_bot_status())

@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics"""
    return jsonify(stats_cache)

@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    """API endpoint to refresh statistics"""
    get_database_stats()
    return jsonify({'success': True, 'stats': stats_cache})

@app.route('/api/reset-data', methods=['POST'])
def api_reset_data():
    """Reset all command logging data"""
    try:
        # Clear the global command database
        db_path = 'data/commands_global.db'
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM command_logs")
            conn.commit()
            conn.close()
            print("🗑️ Command logging data reset")
        
        # Clear the stats cache
        global stats_cache
        stats_cache = {
            'last_updated': None,
            'server_commands': {},
            'command_usage_24h': {},
            'command_usage_month': {},
            'total_servers': 0,
            'total_users': 0,
            'uptime': None
        }
        
        # Refresh stats
        get_database_stats()
        
        return jsonify({'status': 'success', 'message': 'All command data has been reset'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    print("🌐 Starting PuddlesBot Web UI...")
    print("📊 Dashboard will be available at: http://localhost:42069")
    print("🔄 Statistics will update automatically every 30 seconds")
    print("⚡ Use Ctrl+C to stop the web server")
    
    app.run(host='0.0.0.0', port=42069, debug=True, use_reloader=False)
