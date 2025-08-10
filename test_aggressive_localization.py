#!/usr/bin/env python3
"""
Test script to verify aggressive command localization system
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
    
    def clear_commands(self, guild=None):
        print(f"🗑️ Clearing commands (guild: {guild})")
        self.commands.clear()
    
    def add_command(self, command, guild=None):
        print(f"➕ Adding command: {command.name} (guild: {guild})")
        self.commands[command.name] = command
    
    def sync(self, guild=None):
        print(f"🔄 Syncing commands (guild: {guild})")
        return len(self.commands)

# Test commands
@app_commands.command(
    name="coinflip",
    description="Flip a coin! Heads or Tails? 🪙"
)
async def coinflip_test(interaction: discord.Interaction):
    await interaction.response.send_message("Coinflip test!")

@app_commands.command(
    name="quack",
    description="Get a random duck image! 🦆"
)
async def quack_test(interaction: discord.Interaction):
    await interaction.response.send_message("Quack test!")

async def test_aggressive_localization():
    """Test the aggressive localization system"""
    print("🧪 Testing Aggressive Command Localization System")
    print("=" * 60)
    
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
    language.register_command("quack", quack_test, "quack", "Get a random duck image! 🦆")
    
    print(f"\n✅ Registered commands: {list(language.command_registry.keys())}")
    
    # Test getting localized command info
    print("\n📝 Testing command localization:")
    
    # English server
    coinflip_en_name, coinflip_en_desc = language.get_localized_command_info("coinflip", "en")
    quack_en_name, quack_en_desc = language.get_localized_command_info("quack", "en")
    print(f"English coinflip: {coinflip_en_name} - {coinflip_en_desc}")
    print(f"English quack: {quack_en_name} - {quack_en_desc}")
    
    # Spanish server
    coinflip_es_name, coinflip_es_desc = language.get_localized_command_info("coinflip", "es")
    quack_es_name, quack_es_desc = language.get_localized_command_info("quack", "es")
    print(f"Spanish coinflip: {coinflip_es_name} - {coinflip_es_desc}")
    print(f"Spanish quack: {quack_es_name} - {quack_es_desc}")
    
    # Test aggressive reinitialization
    print("\n🚀 Testing aggressive reinitialization...")
    try:
        await language.aggressive_command_reinitialization_for_all_guilds()
        print("✅ Aggressive reinitialization completed successfully!")
    except Exception as e:
        print(f"❌ Aggressive reinitialization failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Test language change
    print("\n🔄 Testing language change...")
    print("Changing English Server to Spanish...")
    language.set_server_language(123456789, "es")
    
    # Wait a moment for async tasks
    await asyncio.sleep(1)
    
    # Check if the change was processed
    new_lang = language.get_server_language(123456789)
    print(f"✅ Language changed to: {new_lang}")
    
    print("\n✅ Aggressive localization test completed!")

if __name__ == "__main__":
    asyncio.run(test_aggressive_localization()) 