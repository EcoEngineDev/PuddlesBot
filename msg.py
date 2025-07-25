import discord
from discord import app_commands
from discord.ext import commands
import functools
import traceback
from typing import Any
import asyncio
import io

def log_command(func):
    """Decorator to log command usage"""
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args: Any, **kwargs: Any) -> Any:
        try:
            print(f"Executing command: {func.__name__}")
            print(f"Command called by: {interaction.user.name}")
            print(f"Arguments: {args}")
            print(f"Keyword arguments: {kwargs}")
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

def setup_msg_commands(tree: app_commands.CommandTree):
    """Setup message sending commands"""
    
    @tree.command(
        name="msg",
        description="Send your next message to a specific channel (Admin only)"
    )
    @app_commands.describe(
        channel="The channel to send your next message to"
    )
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def msg(interaction: discord.Interaction, channel: discord.TextChannel):
        """Wait for the next message from the user and send it to the specified channel"""
        try:
            # Check if the bot has permission to send messages in the target channel
            permissions = channel.permissions_for(interaction.guild.me)
            if not permissions.send_messages:
                await interaction.response.send_message(
                    f"❌ I don't have permission to send messages in {channel.mention}!",
                    ephemeral=True
                )
                return
            
            # Check if bot has permission to attach files (for image support)
            if not permissions.attach_files:
                await interaction.response.send_message(
                    f"❌ I don't have permission to attach files in {channel.mention}!\n"
                    f"Text messages will work, but images won't be forwarded.",
                    ephemeral=True
                )
            
            # Initial response to let the user know we're waiting
            await interaction.response.send_message(
                f"✅ **Ready to forward to {channel.mention}**\n\n"
                f"📝 **Send your next message now** (text, images, or both)\n"
                f"⏱️ You have **60 seconds** to send your message\n"
                f"❌ **To cancel**, type `cancel`",
                ephemeral=True
            )
            
            # Wait for the user's next message
            def check(message):
                return (message.author == interaction.user and 
                       message.guild == interaction.guild and
                       message.channel == interaction.channel)
            
            try:
                user_message = await interaction.client.wait_for('message', check=check, timeout=60.0)
            except asyncio.TimeoutError:
                await interaction.followup.send(
                    "❌ **Timeout!** You didn't send a message within 60 seconds. Command cancelled.",
                    ephemeral=True
                )
                return
            
            # Check if user wants to cancel
            if user_message.content.lower().strip() == 'cancel':
                await user_message.delete()
                await interaction.followup.send(
                    "❌ **Cancelled!** No message was sent.",
                    ephemeral=True
                )
                return
            
            # Check if the message is empty (no content and no attachments)
            if not user_message.content.strip() and not user_message.attachments:
                await user_message.delete()
                await interaction.followup.send(
                    "❌ **Empty message!** Please send a message with content or attachments.",
                    ephemeral=True
                )
                return
            
            # Check message length (Discord limit is 2000 characters)
            if len(user_message.content) > 2000:
                await user_message.delete()
                await interaction.followup.send(
                    f"❌ **Message too long!** ({len(user_message.content)}/2000 characters)\n"
                    f"Please shorten your message by {len(user_message.content) - 2000} characters.",
                    ephemeral=True
                )
                return
            
            # Prepare files from attachments
            files = []
            attachment_info = []
            
            if user_message.attachments:
                for attachment in user_message.attachments:
                    try:
                        # Download the attachment
                        file_data = await attachment.read()
                        file = discord.File(
                            fp=io.BytesIO(file_data),
                            filename=attachment.filename
                        )
                        files.append(file)
                        attachment_info.append(f"📎 {attachment.filename} ({attachment.size} bytes)")
                    except Exception as attach_error:
                        print(f"Error downloading attachment {attachment.filename}: {str(attach_error)}")
                        attachment_info.append(f"❌ Failed to download {attachment.filename}")
            
            # Send the message to the target channel with all mentions allowed
            sent_message = await channel.send(
                content=user_message.content if user_message.content.strip() else None,
                files=files,
                allowed_mentions=discord.AllowedMentions.all()
            )
            
            # Delete the original user message to keep things clean
            try:
                await user_message.delete()
            except:
                pass  # Ignore if we can't delete (permissions, etc.)
            
            # Confirm to the admin
            embed = discord.Embed(
                title="✅ Message Forwarded",
                description=f"Message successfully sent to {channel.mention}",
                color=discord.Color.green()
            )
            embed.add_field(
                name="Target Channel",
                value=f"{channel.mention} (#{channel.name})",
                inline=True
            )
            
            if user_message.content.strip():
                embed.add_field(
                    name="Message Length",
                    value=f"{len(user_message.content)} characters",
                    inline=True
                )
                embed.add_field(
                    name="Message Preview",
                    value=f"```{user_message.content[:200]}{'...' if len(user_message.content) > 200 else ''}```",
                    inline=False
                )
            
            if attachment_info:
                embed.add_field(
                    name="Attachments",
                    value="\n".join(attachment_info),
                    inline=False
                )
            
            embed.add_field(
                name="Message Link",
                value=f"[Jump to message]({sent_message.jump_url})",
                inline=False
            )
            embed.set_footer(text=f"Forwarded by {interaction.user.display_name}")
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ I don't have permission to send messages in {channel.mention}!",
                ephemeral=True
            )
        except discord.NotFound:
            await interaction.followup.send(
                "❌ The specified channel was not found!",
                ephemeral=True
            )
        except Exception as e:
            print(f"Error in msg command: {str(e)}")
            print(traceback.format_exc())
            await interaction.followup.send(
                f"❌ An error occurred while forwarding the message: {str(e)}",
                ephemeral=True
            )

# Export the setup function
__all__ = ['setup_msg_commands'] 