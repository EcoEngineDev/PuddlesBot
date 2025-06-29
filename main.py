import discord
from discord import app_commands
import requests
import os
from keep_alive import keep_alive

# Initialize bot with all intents
class PuddlesBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

client = PuddlesBot()

@client.event
async def on_ready():
    print(f'Logged in as {client.user}')

@client.tree.command(name="quack", description="Get a random duck image!")
async def quack(interaction: discord.Interaction):
    # Using the Random Duck API
    response = requests.get('https://random-d.uk/api/v2/random')
    if response.status_code == 200:
        duck_data = response.json()
        embed = discord.Embed(title="Quack! 🦆", color=discord.Color.yellow())
        embed.set_image(url=duck_data['url'])
        await interaction.response.send_message(embed=embed)
    else:
        await interaction.response.send_message("Sorry, couldn't fetch a duck right now! 😢")

# Keep the bot alive
keep_alive()

# Start the bot with the token
client.run(os.getenv('TOKEN')) 