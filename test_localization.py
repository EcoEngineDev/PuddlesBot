#!/usr/bin/env python3
"""
Test script to demonstrate command localization system
"""

import asyncio
import discord
from discord import app_commands
import language

# Mock bot class for testing
class MockBot:
    def __init__(self):
        self.guilds = []
        self.http = None  # Mock HTTP client
        self.tree = None  # Mock command tree
    
    def get_guild(self, guild_id):
        for guild in self.guilds:
            if guild.id == guild_id:
                return guild
        return None

class MockGuild:
    def __init__(self, id, name):
        self.id = id
        self.name = name

# Test commands
@app_commands.command(
    name="test",
    description="Test command for localization"
)
async def test_command(interaction: discord.Interaction):
    await interaction.response.send_message("Test command executed!")

@app_commands.command(
    name="hello",
    description="Say hello in different languages"
)
async def hello_command(interaction: discord.Interaction):
    user_lang = language.get_user_language(interaction.user.id)
    greeting = language.get_text("welcome_title", user_lang, server_name="Test Server")
    await interaction.response.send_message(greeting)

async def test_localization():
    """Test the localization system"""
    print("🧪 Testing Command Localization System")
    print("=" * 50)
    
    # Initialize language system
    bot = MockBot()
    language.setup_language_system(bot)
    
    # Create test guilds
    guild1 = MockGuild(123456789, "English Server")
    guild2 = MockGuild(987654321, "Spanish Server")
    bot.guilds = [guild1, guild2]
    
    # Set different languages for each guild
    language.set_server_language(123456789, "en")
    language.set_server_language(987654321, "es")
    
    # Register test commands
    language.register_command("test", test_command, "test", "Test command for localization")
    language.register_command("hello", hello_command, "hello", "Say hello in different languages")
    
    # Register coinflip command for testing
    @app_commands.command(
        name="coinflip",
        description="Flip a coin! Heads or Tails? 🪙"
    )
    async def coinflip_test(interaction: discord.Interaction):
        await interaction.response.send_message("Coinflip test!")
    
    language.register_command("coinflip", coinflip_test, "coinflip", "Flip a coin! Heads or Tails? 🪙")
    
    print(f"✅ Registered commands: {list(language.command_registry.keys())}")
    
    # Test getting localized command info
    print("\n📝 Testing command localization:")
    
    # English server
    en_name, en_desc = language.get_localized_command_info("test", "en")
    print(f"English: {en_name} - {en_desc}")
    
    # Spanish server
    es_name, es_desc = language.get_localized_command_info("test", "es")
    print(f"Spanish: {es_name} - {es_desc}")
    
    # Test with non-existent command
    fake_name, fake_desc = language.get_localized_command_info("nonexistent", "en")
    print(f"Non-existent: {fake_name} - {fake_desc}")
    
    print("\n🌐 Testing text localization:")
    
    # Test welcome message
    en_welcome = language.get_text("welcome_title", "en", server_name="Test Server")
    es_welcome = language.get_text("welcome_title", "es", server_name="Test Server")
    
    print(f"English welcome: {en_welcome}")
    print(f"Spanish welcome: {es_welcome}")
    
    # Test command translations
    print("\n🎮 Testing command translations:")
    
    # Test quack command
    quack_en_name, quack_en_desc = language.get_localized_command_info("quack", "en")
    quack_es_name, quack_es_desc = language.get_localized_command_info("quack", "es")
    print(f"Quack command - English: {quack_en_name} - {quack_en_desc}")
    print(f"Quack command - Spanish: {quack_es_name} - {quack_es_desc}")
    
    # Test coinflip command
    coinflip_en_name, coinflip_en_desc = language.get_localized_command_info("coinflip", "en")
    coinflip_es_name, coinflip_es_desc = language.get_localized_command_info("coinflip", "es")
    print(f"Coinflip command - English: {coinflip_en_name} - {coinflip_en_desc}")
    print(f"Coinflip command - Spanish: {coinflip_es_name} - {coinflip_es_desc}")
    
    print("\n✅ Localization test completed!")

if __name__ == "__main__":
    asyncio.run(test_localization()) 