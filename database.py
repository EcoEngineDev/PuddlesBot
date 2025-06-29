from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey
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
DB_FILE = os.path.join(DATA_DIR, 'tasks.db')

# Create data and backup directories if they don't exist
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

# Lock for database initialization
_init_lock = threading.Lock()
_is_initialized = False

def create_backup():
    """Create a backup of the database file"""
    if os.path.exists(DB_FILE):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = os.path.join(BACKUP_DIR, f'tasks_backup_{timestamp}.db')
        shutil.copy2(DB_FILE, backup_file)
        
        # Clean up old backups (keep last 5)
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('tasks_backup_')])
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

def init_db():
    """Initialize the database and create all tables"""
    global _is_initialized
    
    with _init_lock:
        if _is_initialized:
            return
            
        try:
            # Create database engine (this will create the database file if it doesn't exist)
            engine = create_engine(f'sqlite:///{DB_FILE}', echo=False)
            
            # Create all tables (this only creates tables that don't already exist)
            Base.metadata.create_all(bind=engine)
            
            if os.path.exists(DB_FILE):
                print(f"Database initialized successfully at: {DB_FILE}")
                # Check if database has existing data
                Session = sessionmaker(bind=engine)
                session = Session()
                try:
                    task_count = session.query(Task).count()
                    creator_count = session.query(TaskCreator).count()
                    print(f"Database contains {task_count} tasks and {creator_count} task creators")
                except:
                    print("Database tables created successfully")
                finally:
                    session.close()
            else:
                print("New database created successfully")
            
            _is_initialized = True
            return engine
            
        except Exception as e:
            print(f"Error initializing database: {e}")
            raise

# Create engine and initialize database
engine = init_db()

# Create session factory
Session = sessionmaker(bind=engine)

def get_session():
    """Get a new database session"""
    try:
        session = Session()
        # Test the connection
        session.execute(sqlalchemy.text("SELECT 1"))
        return session
    except Exception as e:
        print(f"Error creating session: {e}")
        # Try to initialize the database if there was an error
        init_db()
        return Session() 