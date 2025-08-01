from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Float, Table, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
import sqlalchemy
import threading
import shutil
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Get the absolute path to the data directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')

# Create data and backup directories if they don't exist
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(BACKUP_DIR, exist_ok=True)
    print(f"[DEBUG] Database directories created: {DATA_DIR}")
except Exception as e:
    print(f"[ERROR] Failed to create database directories: {str(e)}")
    # Try to continue anyway

# Lock for database initialization
_init_lock = threading.Lock()
_engines = {}  # server_id -> engine
_sessions = {}  # server_id -> sessionmaker

# Startup protection
_startup_complete = False

def mark_startup_complete():
    """Mark that bot startup is complete - used to prevent database hangs during startup"""
    global _startup_complete
    _startup_complete = True
    print("[DEBUG] Database startup protection disabled - bot is fully loaded")

def is_startup_complete():
    """Check if bot startup is complete"""
    return _startup_complete

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
    
    # Snipe tracking fields
    is_sniped = Column(Boolean, default=False)  # Whether this task was completed via snipe
    sniped_from = Column(String, nullable=True)  # Original assignee user ID (if sniped)
    sniped_by = Column(String, nullable=True)  # User ID who sniped the task
    sniped_at = Column(DateTime, nullable=True)  # When the snipe was approved

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

class TaskReminder(Base):
    __tablename__ = 'task_reminders'
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, nullable=False)
    user_id = Column(String, nullable=False)  # Discord user ID
    reminder_type = Column(String, nullable=False)  # '7d', '3d', '1d'
    sent_at = Column(DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f"<TaskReminder(task_id={self.task_id}, user_id={self.user_id}, type={self.reminder_type})>"

class TimezoneSettings(Base):
    __tablename__ = 'timezone_settings'
    id = Column(Integer, primary_key=True)
    server_id = Column(String, nullable=False, unique=True)
    timezone = Column(String, nullable=False, default='UTC')  # IANA timezone name
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<TimezoneSettings(server_id='{self.server_id}', timezone='{self.timezone}')>"

class SnipeRequest(Base):
    __tablename__ = 'snipe_requests'
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, nullable=False)
    original_assignee = Column(String, nullable=False)  # Discord user ID of original assignee
    sniper_id = Column(String, nullable=False)  # Discord user ID of person claiming the task
    server_id = Column(String, nullable=False)  # Discord server ID
    status = Column(String, nullable=False, default='pending')  # 'pending', 'approved', 'denied'
    requested_at = Column(DateTime, default=datetime.utcnow)
    handled_by = Column(String, nullable=True)  # Discord user ID of admin who handled it
    handled_at = Column(DateTime, nullable=True)
    
    def __repr__(self):
        return f"<SnipeRequest(task_id={self.task_id}, sniper_id='{self.sniper_id}', status='{self.status}')>"

class SnipeSettings(Base):
    __tablename__ = 'snipe_settings'
    id = Column(Integer, primary_key=True)
    server_id = Column(String, nullable=False, unique=True)
    snipe_channel_id = Column(String, nullable=False)  # Discord channel ID for snipe requests
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f"<SnipeSettings(server_id='{self.server_id}', channel_id='{self.snipe_channel_id}')>"

class MultidimensionalOptIn(Base):
    """Stores server opt-in status for multidimensional travel feature"""
    __tablename__ = 'multidimensional_optin'
    
    server_id = Column(String, primary_key=True)
    opted_in = Column(Boolean, default=False)
    opt_in_time = Column(DateTime, nullable=True)
    opt_in_by = Column(String, nullable=True)  # Discord ID of admin who opted in
    
    def __repr__(self):
        return f"<MultidimensionalOptIn(server_id='{self.server_id}', opted_in={self.opted_in})>"

def get_db_path(server_id):
    return os.path.join(DATA_DIR, f"{server_id}.db")

