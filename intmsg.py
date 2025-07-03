import discord
from discord import app_commands
from discord.app_commands import checks
import asyncio
import functools
from typing import Callable, Any
import traceback
import sqlite3
import os
from database import get_session
from ticket_system import (
    InteractiveMessage, MessageButton, Ticket, IntMsgCreator,
    InteractiveMessageView, ButtonSetupModal
)

# Store reference to the client
_client = None

def setup_intmsg_system(client):
    """Initialize the interactive message system with client reference"""
    global _client
    _client = client

def log_command(func: Callable) -> Callable:
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

# Global dictionary to track ongoing conversations
intmsg_conversations = {}

class IntMsgConversation:
    def __init__(self, user_id, channel_id, guild_id, target_channel_id):
        self.user_id = user_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.target_channel_id = target_channel_id  # Where final message will be sent
        self.step = 1
        self.data = {
            'title': None,
            'description': None,
            'color': '#5865F2',
            'buttons': []
        }
    
    def add_button(self, button_data):
        self.data['buttons'].append(button_data)

async def can_create_intmsg(interaction: discord.Interaction) -> bool:
    """Check if user can create interactive messages"""
    # Check if user is administrator
    if interaction.user.guild_permissions.administrator:
        return True
    
    # Check if user is in the intmsg creator whitelist
    session = get_session(str(interaction.guild_id))
    try:
        creator = session.query(IntMsgCreator).filter_by(
            user_id=str(interaction.user.id),
            server_id=str(interaction.guild_id)
        ).first()
        return creator is not None
    finally:
        session.close() 

async def start_intmsg_conversation(interaction):
    """Start the interactive message conversation"""
    user_id = str(interaction.user.id)
    channel_id = str(interaction.channel_id)
    guild_id = str(interaction.guild_id)
    
    print(f"🚀 Starting intmsg conversation for {interaction.user.name}")
    
    intmsg_conversations[user_id] = IntMsgConversation(
        user_id, 
        channel_id, 
        guild_id,
        None  # Will be set when user chooses channel
    )
    
    print(f"   ✅ Conversation initialized, total active: {len(intmsg_conversations)}")

async def handle_intmsg_message(message):
    """Handle conversation messages for intmsg creation"""
    if message.author == _client.user or message.author.bot:
        return False
    
    user_id = str(message.author.id)
    
    # Check if user is in an intmsg conversation
    if user_id in intmsg_conversations:
        conversation = intmsg_conversations[user_id]
        
        print(f"🎯 Processing intmsg conversation for {message.author.name} (step {conversation.step})")
        
        # Check if message is in the right channel
        if str(message.channel.id) != conversation.channel_id:
            print(f"   ❌ Channel mismatch: {message.channel.id} != {conversation.channel_id}")
            return False
        
        # Handle cancel
        if message.content.lower() == 'cancel':
            del intmsg_conversations[user_id]
            await message.reply("❌ Interactive message creation cancelled.")
            return True
        
        try:
            await handle_intmsg_conversation_step(message, conversation)
        except Exception as e:
            print(f"   ❌ Error in conversation step: {e}")
            print(traceback.format_exc())
            await message.reply(f"❌ An error occurred: {str(e)}\nType `cancel` to abort or try again.")
        return True
    
    return False

