from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import sqlalchemy
import threading
import shutil
import time
import glob

# Get the absolute path to the data directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')

# Create data and backup directories if they don't exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# Lock for database initialization
_init_lock = threading.Lock()
_initialized_dbs = set()

# Store engines and sessions for each server
_engines = {}
_sessions = {}

def get_db_file_path(server_id):
    """Get the database file path for a specific server"""
    return os.path.join(DATA_DIR, f'server_{server_id}.db')

def create_backup(server_id=None):
    """Create a backup of the database file(s)"""
    if server_id:
        # Backup specific server database
        db_file = get_db_file_path(server_id)
        if os.path.exists(db_file):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(BACKUP_DIR, f'server_{server_id}_backup_{timestamp}.db')
            shutil.copy2(db_file, backup_file)
            
            # Clean up old backups for this server (keep last 5)
            pattern = os.path.join(BACKUP_DIR, f'server_{server_id}_backup_*.db')
            backups = sorted(glob.glob(pattern))
            for old_backup in backups[:-5]:  # Keep only the 5 most recent backups
                os.remove(old_backup)
    else:
        # Backup all server databases
        pattern = os.path.join(DATA_DIR, 'server_*.db')
        server_dbs = glob.glob(pattern)
        for db_file in server_dbs:
            # Extract server ID from filename
            filename = os.path.basename(db_file)
            if filename.startswith('server_') and filename.endswith('.db'):
                server_id = filename[7:-3]  # Remove 'server_' prefix and '.db' suffix
                create_backup(server_id)

