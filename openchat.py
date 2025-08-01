import discord
from discord import app_commands
from discord.ext import commands
from database import get_session, Base, Column, String, Boolean, DateTime, get_async_session
from datetime import datetime
import functools
import traceback
import disable
import sqlalchemy
import asyncio
import io

# Store reference to the client
_client = None

# Track which channels have OpenChat enabled
active_channels = {}  # guild_id -> channel_id

class OpenChatSettings(Base):
    """Stores OpenChat settings for each server"""
    __tablename__ = 'openchat_settings'
    
    guild_id = Column(String, primary_key=True)
    channel_id = Column(String, nullable=True)  # Channel where OpenChat is active
    enabled = Column(Boolean, default=False)
    enabled_by = Column(String)  # Discord ID of admin who enabled it
    enabled_at = Column(DateTime, default=datetime.utcnow)

class ImageRevealButton(discord.ui.Button):
    def __init__(self, image_url: str):
        super().__init__(
            label="🖼️ Click to View Image",
            style=discord.ButtonStyle.secondary,
            custom_id=f"reveal_image:{image_url}"
        )
        self.image_url = image_url

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(color=discord.Color.blue())
        embed.set_image(url=self.image_url)
        embed.set_footer(text="⚠️ Image content is not moderated. Report violations to server staff.")
        await interaction.response.send_message(embed=embed, ephemeral=True)

class OpenChatView(discord.ui.View):
    def __init__(self, image_urls: list):
        super().__init__(timeout=None)  # Make the button persistent
        for url in image_urls:
            self.add_item(ImageRevealButton(url))

def setup_openchat_system(client):
    """Initialize the OpenChat system with client reference"""
    global _client
    _client = client
    
    # Load active channels from database on startup
    async def load_active_channels():
        try:
            async with get_async_session() as session:
                query = sqlalchemy.select(OpenChatSettings).where(OpenChatSettings.enabled == True)
                result = await session.execute(query)
                enabled_settings = result.scalars().all()
                
                for setting in enabled_settings:
                    active_channels[setting.guild_id] = setting.channel_id
                print(f"✅ Loaded {len(enabled_settings)} active OpenChat channels")
        except Exception as e:
            print(f"❌ Error loading OpenChat channels: {e}")

    # Schedule the loading of active channels
    asyncio.create_task(load_active_channels())

def log_command(func):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        try:
            print(f"Executing OpenChat command: {func.__name__}")
            print(f"Command called by: {interaction.user.name}")
            return await func(interaction, *args, **kwargs)
        except Exception as e:
            print(f"Error in {func.__name__}:")
            print(traceback.format_exc())
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"An error occurred while processing the command. Error: {str(e)}",
                    ephemeral=True
                )
    return wrapper