async def handle_intmsg_conversation_step(message, conversation):
    """Handle each step of the intmsg conversation"""
    content = message.content.strip()
    
    if conversation.step == 1:  # Title
        conversation.data['title'] = content
        conversation.step = 2
        await message.reply(
            f"✅ Title set to: **{content}**\n\n"
            "**Step 2/7:** What should the **description** be? (or type `skip` for no description)"
        )
    
    elif conversation.step == 2:  # Description
        if content.lower() != 'skip':
            conversation.data['description'] = content
        conversation.step = 3
        await message.reply(
            "✅ Description set!\n\n"
            "**Step 3/7:** What **color** do you want? (hex format like `#FF0000` for red, or type `skip` for default blue)"
        )
    
    elif conversation.step == 3:  # Color
        if content.lower() != 'skip':
            if content.startswith('#') and len(content) == 7:
                try:
                    int(content[1:], 16)  # Validate hex
                    conversation.data['color'] = content
                except ValueError:
                    await message.reply("❌ Invalid color format! Using default blue. Please use format like `#FF0000`")
            else:
                await message.reply("❌ Invalid color format! Using default blue. Please use format like `#FF0000`")
        
        conversation.step = 4
        await message.reply(
            "✅ Color set!\n\n"
            "**Step 4/7:** Do you want to add **ticket buttons**? \n"
            "Type `yes` to add ticket buttons, or `no` to skip.\n\n"
            "*Ticket buttons create temporary channels when clicked.*"
        )
    
    elif conversation.step == 4:  # Ticket buttons
        if content.lower() in ['yes', 'y']:
            conversation.step = 41  # Sub-step for ticket details
            await message.reply(
                "🎫 **Adding Ticket Buttons**\n\n"
                "Please provide ticket button details in this format:\n"
                "```\n"
                "Label: Support Ticket\n"
                "Emoji: 🎫\n"
                "Style: primary\n"
                "Name Format: ticket-{id}\n"
                "Welcome Message: Welcome! Staff will help you soon.\n"
                "Questions: What is your issue? [Describe your problem in detail] | When did this start? [Today, yesterday, last week, etc.] | What have you tried? [List the steps you've already taken]\n"
                "Ticket Visible To: 123456789012345678, 987654321098765432\n"
                "```\n"
                "**Styles:** primary (blue), secondary (gray), success (green), danger (red)\n"
                "**Name Format:** Use `{id}` for ticket number, `{user}` for username\n"
                "**Questions:** Format: `Question text [Example answer]` separated by ` | `\n"
                "**Visible To:** Role IDs separated by commas (get by right-clicking role → Copy ID)\n\n"
                "*You can add multiple ticket buttons by separating them with `---`*"
            )
        else:
            conversation.step = 5
            await message.reply(
                "**Step 5/7:** Do you want to add **role buttons**?\n"
                "Type `yes` to add role buttons, or `no` to skip.\n\n"
                "*Role buttons give/remove roles when clicked.*"
            )
    
    elif conversation.step == 41:  # Ticket button details
        await parse_ticket_buttons(message, conversation, content)
    
    elif conversation.step == 5:  # Role buttons
        if content.lower() in ['yes', 'y']:
            conversation.step = 51  # Sub-step for role details
            await message.reply(
                "👤 **Adding Role Buttons**\n\n"
                "Please provide role button details in this format:\n"
                "```\n"
                "Label: Get Updates\n"
                "Emoji: 📢\n"
                "Style: secondary\n"
                "Role ID: 123456789012345678\n"
                "Action: add\n"
                "```\n"
                "**Styles:** primary (blue), secondary (gray), success (green), danger (red)\n"
                "**Actions:** `add` to give role, `remove` to take role\n\n"
                "*You can add multiple role buttons by separating them with `---`*\n"
                "*To get Role ID: Right-click role → Copy ID (enable Developer Mode)*"
            )
        else:
            conversation.step = 6
            await message.reply(
                "**Step 6/7:** Which **channel** should this interactive message be sent to?\n"
                "Please mention the channel (like #general) or type the channel name."
            )
    
    elif conversation.step == 51:  # Role button details
        await parse_role_buttons(message, conversation, content)
    
    elif conversation.step == 6:  # Channel selection
        # Parse channel mention or name
        channel = None
        guild = _client.get_guild(int(conversation.guild_id))
        
        # Try to parse channel mention like #general
        if content.startswith('<#') and content.endswith('>'):
            try:
                channel_id = content[2:-1]
                channel = guild.get_channel(int(channel_id))
            except:
                pass
        
        # Try to find channel by name
        if not channel:
            # Remove # if present
            channel_name = content.lstrip('#').lower()
            for c in guild.text_channels:
                if c.name.lower() == channel_name:
                    channel = c
                    break
        
        if not channel:
            await message.reply(
                "❌ Channel not found! Please mention a valid channel (like #general) or type the exact channel name."
            )
            return
        
        # Check if bot can send messages to the target channel
        if not channel.permissions_for(guild.me).send_messages:
            await message.reply(
                f"❌ I don't have permission to send messages in {channel.mention}!"
            )
            return
        
        # Set the target channel
        conversation.target_channel_id = str(channel.id)
        conversation.step = 7
        
        await message.reply(
            f"✅ Channel set to {channel.mention}!\n\n"
            "**Step 7/7:** Ready to create your interactive message!\n"
            "Type `confirm` to create the message, or `cancel` to abort."
        )
    
    elif conversation.step == 7:  # Final confirmation
        if content.lower() == 'confirm':
            await finalize_intmsg_creation(message, conversation)
        else:
            await message.reply(
                "Please type `confirm` to create the message, or `cancel` to abort the creation process."
            )

async def parse_ticket_buttons(message, conversation, content):
    """Parse ticket button configuration"""
    try:
        # Split multiple buttons
        button_configs = content.split('---')
        
        for config in button_configs:
            lines = [line.strip() for line in config.strip().split('\n') if line.strip()]
            button_data = {
                'type': 'ticket',
                'label': 'Ticket',
                'emoji': None,
                'style': 'primary',
                'name_format': 'ticket-{id}',
                'welcome_message': None,
                'questions': None,
                'visible_roles': None
            }
            
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()
                    
                    if key in ['label', 'name']:
                        button_data['label'] = value
                    elif key == 'emoji':
                        button_data['emoji'] = value
                    elif key == 'style':
                        if value.lower() in ['primary', 'secondary', 'success', 'danger']:
                            button_data['style'] = value.lower()
                    elif key in ['name format', 'format', 'name_format']:
                        button_data['name_format'] = value
                    elif key in ['welcome message', 'welcome', 'message']:
                        button_data['welcome_message'] = value
                    elif key in ['questions', 'question']:
                        button_data['questions'] = value
                    elif key in ['ticket visible to', 'visible to', 'roles', 'visible_roles']:
                        button_data['visible_roles'] = value
            
            conversation.add_button(button_data)
        
        # Check if this is an edit operation
        if 'message_id' in conversation.data:
            await add_buttons_to_existing_message(message, conversation, 'ticket')
        else:
            conversation.step = 5
            await message.reply(
                f"✅ Added {len(button_configs)} ticket button(s)!\n\n"
                "**Step 5/7:** Do you want to add **role buttons**?\n"
                "Type `yes` to add role buttons, or `no` to skip."
            )
        
    except Exception as e:
        await message.reply(
            "❌ Error parsing ticket buttons. Please try again with the correct format:\n"
            "```\n"
            "Label: Support Ticket\n"
            "Emoji: 🎫\n"
            "Style: primary\n"
            "Name Format: ticket-{id}\n"
            "Welcome Message: Welcome!\n"
            "```"
        )

