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
                import language
                user_lang = language.get_server_language(interaction.guild_id)
                await interaction.response.send_message(
                    language.get_text("error_general", user_lang, error=str(e)),
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
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        try:
            # Check if the bot has permission to send messages in the target channel
            permissions = channel.permissions_for(interaction.guild.me)
            if not permissions.send_messages:
                await interaction.response.send_message(
                    language.get_text("msg_no_permission", user_lang, channel_mention=channel.mention),
                    ephemeral=True
                )
                return
            
            # Check if bot has permission to attach files (for image support)
            if not permissions.attach_files:
                await interaction.response.send_message(
                    language.get_text("msg_file_permission", user_lang, channel_mention=channel.mention),
                    ephemeral=True
                )
            
            # Initial response to let the user know we're waiting
            await interaction.response.send_message(
                language.get_text("ready_to_forward", user_lang, channel=channel.mention),
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
                    language.get_text("timeout_message", user_lang),
                    ephemeral=True
                )
                return
            
            # Check if user wants to cancel
            if user_message.content.lower().strip() == 'cancel':
                await user_message.delete()
                await interaction.followup.send(
                    language.get_text("cancelled_message", user_lang),
                    ephemeral=True
                )
                return
            
            # Check if the message is empty (no content and no attachments)
            if not user_message.content.strip() and not user_message.attachments:
                await user_message.delete()
                await interaction.followup.send(
                    language.get_text("empty_message", user_lang),
                    ephemeral=True
                )
                return
            
            # Check message length (Discord limit is 2000 characters)
            if len(user_message.content) > 2000:
                await user_message.delete()
                await interaction.followup.send(
                    language.get_text("message_too_long", user_lang, length=len(user_message.content), difference=len(user_message.content) - 2000),
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
                title=language.get_text("msg_forwarded_title", user_lang),
                description=language.get_text("msg_forwarded_description", user_lang, channel_mention=channel.mention),
                color=discord.Color.green()
            )
            embed.add_field(
                name=language.get_text("msg_target_channel", user_lang),
                value=f"{channel.mention} (#{channel.name})",
                inline=True
            )
            
            if user_message.content.strip():
                embed.add_field(
                    name=language.get_text("msg_message_length", user_lang),
                    value=f"{len(user_message.content)} characters",
                    inline=True
                )
                embed.add_field(
                    name=language.get_text("msg_message_preview", user_lang),
                    value=f"```{user_message.content[:200]}{'...' if len(user_message.content) > 200 else ''}```",
                    inline=False
                )
            
            if attachment_info:
                embed.add_field(
                    name=language.get_text("msg_attachments", user_lang),
                    value="\n".join(attachment_info),
                    inline=False
                )
            
            embed.add_field(
                name=language.get_text("msg_message_link", user_lang),
                value=f"[{language.get_text('msg_jump_to_message', user_lang)}]({sent_message.jump_url})",
                inline=False
            )
            embed.set_footer(text=language.get_text("msg_forwarded_by", user_lang, user=interaction.user.display_name))
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            
        except discord.Forbidden:
            await interaction.followup.send(
                language.get_text("msg_no_permission", user_lang, channel_mention=channel.mention),
                ephemeral=True
            )
        except discord.NotFound:
            await interaction.followup.send(
                language.get_text("msg_channel_not_found", user_lang),
                ephemeral=True
            )
        except Exception as e:
            print(f"Error in msg command: {str(e)}")
            print(traceback.format_exc())
            await interaction.followup.send(
                language.get_text("msg_forward_error", user_lang, error=str(e)),
                ephemeral=True
            )

# Export the setup function
__all__ = ['setup_msg_commands'] 