async def handle_openchat_message(message: discord.Message):
    """Process messages in OpenChat channels"""
    if not message.guild or message.author.bot:
        return False

    # Check if OpenChat is disabled for this server
    if await disable.is_feature_disabled(message.guild.id, "openchat"):
        return False

    # Check if this channel is an OpenChat channel
    if str(message.channel.id) not in active_channels.values():
        return False

    try:
        # Create the base embed
        embed = discord.Embed(
            description=message.content or "_ _",  # Use "_ _" if no content to ensure embed shows
            color=discord.Color.blue(),
            timestamp=message.created_at
        )
        
        # Add user and server info
        embed.set_author(
            name=f"{message.author.display_name} ({message.guild.name})",
            icon_url=message.author.display_avatar.url
        )

        # Handle attachments
        view = None
        image_urls = []
        
        if message.attachments:
            for idx, attachment in enumerate(message.attachments):
                if attachment.content_type and attachment.content_type.startswith('image/'):
                    # For images, add to list for reveal buttons
                    image_urls.append(attachment.url)
                    embed.add_field(
                        name=f"📎 Image Attachment {idx + 1}",
                        value="Click the button below to view the image",
                        inline=False
                    )
                else:
                    # For other files, show warning and link
                    embed.add_field(
                        name=f"⚠️ File Attachment {idx + 1}",
                        value=(
                            f"**{attachment.filename}**\n"
                            f"[Click to Download]({attachment.url})\n\n"
                            "**⚠️ SECURITY WARNING:**\n"
                            "WE DO NOT SCAN FILES FOR MALWARE.\n"
                            "DOWNLOAD AND USE FILES AT YOUR OWN RISK!"
                        ),
                        inline=False
                    )
                    embed.color = discord.Color.yellow()

        # Create view if there are images
        if image_urls:
            view = OpenChatView(image_urls)

        # Forward the message to all other active OpenChat channels
        sent_to = []
        for guild_id, channel_id in list(active_channels.items()):  # Create a copy of items to safely modify during iteration
            # Skip the source channel
            if channel_id == str(message.channel.id):
                continue

            try:
                # Get the target channel
                channel = None
                guild = _client.get_guild(int(guild_id))
                if guild:
                    channel = guild.get_channel(int(channel_id))
                if not channel:
                    try:
                        channel = await _client.fetch_channel(int(channel_id))
                    except discord.NotFound:
                        print(f"Channel {channel_id} not found, removing from active channels")
                        active_channels.pop(guild_id, None)
                        async with get_async_session() as session:
                            settings = await session.get(OpenChatSettings, guild_id)
                            if settings:
                                settings.enabled = False
                                await session.commit()
                        continue
                    except Exception as e:
                        print(f"Error fetching channel {channel_id}: {e}")
                        continue

                if channel:
                    try:
                        await channel.send(embed=embed, view=view)
                        sent_to.append(channel.guild.name)
                    except discord.Forbidden:
                        print(f"No permission to send messages in channel {channel_id}")
                        continue
                    except Exception as e:
                        print(f"Error sending message to channel {channel_id}: {e}")
                        continue

            except Exception as e:
                print(f"Error handling channel {channel_id} in guild {guild_id}: {e}")
                traceback.print_exc()
                # Don't remove the channel here - only remove if we explicitly know it's invalid

        if sent_to:
            print(f"✅ OpenChat message forwarded to: {', '.join(sent_to)}")
            return True
        else:
            print("❌ No active OpenChat channels to forward to")
            return False

    except Exception as e:
        print(f"Error in OpenChat message handling: {e}")
        traceback.print_exc()
        return False