async def parse_role_buttons(message, conversation, content):
    """Parse role button configuration"""
    try:
        # Split multiple buttons
        button_configs = content.split('---')
        
        for config in button_configs:
            lines = [line.strip() for line in config.strip().split('\n') if line.strip()]
            button_data = {
                'type': 'role',
                'label': 'Role',
                'emoji': None,
                'style': 'secondary',
                'role_id': None,
                'action': 'add'
            }
            
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip()
                    
                    if key in ['label', 'name']:
                        button_data['label'] = value
                    elif key == 'emoji':
                        button_data['emoji'] = value
                    elif key == 'style':
                        if value.lower() in ['primary', 'secondary', 'success', 'danger']:
                            button_data['style'] = value.lower()
                    elif key in ['role id', 'role', 'role_id']:
                        button_data['role_id'] = value
                    elif key == 'action':
                        if value.lower() in ['add', 'remove']:
                            button_data['action'] = value.lower()
            
            if not button_data['role_id']:
                await message.reply("❌ Role ID is required for role buttons!")
                return
            
            conversation.add_button(button_data)
        
        # Check if this is an edit operation
        if 'message_id' in conversation.data:
            await add_buttons_to_existing_message(message, conversation, 'role')
        else:
            conversation.step = 6
            await message.reply(
                f"✅ Added {len(button_configs)} role button(s)!\n\n"
                "**Step 6/7:** Which **channel** should this interactive message be sent to?\n"
                "Please mention the channel (like #general) or type the channel name."
            )
        
    except Exception as e:
        await message.reply(
            "❌ Error parsing role buttons. Please try again with the correct format:\n"
            "```\n"
            "Label: Get Updates\n"
            "Emoji: 📢\n"
            "Style: secondary\n"
            "Role ID: 123456789012345678\n"
            "Action: add\n"
            "```"
        ) 

async def finalize_intmsg_creation(message, conversation):
    """Create the final interactive message"""
    try:
        # Create the embed
        color = discord.Color.blurple()
        try:
            color = discord.Color(int(conversation.data['color'][1:], 16))
        except:
            pass
        
        # Build description with larger title
        description_text = conversation.data['description'] if conversation.data['description'] else ""
        
        # Extract pings from description for message content
        ping_content = ""
        cleaned_description = description_text
        
        if description_text:
            # Check for @everyone and @here mentions
            if "@everyone" in description_text:
                ping_content += "@everyone "
                # Keep @everyone in the description but it won't ping from embed
            if "@here" in description_text:
                ping_content += "@here "
                # Keep @here in the description but it won't ping from embed
        
        if description_text:
            full_description = f"# {conversation.data['title']}\n\n{description_text}"
        else:
            full_description = f"# {conversation.data['title']}"
        
        embed = discord.Embed(
            description=full_description,
            color=color
        )
        
        # Send the message to the target channel with ping content if needed
        channel = _client.get_channel(int(conversation.target_channel_id))
        if ping_content.strip():
            sent_message = await channel.send(content=ping_content.strip(), embed=embed)
        else:
            sent_message = await channel.send(embed=embed)
        
        # Update embed with message ID
        if description_text:
            updated_description = f"# {conversation.data['title']}\n\n{description_text}\n\n-# Message ID: {sent_message.id}"
        else:
            updated_description = f"# {conversation.data['title']}\n\n-# Message ID: {sent_message.id}"
        
        embed.description = updated_description
        
        # Save to database
        session = get_session(conversation.guild_id)
        try:
            interactive_msg = InteractiveMessage(
                message_id=str(sent_message.id),
                channel_id=conversation.target_channel_id,
                server_id=conversation.guild_id,
                title=conversation.data['title'],
                description=conversation.data['description'],
                color=str(hex(color.value)),
                created_by=conversation.user_id
            )
            session.add(interactive_msg)
            session.flush()  # Get the ID
            
            # Add buttons to database
            for btn_data in conversation.data['buttons']:
                db_button = MessageButton(
                    message_id=interactive_msg.id,
                    label=btn_data['label'],
                    emoji=btn_data.get('emoji'),
                    style=btn_data['style'],
                    button_type=btn_data['type']
                )
                
                if btn_data['type'] == 'ticket':
                    db_button.ticket_name_format = btn_data['name_format']
                    db_button.ticket_description = btn_data.get('welcome_message')
                    db_button.ticket_id_start = 1
                    db_button.ticket_questions = btn_data.get('questions')
                    db_button.ticket_visible_roles = btn_data.get('visible_roles')
                else:  # role
                    db_button.role_id = btn_data['role_id']
                    db_button.role_action = btn_data['action']
                
                session.add(db_button)
            
            session.commit()
            
            # Update message with buttons if any
            if conversation.data['buttons']:
                # Refresh the interactive_msg object with buttons
                session.refresh(interactive_msg)
                view = InteractiveMessageView(interactive_msg)
                await sent_message.edit(embed=embed, view=view)
            else:
                await sent_message.edit(embed=embed)
            
            # Success message
            button_count = len(conversation.data['buttons'])
            target_channel = _client.get_channel(int(conversation.target_channel_id))
            await message.reply(
                f"✅ **Interactive message created successfully!**\n\n"
                f"📊 **Summary:**\n"
                f"• Title: {conversation.data['title']}\n"
                f"• Buttons: {button_count}\n"
                f"• Sent to: {target_channel.mention}\n"
                f"• Message ID: {interactive_msg.id}\n\n"
                f"Use `/editintmsg {interactive_msg.id}` to modify it later!"
            )
            
        except Exception as e:
            print(f"Database error: {e}")
            await message.reply("❌ Error saving to database. Please try again.")
        finally:
            session.close()
        
        # Clean up conversation
        del intmsg_conversations[conversation.user_id]
        
    except Exception as e:
        print(f"Error creating interactive message: {e}")
        await message.reply("❌ Error creating interactive message. Please try again.")
        if conversation.user_id in intmsg_conversations:
            del intmsg_conversations[conversation.user_id]