def migrate_old_database():
    """Migrate data from old single database to server-specific databases"""
    old_db_file = os.path.join(DATA_DIR, 'tasks.db')
    if not os.path.exists(old_db_file):
        return  # No old database to migrate
    
    print("🔄 Migrating old database to server-specific databases...")
    
    try:
        # Create engine for old database
        old_engine = create_engine(f'sqlite:///{old_db_file}', echo=False)
        OldSession = sessionmaker(bind=old_engine)
        old_session = OldSession()
        
        # Get all unique server IDs from the old database
        try:
            # Check if tables exist
            old_engine.execute(sqlalchemy.text("SELECT name FROM sqlite_master WHERE type='table'"))
            
            server_ids = set()
            
            # Get server IDs from tasks
            try:
                result = old_session.execute(sqlalchemy.text("SELECT DISTINCT server_id FROM tasks"))
                for row in result:
                    if row[0]:
                        server_ids.add(row[0])
            except:
                pass
            
            # Get server IDs from task_creators
            try:
                result = old_session.execute(sqlalchemy.text("SELECT DISTINCT server_id FROM task_creators"))
                for row in result:
                    if row[0]:
                        server_ids.add(row[0])
            except:
                pass
            
            # Get server IDs from user_levels
            try:
                result = old_session.execute(sqlalchemy.text("SELECT DISTINCT guild_id FROM user_levels"))
                for row in result:
                    if row[0]:
                        server_ids.add(row[0])
            except:
                pass
            
            # Get server IDs from level_settings
            try:
                result = old_session.execute(sqlalchemy.text("SELECT DISTINCT guild_id FROM level_settings"))
                for row in result:
                    if row[0]:
                        server_ids.add(row[0])
            except:
                pass
            
            # Get server IDs from level_rewards
            try:
                result = old_session.execute(sqlalchemy.text("SELECT DISTINCT guild_id FROM level_rewards"))
                for row in result:
                    if row[0]:
                        server_ids.add(row[0])
            except:
                pass
            
            print(f"📋 Found data for {len(server_ids)} servers: {list(server_ids)}")
            
            # Migrate data for each server
            for server_id in server_ids:
                print(f"🔄 Migrating data for server {server_id}...")
                
                # Initialize database for this server
                init_db(server_id)
                session = get_session(server_id)
                
                try:
                    # Migrate tasks
                    try:
                        tasks = old_session.execute(
                            sqlalchemy.text("SELECT * FROM tasks WHERE server_id = :server_id"),
                            {"server_id": server_id}
                        ).fetchall()
                        
                        for task_row in tasks:
                            # Insert into new database
                            session.execute(
                                sqlalchemy.text("""
                                    INSERT INTO tasks (id, name, assigned_to, due_date, description, 
                                                     completed, completed_at, created_at, server_id, created_by)
                                    VALUES (:id, :name, :assigned_to, :due_date, :description, 
                                           :completed, :completed_at, :created_at, :server_id, :created_by)
                                """),
                                {
                                    "id": task_row[0],
                                    "name": task_row[1],
                                    "assigned_to": task_row[2],
                                    "due_date": task_row[3],
                                    "description": task_row[4],
                                    "completed": task_row[5],
                                    "completed_at": task_row[6],
                                    "created_at": task_row[7],
                                    "server_id": task_row[8],
                                    "created_by": task_row[9]
                                }
                            )
                        print(f"   ✅ Migrated {len(tasks)} tasks")
                    except Exception as e:
                        print(f"   ⚠️ Error migrating tasks: {e}")
                    
                    # Migrate task creators
                    try:
                        creators = old_session.execute(
                            sqlalchemy.text("SELECT * FROM task_creators WHERE server_id = :server_id"),
                            {"server_id": server_id}
                        ).fetchall()
                        
                        for creator_row in creators:
                            session.execute(
                                sqlalchemy.text("""
                                    INSERT INTO task_creators (id, user_id, server_id, added_by, added_at)
                                    VALUES (:id, :user_id, :server_id, :added_by, :added_at)
                                """),
                                {
                                    "id": creator_row[0],
                                    "user_id": creator_row[1],
                                    "server_id": creator_row[2],
                                    "added_by": creator_row[3],
                                    "added_at": creator_row[4]
                                }
                            )
                        print(f"   ✅ Migrated {len(creators)} task creators")
                    except Exception as e:
                        print(f"   ⚠️ Error migrating task creators: {e}")
                    
                    # Migrate user levels
                    try:
                        levels = old_session.execute(
                            sqlalchemy.text("SELECT * FROM user_levels WHERE guild_id = :guild_id"),
                            {"guild_id": server_id}
                        ).fetchall()
                        
                        for level_row in levels:
                            session.execute(
                                sqlalchemy.text("""
                                    INSERT INTO user_levels (id, user_id, guild_id, text_xp, voice_xp, 
                                                           text_level, voice_level, total_messages, total_voice_time,
                                                           last_text_xp, last_voice_update, voice_join_time)
                                    VALUES (:id, :user_id, :guild_id, :text_xp, :voice_xp, 
                                           :text_level, :voice_level, :total_messages, :total_voice_time,
                                           :last_text_xp, :last_voice_update, :voice_join_time)
                                """),
                                {
                                    "id": level_row[0],
                                    "user_id": level_row[1],
                                    "guild_id": level_row[2],
                                    "text_xp": level_row[3],
                                    "voice_xp": level_row[4],
                                    "text_level": level_row[5],
                                    "voice_level": level_row[6],
                                    "total_messages": level_row[7],
                                    "total_voice_time": level_row[8],
                                    "last_text_xp": level_row[9],
                                    "last_voice_update": level_row[10],
                                    "voice_join_time": level_row[11]
                                }
                            )
                        print(f"   ✅ Migrated {len(levels)} user levels")
                    except Exception as e:
                        print(f"   ⚠️ Error migrating user levels: {e}")
                    
                    # Migrate level settings
                    try:
                        settings = old_session.execute(
                            sqlalchemy.text("SELECT * FROM level_settings WHERE guild_id = :guild_id"),
                            {"guild_id": server_id}
                        ).fetchall()
                        
                        for setting_row in settings:
                            session.execute(
                                sqlalchemy.text("""
                                    INSERT INTO level_settings (id, guild_id, text_xp_enabled, voice_xp_enabled, 
                                                               text_xp_min, text_xp_max, voice_xp_rate, text_cooldown,
                                                               level_up_messages, level_up_channel, no_xp_roles, 
                                                               no_xp_channels, multiplier)
                                    VALUES (:id, :guild_id, :text_xp_enabled, :voice_xp_enabled, 
                                           :text_xp_min, :text_xp_max, :voice_xp_rate, :text_cooldown,
                                           :level_up_messages, :level_up_channel, :no_xp_roles, 
                                           :no_xp_channels, :multiplier)
                                """),
                                {
                                    "id": setting_row[0],
                                    "guild_id": setting_row[1],
                                    "text_xp_enabled": setting_row[2],
                                    "voice_xp_enabled": setting_row[3],
                                    "text_xp_min": setting_row[4],
                                    "text_xp_max": setting_row[5],
                                    "voice_xp_rate": setting_row[6],
                                    "text_cooldown": setting_row[7],
                                    "level_up_messages": setting_row[8],
                                    "level_up_channel": setting_row[9],
                                    "no_xp_roles": setting_row[10],
                                    "no_xp_channels": setting_row[11],
                                    "multiplier": setting_row[12]
                                }
                            )
                        print(f"   ✅ Migrated {len(settings)} level settings")
                    except Exception as e:
                        print(f"   ⚠️ Error migrating level settings: {e}")
                    
                    # Migrate level rewards
                    try:
                        rewards = old_session.execute(
                            sqlalchemy.text("SELECT * FROM level_rewards WHERE guild_id = :guild_id"),
                            {"guild_id": server_id}
                        ).fetchall()
                        
                        for reward_row in rewards:
                            session.execute(
                                sqlalchemy.text("""
                                    INSERT INTO level_rewards (id, guild_id, role_id, text_level, voice_level, 
                                                              remove_previous, dm_user)
                                    VALUES (:id, :guild_id, :role_id, :text_level, :voice_level, 
                                           :remove_previous, :dm_user)
                                """),
                                {
                                    "id": reward_row[0],
                                    "guild_id": reward_row[1],
                                    "role_id": reward_row[2],
                                    "text_level": reward_row[3],
                                    "voice_level": reward_row[4],
                                    "remove_previous": reward_row[5],
                                    "dm_user": reward_row[6]
                                }
                            )
                        print(f"   ✅ Migrated {len(rewards)} level rewards")
                    except Exception as e:
                        print(f"   ⚠️ Error migrating level rewards: {e}")
                    
                    session.commit()
                    print(f"✅ Successfully migrated server {server_id}")
                    
                finally:
                    session.close()
            
            # Create backup of old database before deleting
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = os.path.join(BACKUP_DIR, f'old_tasks_backup_{timestamp}.db')
            shutil.copy2(old_db_file, backup_file)
            
            # Delete old database file
            os.remove(old_db_file)
            print(f"✅ Migration complete! Old database backed up and removed.")
            
        finally:
            old_session.close()
            
    except Exception as e:
        print(f"❌ Error during migration: {e}")
        # Don't delete old database if migration failed
        raise

