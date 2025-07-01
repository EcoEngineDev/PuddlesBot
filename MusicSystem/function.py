# Minimal Vocard function.py to prevent import errors
import json
import os
import logging

# Create a basic logger
logger = logging.getLogger('vocard')

class Settings:
    """Basic settings class for Vocard compatibility"""
    def __init__(self, data):
        for key, value in data.items():
            setattr(self, key, value)

def langs_setup():
    """Placeholder for language setup"""
    pass

# Initialize global variables
settings = None
MONGO_DB = None
SETTINGS_DB = None  
USERS_DB = None

print("⚠️ Using minimal Vocard compatibility mode")
print("💡 For full music functionality, restore complete Vocard files") 