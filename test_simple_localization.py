#!/usr/bin/env python3
"""
Simple test script to verify the new localization approach
"""
import asyncio
import discord
from discord import app_commands
import language

class MockBot:
    def __init__(self):
        self.guilds = []
        self.http = None
        self.tree = None
    
    def get_guild(self, guild_id):
        for guild in self.guilds:
            if guild.id == guild_id:
                return guild
        return None

class MockGuild:
    def __init__(self, id, name):
        self.id = id
        self.name = name

class MockCommandTree:
    def __init__(self):
        self.commands = {}
    
    def get_commands(self):
        return [MockCommand(name) for name in self.commands.keys()]
    
    def sync(self):
        print(f"🔄 Syncing {len(self.commands)} commands")
        return len(self.commands)

class MockCommand:
    def __init__(self, name):
        self.name = name

# Test commands
@app_commands.command(
    name="coinflip",
    description="Flip a coin! Heads or Tails? 🪙"
)
async def coinflip_test(interaction: discord.Interaction):
    await interaction.response.send_message("Coinflip test!")

async def test_simple_localization():
    """Test the simple localization system"""
    print("🧪 Testing Simple Command Localization System")
    print("=" * 50)
    
    # Initialize language system
    bot = MockBot()
    bot.tree = MockCommandTree()
    language.setup_language_system(bot)
    
    # Create test guilds
    guild1 = MockGuild(123456789, "English Server")
    guild2 = MockGuild(987654321, "Spanish Server")
    bot.guilds = [guild1, guild2]
    
    # Set different languages for each guild
    language.set_server_language(123456789, "en")
    language.set_server_language(987654321, "es")
    
    print(f"✅ Set up test guilds:")
    print(f"   • {guild1.name}: English")
    print(f"   • {guild2.name}: Spanish")
    
    # Register test commands
    language.register_command("coinflip", coinflip_test, "coinflip", "Flip a coin! Heads or Tails? 🪙")
    
    print(f"\n✅ Registered commands: {list(language.command_registry.keys())}")
    
    # Test getting localized command info
    print("\n📝 Testing command localization:")
    
    # English server
    coinflip_en_name, coinflip_en_desc = language.get_localized_command_info("coinflip", "en")
    print(f"English coinflip: {coinflip_en_name} - {coinflip_en_desc}")
    
    # Spanish server
    coinflip_es_name, coinflip_es_desc = language.get_localized_command_info("coinflip", "es")
    print(f"Spanish coinflip: {coinflip_es_name} - {coinflip_es_desc}")
    
    # Test simple command registration
    print("\n🔄 Testing simple command registration...")
    try:
        await language.ensure_commands_registered()
        print("✅ Simple command registration completed successfully!")
    except Exception as e:
        print(f"❌ Simple command registration failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n✅ Simple localization test completed!")

if __name__ == "__main__":
    asyncio.run(test_simple_localization()) 