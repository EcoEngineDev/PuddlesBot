# Minimal IPC client for Vocard compatibility

class IPCClient:
    """Minimal IPC client to prevent import errors"""
    
    def __init__(self, bot, **kwargs):
        self.bot = bot
        self.config = kwargs
        print("⚠️ Using minimal IPC client (no actual IPC functionality)")
    
    async def connect(self):
        """Placeholder connect method"""
        print("💡 IPC client connection skipped (minimal mode)")
        return True
    
    async def disconnect(self):
        """Placeholder disconnect method"""
        pass 