async def add_buttons_to_existing_message(message, conversation, button_type):
    """Add buttons to an existing interactive message"""
    session = get_session(conversation.guild_id)
    try:
        message_id = conversation.data['message_id']
        interactive_msg = session.query(InteractiveMessage).get(message_id)
        
        if not interactive_msg:
            await message.reply("❌ Interactive message not found!")
            return
        
        # Add buttons to database
        for btn_data in conversation.data['buttons']:
            db_button = MessageButton(
                message_id=interactive_msg.id,
                label=btn_data['label'],
                emoji=btn_data.get('emoji'),
                style=btn_data['style'],
                button_type=btn_data['type']
            )
            
            if btn_data['type'] == 'ticket':
                db_button.ticket_name_format = btn_data['name_format']
                db_button.ticket_description = btn_data.get('welcome_message')
                db_button.ticket_id_start = 1
                db_button.ticket_questions = btn_data.get('questions')
                db_button.ticket_visible_roles = btn_data.get('visible_roles')
            else:  # role
                db_button.role_id = btn_data['role_id']
                db_button.role_action = btn_data['action']
            
            session.add(db_button)
        
        session.commit()
        
        # Update the Discord message
        try:
            channel = _client.get_channel(int(interactive_msg.channel_id))
            discord_message = await channel.fetch_message(int(interactive_msg.message_id))
            
            # Refresh interactive_msg to get new buttons
            session.refresh(interactive_msg)
            
            # Build updated embed
            color = discord.Color(int(interactive_msg.color, 16))
            description_text = interactive_msg.description if interactive_msg.description else ""
            
            if description_text:
                updated_description = f"# {interactive_msg.title}\n\n{description_text}\n\n-# Message ID: {interactive_msg.message_id}"
            else:
                updated_description = f"# {interactive_msg.title}\n\n-# Message ID: {interactive_msg.message_id}"
            
            embed = discord.Embed(
                description=updated_description,
                color=color
            )
            
            # Update with new view
            view = InteractiveMessageView(interactive_msg)
            await discord_message.edit(embed=embed, view=view)
            
            button_count = len(conversation.data['buttons'])
            await message.reply(
                f"✅ Added {button_count} {button_type} button(s) to the interactive message!\n"
                f"Use `/editintmsg {interactive_msg.message_id}` to add more or make changes."
            )
            
        except Exception as e:
            print(f"Error updating Discord message: {e}")
            await message.reply("✅ Buttons added to database, but couldn't update the Discord message. Try using `/editintmsg` to refresh it.")
        
    except Exception as e:
        print(f"Error adding buttons to existing message: {e}")
        await message.reply("❌ Error adding buttons to the message. Please try again.")
    finally:
        session.close()
        
        # Clean up conversation
        if conversation.user_id in intmsg_conversations:
            del intmsg_conversations[conversation.user_id]