def _create_tables_sync(engine, server_id):
    """Synchronous table creation function"""
    try:
        print(f"[DEBUG] Creating tables for server {server_id}")
        Base.metadata.create_all(bind=engine)
        print(f"[DEBUG] Tables created successfully for server {server_id}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to create tables for server {server_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

def migrate_database(engine, server_id):
    """Handle database migrations for schema changes"""
    try:
        print(f"[DEBUG] Starting database migration check for server {server_id}")
        
        # Use a shorter timeout for migration operations
        with engine.connect() as conn:
            # Set a timeout for operations
            conn.execute(sqlalchemy.text("PRAGMA busy_timeout = 3000"))  # 3 second timeout
            
            try:
                # Check if new snipe columns exist in tasks table
                print(f"[DEBUG] Checking for snipe columns in server {server_id}")
                result = conn.execute(sqlalchemy.text("SELECT is_sniped, sniped_from, sniped_by, sniped_at FROM tasks LIMIT 1"))
                print(f"[DEBUG] Snipe columns already exist for server {server_id}")
            except Exception as e:
                error_str = str(e).lower()
                if "no column named" in error_str or "no such column" in error_str:
                    print(f"[INFO] Adding missing snipe columns to tasks table for server {server_id}")
                    try:
                        # Add columns one by one with individual error handling
                        try:
                            conn.execute(sqlalchemy.text("ALTER TABLE tasks ADD COLUMN is_sniped BOOLEAN DEFAULT 0"))
                            print(f"[DEBUG] Added is_sniped column for server {server_id}")
                        except Exception as e1:
                            if "duplicate column name" not in str(e1).lower():
                                print(f"[WARNING] Could not add is_sniped column: {str(e1)}")
                        
                        try:
                            conn.execute(sqlalchemy.text("ALTER TABLE tasks ADD COLUMN sniped_from VARCHAR"))
                            print(f"[DEBUG] Added sniped_from column for server {server_id}")
                        except Exception as e2:
                            if "duplicate column name" not in str(e2).lower():
                                print(f"[WARNING] Could not add sniped_from column: {str(e2)}")
                        
                        try:
                            conn.execute(sqlalchemy.text("ALTER TABLE tasks ADD COLUMN sniped_by VARCHAR"))
                            print(f"[DEBUG] Added sniped_by column for server {server_id}")
                        except Exception as e3:
                            if "duplicate column name" not in str(e3).lower():
                                print(f"[WARNING] Could not add sniped_by column: {str(e3)}")
                        
                        try:
                            conn.execute(sqlalchemy.text("ALTER TABLE tasks ADD COLUMN sniped_at DATETIME"))
                            print(f"[DEBUG] Added sniped_at column for server {server_id}")
                        except Exception as e4:
                            if "duplicate column name" not in str(e4).lower():
                                print(f"[WARNING] Could not add sniped_at column: {str(e4)}")
                        
                        conn.commit()
                        print(f"[DEBUG] Successfully completed snipe column migration for server {server_id}")
                    except Exception as alter_error:
                        print(f"[WARNING] Migration error for server {server_id}: {str(alter_error)}")
                        # Don't fail completely, just continue
                else:
                    print(f"[WARNING] Database check error for server {server_id}: {str(e)}")
            
            # Quick check for single-to-multi assignee migration (non-blocking)
            try:
                print(f"[DEBUG] Checking assignee format for server {server_id}")
                result = conn.execute(sqlalchemy.text(
                    "SELECT COUNT(*) as count FROM tasks WHERE assigned_to NOT LIKE '%,%' AND assigned_to IS NOT NULL AND assigned_to != '' LIMIT 1"
                ))
                row = result.fetchone()
                if row and row[0] > 0:
                    print(f"[INFO] Found single-assignee tasks for server {server_id} - they're compatible with multi-assignee system")
                else:
                    print(f"[DEBUG] All tasks already in multi-assignee format for server {server_id}")
            except Exception as migration_error:
                print(f"[WARNING] Could not check assignee migration for server {server_id}: {str(migration_error)}")
                # Don't block startup for this
            
        print(f"[DEBUG] Database migration completed for server {server_id}")
                
    except Exception as e:
        print(f"[ERROR] Migration failed for server {server_id}: {str(e)}")
        # Don't fail completely - let the app continue with potentially missing columns
        # The app should handle missing columns gracefully

def get_engine(server_id):
    """Get or create the SQLAlchemy engine for a given server_id."""
    with _init_lock:
        if server_id in _engines:
            return _engines[server_id]
        
        print(f"[DEBUG] Creating database engine for server {server_id}")
        db_path = get_db_path(server_id)
        
        try:
            # Create engine with aggressive timeout settings to prevent hangs
            engine = create_engine(
                f'sqlite:///{db_path}', 
                echo=False, 
                connect_args={
                    "check_same_thread": False,
                    "timeout": 3  # Very short timeout to prevent hangs
                },
                pool_timeout=3,  # Short pool timeout
                pool_recycle=1800,  # Recycle connections every 30 minutes
                pool_pre_ping=True  # Verify connections before use
            )
            
            # Store engine first, then create tables
            _engines[server_id] = engine
            print(f"[DEBUG] Engine created and stored for server {server_id}")
            
            # Try to create tables with timeout protection
            try:
                print(f"[DEBUG] Creating tables for server {server_id}")
                # Use a connection with timeout to prevent hangs
                with engine.connect() as conn:
                    conn.execute(sqlalchemy.text("PRAGMA busy_timeout = 2000"))  # 2 second timeout
                    Base.metadata.create_all(bind=engine)
                    print(f"[DEBUG] Tables created successfully for server {server_id}")
                
                # Run database migrations with timeout protection
                print(f"[DEBUG] Running migrations for server {server_id}")
                migrate_database(engine, server_id)
                print(f"[DEBUG] Migrations completed for server {server_id}")
                
            except Exception as table_error:
                print(f"[WARNING] Could not complete table creation/migration for server {server_id}: {str(table_error)}")
                print("[INFO] Tables will be created on first database access if needed")
                # Don't fail completely - the engine is still usable
            
            print(f"[DEBUG] Database engine ready for server {server_id}")
            return engine
            
        except Exception as e:
            print(f"[ERROR] Failed to create database engine for server {server_id}: {str(e)}")
            import traceback
            traceback.print_exc()
            # Create a minimal engine as fallback
            try:
                print(f"[DEBUG] Creating fallback engine for server {server_id}")
                engine = create_engine(
                    f'sqlite:///{db_path}', 
                    echo=False,
                    connect_args={"check_same_thread": False, "timeout": 2}
                )
                _engines[server_id] = engine
                print(f"[DEBUG] Fallback engine created for server {server_id}")
                return engine
            except Exception as fallback_error:
                print(f"[CRITICAL] Complete database failure for server {server_id}: {str(fallback_error)}")
                raise

def get_session(server_id):
    """Get a database session for the given server_id."""
    try:
        print(f"[DEBUG] Getting database session for server {server_id}")
        
        # During startup, use minimal database operations to prevent hangs
        if not _startup_complete:
            print(f"[DEBUG] Startup mode - using minimal database operations for server {server_id}")
        
        engine = get_engine(server_id)
        
        if server_id not in _sessions:
            print(f"[DEBUG] Creating new session maker for server {server_id}")
            _sessions[server_id] = sessionmaker(bind=engine)
        
        Session = _sessions[server_id]
        session = Session()
        
        # Test the connection with a quick timeout
        print(f"[DEBUG] Testing database connection for server {server_id}")
        try:
            # Use a very quick test with timeout
            session.execute(sqlalchemy.text("SELECT 1"))
            print(f"[DEBUG] Database connection successful for server {server_id}")
        except Exception as conn_error:
            print(f"[WARNING] Database connection test failed for server {server_id}: {str(conn_error)}")
            
            # Skip complex operations during startup to prevent hangs
            if not _startup_complete:
                print(f"[INFO] Skipping table creation during startup for server {server_id}")
                # Just return the session - tables will be created on first real use
                return session
            
            # Try to create tables if they don't exist (only after startup)
            try:
                print(f"[DEBUG] Attempting to create tables for server {server_id}")
                with engine.connect() as conn:
                    conn.execute(sqlalchemy.text("PRAGMA busy_timeout = 2000"))  # 2 second timeout
                    Base.metadata.create_all(bind=engine)
                
                # Run migrations to ensure all columns exist
                migrate_database(engine, server_id)
                
                session.execute(sqlalchemy.text("SELECT 1"))  # Test again
                print(f"[DEBUG] Tables created and connection restored for server {server_id}")
            except Exception as table_error:
                print(f"[ERROR] Failed to create tables for server {server_id}: {str(table_error)}")
                # Still return the session, it might work for basic operations
        
        print(f"[DEBUG] Database session ready for server {server_id}")
        return session
        
    except Exception as e:
        print(f"[ERROR] Failed to create database session for server {server_id}: {str(e)}")
        import traceback  
        traceback.print_exc()
        
        # Last resort: try to create a completely fresh session
        try:
            print(f"[DEBUG] Creating emergency session for server {server_id}")
            db_path = get_db_path(server_id)
            emergency_engine = create_engine(
                f'sqlite:///{db_path}', 
                echo=False,
                connect_args={"check_same_thread": False, "timeout": 1}
            )
            EmergencySession = sessionmaker(bind=emergency_engine)
            emergency_session = EmergencySession()
            print(f"[DEBUG] Emergency session created for server {server_id}")
            return emergency_session
        except Exception as emergency_error:
            print(f"[CRITICAL] Could not create any database session for server {server_id}: {str(emergency_error)}")
            raise

def create_backup(server_id):
    """Create a backup of the database file for a server"""
    db_path = get_db_path(server_id)
    if os.path.exists(db_path):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(BACKUP_DIR, f'{server_id}_backup_{timestamp}.db')
        shutil.copy2(db_path, backup_file)
        # Clean up old backups (keep last 5 per server)
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith(f'{server_id}_backup_')])
        for old_backup in backups[:-5]:
            os.remove(os.path.join(BACKUP_DIR, old_backup)) 