Base = declarative_base()

class Task(Base):
    __tablename__ = 'tasks'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    assigned_to = Column(String, nullable=False)  # Discord user ID
    due_date = Column(DateTime, nullable=False)
    description = Column(String)
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    server_id = Column(String, nullable=False)  # Discord server ID
    created_by = Column(String, nullable=False, default="0")  # Discord user ID of task creator

    def __repr__(self):
        return f"<Task(name='{self.name}', assigned_to='{self.assigned_to}', due_date='{self.due_date}')>"

class TaskCreator(Base):
    __tablename__ = 'task_creators'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)  # Discord user ID
    server_id = Column(String, nullable=False)  # Discord server ID
    added_by = Column(String, nullable=False)  # Discord user ID who added them
    added_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<TaskCreator(user_id='{self.user_id}', server_id='{self.server_id}')>"

    __table_args__ = (
        sqlalchemy.UniqueConstraint('user_id', 'server_id', name='unique_user_server'),
    )

# Leveling System Tables
class UserLevel(Base):
    __tablename__ = 'user_levels'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    guild_id = Column(String, nullable=False)
    text_xp = Column(Integer, default=0)
    voice_xp = Column(Integer, default=0)
    text_level = Column(Integer, default=0)
    voice_level = Column(Integer, default=0)
    total_messages = Column(Integer, default=0)
    total_voice_time = Column(Integer, default=0)  # in minutes
    last_text_xp = Column(DateTime, nullable=True)
    last_voice_update = Column(DateTime, nullable=True)
    voice_join_time = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<UserLevel(user_id='{self.user_id}', text_level={self.text_level}, voice_level={self.voice_level})>"

