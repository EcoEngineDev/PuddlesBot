from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

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

    def __repr__(self):
        return f"<Task(name='{self.name}', assigned_to='{self.assigned_to}', due_date='{self.due_date}')>"
    
# Create database engine - use absolute path to avoid any path issues
engine = create_engine('sqlite:///tasks.db', echo=True)

# Drop all tables and recreate them
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

# Create session factory
Session = sessionmaker(bind=engine)

def get_session():
    return Session() 