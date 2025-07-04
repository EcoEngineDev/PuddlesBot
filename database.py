from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
import sqlalchemy
import threading
import shutil
import time

# Get the absolute path to the data directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
BACKUP_DIR = os.path.join(DATA_DIR, 'backups')
SERVERS_DIR = os.path.join(DATA_DIR, 'servers')

# Create necessary directories
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(SERVERS_DIR, exist_ok=True)

# Lock for database initialization
_init_lock = threading.Lock()
_initialized_dbs = set()
_engines = {}
_sessions = {}

def create_backup(server_id: str):
    """Create a backup of a server's database file"""
    db_file = os.path.join(SERVERS_DIR, f'{server_id}.db')
    if os.path.exists(db_file):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(BACKUP_DIR, f'{server_id}_backup_{timestamp}.db')
        shutil.copy2(db_file, backup_file)
        
        # Clean up old backups (keep last 5)
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith(f'{server_id}_backup_')])
        for old_backup in backups[:-5]:  # Keep only the 5 most recent backups
            os.remove(os.path.join(BACKUP_DIR, old_backup))

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

def init_db(server_id: str):
    """Initialize a server-specific database and create all tables"""
    global _initialized_dbs, _engines, _sessions
    
    with _init_lock:
        if server_id in _initialized_dbs:
            return _engines[server_id]
            
        try:
            # Create database engine for this server
            db_file = os.path.join(SERVERS_DIR, f'{server_id}.db')
            engine = create_engine(f'sqlite:///{db_file}', echo=False)
            _engines[server_id] = engine
            
            # Create all tables
            Base.metadata.create_all(bind=engine)
            
            if os.path.exists(db_file):
                print(f"Database initialized successfully for server {server_id} at: {db_file}")
                # Check if database has existing data
                Session = sessionmaker(bind=engine)
                session = Session()
                try:
                    task_count = session.query(Task).count()
                    creator_count = session.query(TaskCreator).count()
                    user_level_count = session.query(UserLevel).count()
                    level_settings_count = session.query(LevelSettings).count()
                    level_rewards_count = session.query(LevelRewards).count()
                    print(f"Database for server {server_id} contains:")
                    print(f"  • {task_count} tasks and {creator_count} task creators")
                    print(f"  • {user_level_count} user levels across {level_settings_count} servers")
                    print(f"  • {level_rewards_count} level rewards configured")
                except:
                    print(f"Database tables created successfully for server {server_id}")
                finally:
                    session.close()
            else:
                print(f"New database created successfully for server {server_id}")
            
            _initialized_dbs.add(server_id)
            _sessions[server_id] = sessionmaker(bind=engine)
            return engine
            
        except Exception as e:
            print(f"Error initializing database for server {server_id}: {e}")
            raise

def get_session(server_id: str = None):
    """Get a new database session for a specific server"""
    try:
        if server_id is None:
            raise ValueError("server_id is required")
            
        # Initialize database if needed
        if server_id not in _initialized_dbs:
            init_db(server_id)
            
        session = _sessions[server_id]()
        # Test the connection
        session.execute(sqlalchemy.text("SELECT 1"))
        return session
    except Exception as e:
        print(f"Error creating session for server {server_id}: {e}")
        # Try to initialize the database if there was an error
        init_db(server_id)
        return _sessions[server_id]()