# UI Classes
class EditIntMsgView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=300)
        self.message_id = message_id
    
    @discord.ui.button(label="📝 Edit Message", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = EditMessageModal(self.message_id, str(interaction.guild_id))
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="➕ Add Ticket Button", style=discord.ButtonStyle.success, emoji="🎫")
    async def add_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "🎫 **Adding Ticket Button**\n\n"
            "Please reply with the ticket button details in this format:\n"
            "```\n"
            "Label: Support Ticket\n"
            "Emoji: 🎫\n"
            "Style: primary\n"
            "Name Format: ticket-{id}\n"
            "Welcome Message: Welcome! Staff will help you soon.\n"
            "Questions: What is your issue? [Describe your problem in detail] | When did this start? [Today, yesterday, last week, etc.] | What have you tried? [List the steps you've already taken]\n"
            "Ticket Visible To: 123456789012345678, 987654321098765432\n"
            "```\n"
            "**Styles:** primary (blue), secondary (gray), success (green), danger (red)\n"
            "**Name Format:** Use `{id}` for ticket number, `{user}` for username\n"
            "**Questions:** Format: `Question text [Example answer]` separated by ` | `\n"
            "**Visible To:** Role IDs separated by commas (get by right-clicking role → Copy ID)",
            ephemeral=True
        )
        # Start edit conversation for this button
        user_id = str(interaction.user.id)
        intmsg_conversations[user_id] = IntMsgConversation(
            user_id, 
            str(interaction.channel_id), 
            str(interaction.guild_id),
            str(interaction.channel_id)  # Use same channel for both conversation and target
        )
        intmsg_conversations[user_id].step = 41  # Ticket button step
        intmsg_conversations[user_id].data['message_id'] = self.message_id
    
    @discord.ui.button(label="➕ Add Role Button", style=discord.ButtonStyle.success, emoji="👤")
    async def add_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "👤 **Adding Role Button**\n\n"
            "Please reply with the role button details in this format:\n"
            "```\n"
            "Label: Get Updates\n"
            "Emoji: 📢\n"
            "Style: secondary\n"
            "Role ID: 123456789012345678\n"
            "Action: add\n"
            "```\n"
            "**Styles:** primary (blue), secondary (gray), success (green), danger (red)\n"
            "**Actions:** `add` to give role, `remove` to take role\n\n"
            "*To get Role ID: Right-click role → Copy ID (enable Developer Mode)*",
            ephemeral=True
        )
        # Start edit conversation for this button  
        user_id = str(interaction.user.id)
        intmsg_conversations[user_id] = IntMsgConversation(
            user_id, 
            str(interaction.channel_id), 
            str(interaction.guild_id),
            str(interaction.channel_id)  # Use same channel for both conversation and target
        )
        intmsg_conversations[user_id].step = 51  # Role button step
        intmsg_conversations[user_id].data['message_id'] = self.message_id
    
    @discord.ui.button(label="🗑️ Remove Button", style=discord.ButtonStyle.danger, emoji="❌")
    async def remove_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = get_session(str(interaction.guild_id))
        try:
            interactive_msg = session.get(InteractiveMessage, self.message_id)
            if not interactive_msg or not interactive_msg.buttons:
                await interaction.response.send_message("❌ No buttons to remove!", ephemeral=True)
                return
            
            # Create dropdown for button selection
            options = []
            for btn in interactive_msg.buttons:
                btn_type_emoji = "🎫" if btn.button_type == 'ticket' else "👤"
                options.append(discord.SelectOption(
                    label=f"{btn.label} ({btn.button_type})",
                    value=str(btn.id),
                    emoji=btn_type_emoji,
                    description=f"Style: {btn.style} | Type: {btn.button_type}"
                ))
            
            view = ButtonRemovalView(self.message_id, options)
            await interaction.response.send_message(
                "Select which button to remove:",
                view=view,
                ephemeral=True
            )
        except Exception as e:
            print(f"Error in remove button: {e}")
            await interaction.response.send_message("❌ An error occurred.", ephemeral=True)
        finally:
            session.close()
    
    @discord.ui.button(label="🔄 Update & Refresh", style=discord.ButtonStyle.blurple, emoji="🔄")
    async def update_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = MessageManagementView(self.message_id)
        await view._update_interactive_message(interaction)