def setup_openchat_commands(tree):
    """Register OpenChat slash commands"""
    
    @tree.command(
        name="openchat",
        description="Manage OpenChat settings for cross-server communication"
    )
    @app_commands.describe(
        action="Choose an action: enable, disable, or status"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="enable", value="enable"),
        app_commands.Choice(name="disable", value="disable"),
        app_commands.Choice(name="status", value="status"),
        app_commands.Choice(name="clear", value="clear")  # Add clear option
    ])
    @log_command
    async def openchat(interaction: discord.Interaction, action: str):
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in servers!", ephemeral=True)
            return

        # Check if OpenChat is disabled for this server
        if await disable.is_feature_disabled(interaction.guild.id, "openchat"):
            await interaction.response.send_message(
                "❌ The OpenChat system is currently disabled in this server. Ask an admin to use `/enable openchat` to enable it.",
                ephemeral=True
            )
            return

        if action == "clear":
            # Only admins can clear the database
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ Only administrators can clear OpenChat data!", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            try:
                # Clear from active channels cache
                active_channels.clear()
                
                # Clear from database
                async with get_async_session() as session:
                    # Delete all OpenChat settings
                    await session.execute(
                        sqlalchemy.delete(OpenChatSettings)
                    )
                    await session.commit()

                await interaction.followup.send(
                    "✅ OpenChat data cleared successfully!\n"
                    "• All channel settings have been reset\n"
                    "• Use `/openchat enable` to set up OpenChat in a channel",
                    ephemeral=True
                )
            except Exception as e:
                print(f"Error clearing OpenChat data: {e}")
                traceback.print_exc()
                await interaction.followup.send(
                    "❌ An error occurred while clearing OpenChat data.",
                    ephemeral=True
                )
            return

        if action == "enable":
            # Check if OpenChat is already enabled in another channel
            existing_channel = active_channels.get(str(interaction.guild.id))
            if existing_channel:
                channel = interaction.guild.get_channel(int(existing_channel))
                await interaction.response.send_message(
                    f"❌ OpenChat is already enabled in {channel.mention if channel else 'another channel'}!",
                    ephemeral=True
                )
                return

            # Enable OpenChat in this channel
            active_channels[str(interaction.guild.id)] = str(interaction.channel.id)
            
            # Update database
            async with get_async_session() as session:
                # Check if settings already exist
                settings = await session.get(OpenChatSettings, str(interaction.guild.id))
                
                if settings:
                    # Update existing settings
                    settings.channel_id = str(interaction.channel.id)
                    settings.enabled = True
                    settings.enabled_by = str(interaction.user.id)
                    settings.enabled_at = datetime.utcnow()
                else:
                    # Create new settings
                    settings = OpenChatSettings(
                        guild_id=str(interaction.guild.id),
                        channel_id=str(interaction.channel.id),
                        enabled=True,
                        enabled_by=str(interaction.user.id)
                    )
                    session.add(settings)
                
                await session.commit()

            # Send success message in channel
            await interaction.channel.send(
                embed=discord.Embed(
                    title="🌐 OpenChat Enabled!",
                    description=(
                        "This channel is now connected to other servers' OpenChat channels!\n\n"
                        "**Features:**\n"
                        "• Messages here are shared with other OpenChat channels\n"
                        "• Images require clicking a button to view (for safety)\n"
                        "• Files show security warnings before download\n\n"
                        "**Rules:**\n"
                        "• No NSFW content\n"
                        "• Follow Discord's Terms of Service\n"
                        "• Be respectful to other servers\n\n"
                        "**Note:** Anyone can disable OpenChat in this channel, and admins can disable it server-wide with `/disable openchat`"
                    ),
                    color=discord.Color.green()
                )
            )

            await interaction.response.send_message(
                "✅ OpenChat enabled successfully!",
                ephemeral=True
            )

        elif action == "disable":
            # Check if this is the active OpenChat channel
            if active_channels.get(str(interaction.guild.id)) != str(interaction.channel.id):
                await interaction.response.send_message(
                    "❌ OpenChat is not enabled in this channel!",
                    ephemeral=True
                )
                return

            # Remove from active channels
            active_channels.pop(str(interaction.guild.id), None)
            
            # Update database
            async with get_async_session() as session:
                settings = await session.get(OpenChatSettings, str(interaction.guild.id))
                if settings:
                    settings.enabled = False
                    await session.commit()

            # Send notification in channel
            await interaction.channel.send(
                embed=discord.Embed(
                    title="🔒 OpenChat Disabled",
                    description="This channel is no longer connected to the OpenChat network.",
                    color=discord.Color.red()
                )
            )

            await interaction.response.send_message(
                "✅ OpenChat disabled successfully!",
                ephemeral=True
            )

        elif action == "status":
            channel_id = active_channels.get(str(interaction.guild.id))
            if channel_id:
                channel = interaction.guild.get_channel(int(channel_id))
                await interaction.response.send_message(
                    f"OpenChat is currently enabled in {channel.mention if channel else 'another channel'}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "OpenChat is not currently enabled in any channel",
                    ephemeral=True
                )

    # Actually register the command with the tree
    tree.add_command(openchat)

# Export the setup functions
__all__ = [
    'setup_openchat_system',
    'setup_openchat_commands',
    'handle_openchat_message'
] 