class LevelSettings(Base):
    __tablename__ = 'level_settings'
    
    id = Column(Integer, primary_key=True)
    guild_id = Column(String, nullable=False, unique=True)
    text_xp_enabled = Column(Boolean, default=True)
    voice_xp_enabled = Column(Boolean, default=True)
    text_xp_min = Column(Integer, default=15)
    text_xp_max = Column(Integer, default=25)
    voice_xp_rate = Column(Integer, default=10)  # XP per minute
    text_cooldown = Column(Integer, default=60)  # seconds between XP gains
    level_up_messages = Column(Boolean, default=True)
    level_up_channel = Column(String, nullable=True)
    no_xp_roles = Column(String, default="")  # comma-separated role IDs
    no_xp_channels = Column(String, default="")  # comma-separated channel IDs
    multiplier = Column(Float, default=1.0)
    
class LevelRewards(Base):
    __tablename__ = 'level_rewards'
    
    id = Column(Integer, primary_key=True)
    guild_id = Column(String, nullable=False)
    role_id = Column(String, nullable=False)
    text_level = Column(Integer, default=0)
    voice_level = Column(Integer, default=0)
    remove_previous = Column(Boolean, default=False)
    dm_user = Column(Boolean, default=False)

def init_db(server_id):
    """Initialize the database for a specific server"""
    global _initialized_dbs, _engines, _sessions
    
    with _init_lock:
        if server_id in _initialized_dbs:
            return _engines[server_id]
            
        try:
            db_file = get_db_file_path(server_id)
            
            # Create database engine for this server
            engine = create_engine(f'sqlite:///{db_file}', echo=False)
            
            # Create all tables (this only creates tables that don't already exist)
            Base.metadata.create_all(bind=engine)
            
            # Store engine and create session factory
            _engines[server_id] = engine
            _sessions[server_id] = sessionmaker(bind=engine)
            
            if os.path.exists(db_file):
                print(f"Database initialized for server {server_id} at: {db_file}")
                # Check if database has existing data
                Session = _sessions[server_id]
                session = Session()
                try:
                    task_count = session.query(Task).count()
                    creator_count = session.query(TaskCreator).count()
                    user_level_count = session.query(UserLevel).count()
                    level_settings_count = session.query(LevelSettings).count()
                    level_rewards_count = session.query(LevelRewards).count()
                    print(f"Server {server_id} database contains:")
                    print(f"  • {task_count} tasks and {creator_count} task creators")
                    print(f"  • {user_level_count} user levels and {level_settings_count} level settings")
                    print(f"  • {level_rewards_count} level rewards configured")
                except:
                    print(f"Server {server_id} database tables created successfully")
                finally:
                    session.close()
            else:
                print(f"New database created for server {server_id}")
            
            _initialized_dbs.add(server_id)
            return engine
            
        except Exception as e:
            print(f"Error initializing database for server {server_id}: {e}")
            raise

def get_session(server_id):
    """Get a new database session for a specific server"""
    try:
        # Initialize database if not already done
        if server_id not in _initialized_dbs:
            init_db(server_id)
        
        Session = _sessions[server_id]
        session = Session()
        
        # Test the connection
        session.execute(sqlalchemy.text("SELECT 1"))
        return session
    except Exception as e:
        print(f"Error creating session for server {server_id}: {e}")
        # Try to initialize the database if there was an error
        init_db(server_id)
        Session = _sessions[server_id]
        return Session()

def get_all_server_ids():
    """Get all server IDs that have databases"""
    pattern = os.path.join(DATA_DIR, 'server_*.db')
    server_dbs = glob.glob(pattern)
    server_ids = []
    
    for db_file in server_dbs:
        filename = os.path.basename(db_file)
        if filename.startswith('server_') and filename.endswith('.db'):
            server_id = filename[7:-3]  # Remove 'server_' prefix and '.db' suffix
            server_ids.append(server_id)
    
    return server_ids

# Run migration on import
migrate_old_database()