class EditMessageModal(discord.ui.Modal):
    def __init__(self, message_id, guild_id):
        super().__init__(title="Edit Interactive Message")
        self.message_id = message_id
        self.guild_id = guild_id
        
        # Load current values
        session = get_session(guild_id)
        try:
            interactive_msg = session.get(InteractiveMessage, message_id)
            current_title = interactive_msg.title if interactive_msg else ""
            current_desc = interactive_msg.description if interactive_msg else ""
            
            # Ensure color is properly formatted as #RRGGBB (7 characters max)
            if interactive_msg and interactive_msg.color:
                color_value = interactive_msg.color
                # Handle different color formats and convert to #RRGGBB
                if color_value.startswith('0x'):
                    # Convert 0x5865f2 to #5865F2
                    current_color = f"#{color_value[2:].upper()}"
                elif color_value.startswith('#'):
                    # Already in correct format, just ensure uppercase
                    current_color = color_value.upper()
                else:
                    # Assume it's just the hex digits
                    current_color = f"#{color_value.upper()}"
                
                # Ensure it's exactly 7 characters (#RRGGBB)
                if len(current_color) != 7:
                    current_color = "#5865F2"  # Default if invalid
            else:
                current_color = "#5865F2"
                
        except Exception as e:
            print(f"Error loading interactive message data: {e}")
            current_title = ""
            current_desc = ""
            current_color = "#5865F2"
        finally:
            session.close()
        
        self.title_input = discord.ui.TextInput(
            label="Message Title",
            placeholder="Enter the new title...",
            required=True,
            default=current_title,
            max_length=256
        )
        self.add_item(self.title_input)
        
        self.description_input = discord.ui.TextInput(
            label="Message Description",
            placeholder="Enter the new description...",
            required=False,
            default=current_desc,
            style=discord.TextStyle.paragraph,
            max_length=2000
        )
        self.add_item(self.description_input)
        
        self.color_input = discord.ui.TextInput(
            label="Embed Color (Hex)",
            placeholder="Enter hex color (e.g., #5865F2)",
            required=False,
            default=current_color,
            max_length=7
        )
        self.add_item(self.color_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        session = get_session(self.guild_id)
        try:
            interactive_msg = session.get(InteractiveMessage, self.message_id)
            if not interactive_msg:
                await interaction.response.send_message("❌ Interactive message not found!", ephemeral=True)
                return
            
            # Update database
            interactive_msg.title = self.title_input.value
            interactive_msg.description = self.description_input.value
            
            # Handle color
            color = discord.Color.blurple()
            if self.color_input.value:
                try:
                    color = discord.Color(int(self.color_input.value.replace('#', ''), 16))
                    interactive_msg.color = str(hex(color.value))
                except ValueError:
                    pass
            
            session.commit()
            
            # Update the actual Discord message
            try:
                channel = _client.get_channel(int(interactive_msg.channel_id))
                message = await channel.fetch_message(int(interactive_msg.message_id))
                
                # Build description with larger title and message ID
                description_text = interactive_msg.description if interactive_msg.description else ""
                if description_text:
                    updated_description = f"# {interactive_msg.title}\n\n{description_text}\n\n-# Message ID: {interactive_msg.message_id}"
                else:
                    updated_description = f"# {interactive_msg.title}\n\n-# Message ID: {interactive_msg.message_id}"
                
                embed = discord.Embed(
                    description=updated_description,
                    color=color
                )
                
                # Keep existing buttons if any
                if interactive_msg.buttons:
                    view = InteractiveMessageView(interactive_msg)
                    await message.edit(embed=embed, view=view)
                else:
                    await message.edit(embed=embed, view=None)
                
                await interaction.response.send_message("✅ Interactive message updated successfully!", ephemeral=True)
                
            except Exception as e:
                print(f"Error updating Discord message: {e}")
                await interaction.response.send_message("✅ Database updated, but couldn't update Discord message. Try using 'Update & Refresh' button.", ephemeral=True)
                
        except Exception as e:
            print(f"Error updating interactive message: {e}")
            await interaction.response.send_message("❌ An error occurred while updating the message.", ephemeral=True)
        finally:
            session.close() 

class ButtonRemovalView(discord.ui.View):
    def __init__(self, message_id, options):
        super().__init__(timeout=60)
        self.message_id = message_id
        
        select = ButtonRemovalSelect(message_id, options)
        self.add_item(select)

class ButtonRemovalSelect(discord.ui.Select):
    def __init__(self, message_id, options):
        super().__init__(
            placeholder="Choose a button to remove...",
            options=options,
            min_values=1,
            max_values=1
        )
        self.message_id = message_id
    
    async def callback(self, interaction: discord.Interaction):
        session = get_session(str(interaction.guild_id))
        try:
            button_id = int(self.values[0])
            button = session.get(MessageButton, button_id)
            
            if not button:
                await interaction.response.send_message("❌ Button not found!", ephemeral=True)
                return
            
            button_label = button.label
            session.delete(button)
            session.commit()
            
            await interaction.response.send_message(f"✅ Button '{button_label}' removed successfully!", ephemeral=True)
            
        except Exception as e:
            print(f"Error removing button: {e}")
            await interaction.response.send_message("❌ An error occurred while removing the button.", ephemeral=True)
        finally:
            session.close()

class MessageManagementView(discord.ui.View):
    def __init__(self, message_id):
        super().__init__(timeout=300)
        self.message_id = message_id
    
    @discord.ui.button(label="Add Ticket Button", style=discord.ButtonStyle.primary, emoji="🎫")
    async def add_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ButtonSetupModal(self.message_id, 'ticket')
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Add Role Button", style=discord.ButtonStyle.secondary, emoji="👤")
    async def add_role_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ButtonSetupModal(self.message_id, 'role')
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Update Message", style=discord.ButtonStyle.success, emoji="🔄")
    async def update_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._update_interactive_message(interaction)
    
    async def _update_interactive_message(self, interaction: discord.Interaction):
        session = get_session(str(interaction.guild_id))
        try:
            interactive_msg = session.get(InteractiveMessage, self.message_id)
            if not interactive_msg:
                await interaction.response.send_message("❌ Interactive message not found!", ephemeral=True)
                return
            
            # Get the original message
            try:
                channel = _client.get_channel(int(interactive_msg.channel_id))
                message = await channel.fetch_message(int(interactive_msg.message_id))
            except:
                await interaction.response.send_message("❌ Could not find the original message!", ephemeral=True)
                return
            
            # Create new embed with message ID and larger title
            color = discord.Color(int(interactive_msg.color, 16))
            
            # Build description with larger title and message ID
            description_text = interactive_msg.description if interactive_msg.description else ""
            if description_text:
                updated_description = f"# {interactive_msg.title}\n\n{description_text}\n\n-# Message ID: {interactive_msg.message_id}"
            else:
                updated_description = f"# {interactive_msg.title}\n\n-# Message ID: {interactive_msg.message_id}"
            
            embed = discord.Embed(
                description=updated_description,
                color=color
            )
            
            # Create view with buttons
            if interactive_msg.buttons:
                view = InteractiveMessageView(interactive_msg)
                await message.edit(embed=embed, view=view)
            else:
                await message.edit(embed=embed, view=None)
            
            await interaction.response.send_message("✅ Interactive message updated with current buttons!", ephemeral=True)
            
        except Exception as e:
            print(f"Error updating interactive message: {e}")
            await interaction.response.send_message("❌ An error occurred while updating the message.", ephemeral=True)
        finally:
            session.close()

def setup_intmsg_commands(tree: app_commands.CommandTree):
    """Setup interactive message system commands"""
    
    @tree.command(
        name="intmsg",
        description="Create an interactive message with customizable buttons"
    )
    @log_command
    async def intmsg(interaction: discord.Interaction):
        """Create an interactive message with buttons for tickets and roles"""
        # Check if user can create interactive messages
        if not await can_create_intmsg(interaction):
            await interaction.response.send_message(
                "❌ You don't have permission to create interactive messages!\n\n"
                "Only administrators or whitelisted users can use this command.\n"
                "Ask an admin to add you with `/imw add @user`",
                ephemeral=True
            )
            return
        
        # Start the conversation flow first
        await start_intmsg_conversation(interaction)
        
        await interaction.response.send_message(
            f"🎨 **Interactive Message Creator Started!** {interaction.user.mention}\n\n"
            "I'll guide you through creating your interactive message. You can cancel anytime by typing `cancel`.\n\n"
            "**Step 1/7:** What should the **title** of your message be?\n"
            "👆 **Please reply to this message in this channel with your title!**",
            ephemeral=False  # Make it visible so user knows where to respond
        )

    @tree.command(
        name="imw",
        description="Add or remove a user from the interactive message creator whitelist (Admin only)"
    )
    @app_commands.describe(
        user="The user to add/remove from the interactive message creator whitelist",
        action="The action to perform: 'add' or 'remove'"
    )
    @checks.has_permissions(administrator=True)
    @log_command
    async def imw(interaction: discord.Interaction, user: discord.Member, action: str):
        """Manage interactive message creator whitelist"""
        if action.lower() not in ['add', 'remove']:
            await interaction.response.send_message(
                "❌ Invalid action! Use 'add' or 'remove'.",
                ephemeral=True
            )
            return
        
        session = get_session(str(interaction.guild_id))
        try:
            existing_creator = session.query(IntMsgCreator).filter_by(
                user_id=str(user.id),
                server_id=str(interaction.guild_id)
            ).first()
            
            if action.lower() == 'add':
                if existing_creator:
                    await interaction.response.send_message(
                        f"❌ {user.display_name} is already in the interactive message creator whitelist!",
                        ephemeral=True
                    )
                    return
                
                new_creator = IntMsgCreator(
                    user_id=str(user.id),
                    server_id=str(interaction.guild_id),
                    added_by=str(interaction.user.id)
                )
                session.add(new_creator)
                session.commit()
                
                await interaction.response.send_message(
                    f"✅ Added {user.display_name} to the interactive message creator whitelist!\n"
                    f"They can now use `/intmsg` to create interactive messages.",
                    ephemeral=True
                )
                
            else:  # remove
                if not existing_creator:
                    await interaction.response.send_message(
                        f"❌ {user.display_name} is not in the interactive message creator whitelist!",
                        ephemeral=True
                    )
                    return
                
                session.delete(existing_creator)
                session.commit()
                
                await interaction.response.send_message(
                    f"✅ Removed {user.display_name} from the interactive message creator whitelist!\n"
                    f"They can no longer use `/intmsg` (unless they're an admin).",
                    ephemeral=True
                )
                
        except Exception as e:
            print(f"Error in imw command: {str(e)}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                f"An error occurred while updating the whitelist: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
        name="editintmsg",
        description="Edit an existing interactive message and its buttons"
    )
    @app_commands.describe(
        message_id="The ID of the interactive message to edit"
    )
    @checks.has_permissions(manage_messages=True)
    @log_command
    async def editintmsg(interaction: discord.Interaction, message_id: str):
        """Edit an interactive message and its buttons"""
        session = get_session(str(interaction.guild_id))
        try:
            # Look up by Discord message ID (not database ID)
            interactive_msg = session.query(InteractiveMessage).filter_by(message_id=message_id).first()
            if not interactive_msg:
                await interaction.response.send_message(
                    f"❌ Interactive message not found!\n"
                    f"**Tried to find:** {message_id}\n"
                    f"Make sure you're using the Discord message ID, not the database ID.\n"
                    f"Use `/listmessages` to see available messages.",
                    ephemeral=True
                )
                return
            
            if str(interaction.guild_id) != interactive_msg.server_id:
                await interaction.response.send_message("❌ That message doesn't belong to this server!", ephemeral=True)
                return
            
            # Show comprehensive editing options
            view = EditIntMsgView(interactive_msg.id)
            
            # Show current message info
            button_count = len(interactive_msg.buttons)
            ticket_buttons = sum(1 for b in interactive_msg.buttons if b.button_type == 'ticket')
            role_buttons = sum(1 for b in interactive_msg.buttons if b.button_type == 'role')
            
            embed = discord.Embed(
                title="🛠️ Editing Interactive Message",
                description=f"**Message:** {interactive_msg.title}\n"
                           f"**Current Buttons:** {button_count} total ({ticket_buttons} ticket, {role_buttons} role)\n"
                           f"**Created:** {interactive_msg.created_at.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
                           f"Choose what you want to edit:",
                color=discord.Color.orange()
            )
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            print(f"Error in editintmsg command: {e}")
            await interaction.response.send_message("❌ An error occurred while processing the command.", ephemeral=True)
        finally:
            session.close()

    @tree.command(
        name="listmessages",
        description="List all interactive messages in this server"
    )
    @checks.has_permissions(manage_messages=True)
    @log_command
    async def listmessages(interaction: discord.Interaction):
        """List all interactive messages in the server"""
        session = get_session(str(interaction.guild_id))
        try:
            messages = session.query(InteractiveMessage).filter_by(
                server_id=str(interaction.guild_id)
            ).order_by(InteractiveMessage.created_at.desc()).all()
            
            if not messages:
                await interaction.response.send_message("❌ No interactive messages found in this server!", ephemeral=True)
                return
            
            embed = discord.Embed(
                title="📋 Interactive Messages",
                description="Here are all the interactive messages in this server:",
                color=discord.Color.blue()
            )
            
            for msg in messages:
                button_count = len(msg.buttons)
                ticket_buttons = sum(1 for b in msg.buttons if b.button_type == 'ticket')
                role_buttons = sum(1 for b in msg.buttons if b.button_type == 'role')
                
                value = (
                    f"**ID:** {msg.id}\n"
                    f"**Channel:** <#{msg.channel_id}>\n"
                    f"**Buttons:** {button_count} total ({ticket_buttons} ticket, {role_buttons} role)\n"
                    f"**Created:** {msg.created_at.strftime('%Y-%m-%d %H:%M UTC')}"
                )
                embed.add_field(name=msg.title, value=value, inline=False)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in listmessages command: {e}")
            await interaction.response.send_message("❌ An error occurred while fetching messages.", ephemeral=True)
        finally:
            session.close()

    @tree.command(
        name="ticketstats",
        description="View ticket statistics for this server"
    )
    @checks.has_permissions(manage_messages=True)
    @log_command
    async def ticketstats(interaction: discord.Interaction):
        """View ticket statistics"""
        session = get_session(str(interaction.guild_id))
        try:
            total_tickets = session.query(Ticket).filter_by(server_id=str(interaction.guild_id)).count()
            open_tickets = session.query(Ticket).filter_by(server_id=str(interaction.guild_id), status="open").count()
            closed_tickets = session.query(Ticket).filter_by(server_id=str(interaction.guild_id), status="closed").count()
            
            embed = discord.Embed(
                title="🎫 Ticket Statistics",
                color=discord.Color.green()
            )
            embed.add_field(name="Total Tickets", value=str(total_tickets), inline=True)
            embed.add_field(name="Open Tickets", value=str(open_tickets), inline=True)
            embed.add_field(name="Closed Tickets", value=str(closed_tickets), inline=True)
            
            if total_tickets > 0:
                # Recent tickets
                recent_tickets = session.query(Ticket).filter_by(
                    server_id=str(interaction.guild_id)
                ).order_by(Ticket.created_at.desc()).limit(5).all()
                
                recent_list = []
                for ticket in recent_tickets:
                    try:
                        creator = await _client.fetch_user(int(ticket.creator_id))
                        creator_name = creator.display_name
                    except:
                        creator_name = "Unknown"
                    
                    status_emoji = "🟢" if ticket.status == "open" else "🔴"
                    recent_list.append(f"{status_emoji} Ticket #{ticket.ticket_id} - {creator_name}")
                
                embed.add_field(
                    name="Recent Tickets",
                    value="\n".join(recent_list) if recent_list else "None",
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in ticketstats command: {e}")
            await interaction.response.send_message("❌ An error occurred while fetching statistics.", ephemeral=True)
        finally:
            session.close()

    @tree.command(
        name="fixdb",
        description="Fix database schema issues (Admin only)"
    )
    @checks.has_permissions(administrator=True)
    @log_command
    async def fixdb(interaction: discord.Interaction):
        """Fix database schema by adding missing columns"""
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Import the database fix function
            import sqlite3
            import os
            
            db_path = os.path.join('data', 'tasks.db')
            
            if not os.path.exists(db_path):
                await interaction.followup.send("❌ Database file not found!", ephemeral=True)
                return
            
            fixed_items = []
            
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # Add missing columns to tickets table
            try:
                cursor.execute("ALTER TABLE tickets ADD COLUMN questions_answers TEXT")
                fixed_items.append("✅ Added questions_answers column to tickets table")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    fixed_items.append(f"⚠️ tickets.questions_answers: {e}")
            
            # Add missing columns to message_buttons table
            try:
                cursor.execute("ALTER TABLE message_buttons ADD COLUMN ticket_questions TEXT")
                fixed_items.append("✅ Added ticket_questions column to message_buttons table")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    fixed_items.append(f"⚠️ message_buttons.ticket_questions: {e}")
            
            try:
                cursor.execute("ALTER TABLE message_buttons ADD COLUMN ticket_visible_roles TEXT")
                fixed_items.append("✅ Added ticket_visible_roles column to message_buttons table")
            except sqlite3.OperationalError as e:
                if "duplicate column name" not in str(e).lower():
                    fixed_items.append(f"⚠️ message_buttons.ticket_visible_roles: {e}")
            
            # Create intmsg_creators table if it doesn't exist
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS intmsg_creators (
                        id INTEGER PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        server_id TEXT NOT NULL,
                        added_by TEXT NOT NULL,
                        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                fixed_items.append("✅ Created/verified intmsg_creators table")
            except sqlite3.OperationalError as e:
                fixed_items.append(f"⚠️ intmsg_creators table: {e}")
            
            conn.commit()
            conn.close()
            
            # Reload persistent views after fixing database
            await _client.load_persistent_views()
            
            result_text = "🔧 **Database Fix Results:**\n\n" + "\n".join(fixed_items)
            result_text += "\n\n🔄 **Persistent views reloaded!**\nAll interactive messages should now work after bot restarts."
            
            await interaction.followup.send(result_text, ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Database fix failed: {str(e)}", ephemeral=True)
            print(f"Database fix error: {e}")
            print(traceback.format_exc())

    @tree.command(
        name="testpersistence",
        description="Test the persistence system (Admin only)"
    )
    @checks.has_permissions(administrator=True)
    @log_command
    async def testpersistence(interaction: discord.Interaction):
        """Test persistence system without restarting"""
        await interaction.response.defer(ephemeral=True)
        
        await interaction.followup.send("🔄 Testing persistence system...", ephemeral=True)
        
        # Run the persistence loading system
        await _client.load_persistent_views()
        
        await interaction.followup.send("✅ Persistence test complete! Check console for detailed output.", ephemeral=True) 