async def migrate_legacy_data():
    """Migrate data from the old single database to server-specific databases"""
    old_db_file = os.path.join(DATA_DIR, 'tasks.db')
    if not os.path.exists(old_db_file):
        print("No legacy database found, skipping migration")
        return
        
    print("Starting legacy data migration...")
    try:
        # Connect to old database
        old_engine = create_engine(f'sqlite:///{old_db_file}')
        Base.metadata.create_all(bind=old_engine)
        OldSession = sessionmaker(bind=old_engine)
        old_session = OldSession()
        
        # Get all unique server IDs from all tables
        server_ids = set()
        server_ids.update([str(r[0]) for r in old_session.query(Task.server_id).distinct()])
        server_ids.update([str(r[0]) for r in old_session.query(TaskCreator.server_id).distinct()])
        server_ids.update([str(r[0]) for r in old_session.query(UserLevel.guild_id).distinct()])
        server_ids.update([str(r[0]) for r in old_session.query(LevelSettings.guild_id).distinct()])
        server_ids.update([str(r[0]) for r in old_session.query(LevelRewards.guild_id).distinct()])
        
        # Migrate data for each server
        for server_id in server_ids:
            print(f"Migrating data for server {server_id}...")
            new_session = get_session(server_id)
            
            try:
                # Migrate tasks
                tasks = old_session.query(Task).filter_by(server_id=server_id).all()
                for task in tasks:
                    new_task = Task(
                        name=task.name,
                        assigned_to=task.assigned_to,
                        due_date=task.due_date,
                        description=task.description,
                        completed=task.completed,
                        completed_at=task.completed_at,
                        created_at=task.created_at,
                        server_id=task.server_id,
                        created_by=task.created_by
                    )
                    new_session.add(new_task)
                
                # Migrate task creators
                creators = old_session.query(TaskCreator).filter_by(server_id=server_id).all()
                for creator in creators:
                    new_creator = TaskCreator(
                        user_id=creator.user_id,
                        server_id=creator.server_id,
                        added_by=creator.added_by,
                        added_at=creator.added_at
                    )
                    new_session.add(new_creator)
                
                # Migrate user levels
                levels = old_session.query(UserLevel).filter_by(guild_id=server_id).all()
                for level in levels:
                    new_level = UserLevel(
                        user_id=level.user_id,
                        guild_id=level.guild_id,
                        text_xp=level.text_xp,
                        voice_xp=level.voice_xp,
                        text_level=level.text_level,
                        voice_level=level.voice_level,
                        total_messages=level.total_messages,
                        total_voice_time=level.total_voice_time,
                        last_text_xp=level.last_text_xp,
                        last_voice_update=level.last_voice_update,
                        voice_join_time=level.voice_join_time
                    )
                    new_session.add(new_level)
                
                # Migrate level settings
                settings = old_session.query(LevelSettings).filter_by(guild_id=server_id).first()
                if settings:
                    new_settings = LevelSettings(
                        guild_id=settings.guild_id,
                        text_xp_enabled=settings.text_xp_enabled,
                        voice_xp_enabled=settings.voice_xp_enabled,
                        text_xp_min=settings.text_xp_min,
                        text_xp_max=settings.text_xp_max,
                        voice_xp_rate=settings.voice_xp_rate,
                        text_cooldown=settings.text_cooldown,
                        level_up_messages=settings.level_up_messages,
                        level_up_channel=settings.level_up_channel,
                        no_xp_roles=settings.no_xp_roles,
                        no_xp_channels=settings.no_xp_channels,
                        multiplier=settings.multiplier
                    )
                    new_session.add(new_settings)
                
                # Migrate level rewards
                rewards = old_session.query(LevelRewards).filter_by(guild_id=server_id).all()
                for reward in rewards:
                    new_reward = LevelRewards(
                        guild_id=reward.guild_id,
                        role_id=reward.role_id,
                        text_level=reward.text_level,
                        voice_level=reward.voice_level,
                        remove_previous=reward.remove_previous,
                        dm_user=reward.dm_user
                    )
                    new_session.add(new_reward)
                
                new_session.commit()
                print(f"✅ Successfully migrated data for server {server_id}")
                
            except Exception as e:
                print(f"❌ Error migrating data for server {server_id}: {e}")
                new_session.rollback()
            finally:
                new_session.close()
        
        # Backup and rename old database
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(BACKUP_DIR, f'legacy_db_backup_{timestamp}.db')
        shutil.copy2(old_db_file, backup_file)
        os.rename(old_db_file, old_db_file + '.migrated')
        print("✅ Legacy database backed up and renamed")
        
    except Exception as e:
        print(f"❌ Error during migration: {e}")
    finally:
        old_session.close() 