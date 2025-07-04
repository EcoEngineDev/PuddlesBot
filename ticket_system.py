# Comprehensive Ticket System for Discord Bot
# This module provides interactive messages with buttons for ticket creation and role assignment

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import discord
from discord import app_commands
import asyncio
from database import get_session, Base
import time

# Database Models for Ticket System
class InteractiveMessage(Base):
    __tablename__ = 'interactive_messages'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(String, unique=True, nullable=False)
    channel_id = Column(String, nullable=False)
    server_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text)
    color = Column(String, default="0x5865F2")
    created_by = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    buttons = relationship("MessageButton", back_populates="message", cascade="all, delete-orphan")

class MessageButton(Base):
    __tablename__ = 'message_buttons'
    
    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey('interactive_messages.id'), nullable=False)
    label = Column(String, nullable=False)
    emoji = Column(String)
    style = Column(String, default="secondary")
    button_type = Column(String, nullable=False)  # 'ticket' or 'role'
    
    # Ticket fields
    ticket_category_id = Column(String)
    ticket_name_format = Column(String)
    ticket_id_start = Column(Integer, default=1)
    ticket_description = Column(Text)
    ticket_questions = Column(Text)  # JSON string of questions
    ticket_visible_roles = Column(Text)  # Comma-separated role IDs
    
    # Role fields
    role_id = Column(String)
    role_action = Column(String)  # 'add' or 'remove'
    
    message = relationship("InteractiveMessage", back_populates="buttons")

class Ticket(Base):
    __tablename__ = 'tickets'
    
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, nullable=False)
    channel_id = Column(String, unique=True, nullable=False)
    server_id = Column(String, nullable=False)
    creator_id = Column(String, nullable=False)
    button_id = Column(Integer, ForeignKey('message_buttons.id'), nullable=False)
    status = Column(String, default="open")
    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime)
    closed_by = Column(String)
    questions_answers = Column(Text)  # JSON string of Q&A

class IntMsgCreator(Base):
    __tablename__ = 'intmsg_creators'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    server_id = Column(String, nullable=False)
    added_by = Column(String, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)

# Discord UI Components
class InteractiveMessageView(discord.ui.View):
    def __init__(self, message_data):
        super().__init__(timeout=None)
        self.message_data = message_data
        
        for button_data in message_data.buttons:
            if button_data.button_type == 'ticket':
                button = TicketButton(button_data)
            else:
                button = RoleButton(button_data)
            self.add_item(button)

class TicketButton(discord.ui.Button):
    def __init__(self, button_data):
        style_map = {
            'primary': discord.ButtonStyle.primary,
            'secondary': discord.ButtonStyle.secondary,
            'success': discord.ButtonStyle.success,
            'danger': discord.ButtonStyle.danger
        }
        
        super().__init__(
            label=button_data.label,
            style=style_map.get(button_data.style, discord.ButtonStyle.secondary),
            emoji=button_data.emoji if button_data.emoji else None,
            custom_id=f"ticket_btn_{button_data.id}"
        )
        self.button_data = button_data
    
    async def callback(self, interaction: discord.Interaction):
        # Check if there are questions to ask first
        if self.button_data.ticket_questions:
            questions = [q.strip() for q in self.button_data.ticket_questions.split('|') if q.strip()]
            if questions:
                modal = TicketQuestionsModal(self.button_data, questions)
                await interaction.response.send_modal(modal)
                return
        
        # No questions, proceed with ticket creation
        await self.create_ticket(interaction)
    
    async def create_ticket(self, interaction, answers=None):
        session = get_session(str(interaction.guild_id))
        try:
            # Check existing ticket
            existing_ticket = session.query(Ticket).filter_by(
                creator_id=str(interaction.user.id),
                button_id=self.button_data.id,
                status="open"
            ).first()
            
            if existing_ticket:
                await interaction.followup.send(
                    f"You already have an open ticket: <#{existing_ticket.channel_id}>",
                    ephemeral=True
                )
                return
            
            # Get next ticket ID
            last_ticket = session.query(Ticket).filter_by(
                button_id=self.button_data.id
            ).order_by(Ticket.ticket_id.desc()).first()
            
            next_ticket_id = (last_ticket.ticket_id + 1) if last_ticket else self.button_data.ticket_id_start
            
            # Create channel
            guild = interaction.guild
            category = None
            if self.button_data.ticket_category_id:
                category = guild.get_channel(int(self.button_data.ticket_category_id))
            
            channel_name = self.button_data.ticket_name_format.format(
                id=next_ticket_id,
                user=interaction.user.display_name.lower().replace(' ', '-'),
                username=interaction.user.name
            )
            
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user: discord.PermissionOverwrite(
                    read_messages=True, send_messages=True, attach_files=True, embed_links=True
                )
            }
            
            # Add staff permissions
            for role in guild.roles:
                if any(perm in role.name.lower() for perm in ['staff', 'admin', 'mod', 'support']):
                    overwrites[role] = discord.PermissionOverwrite(
                        read_messages=True, send_messages=True, manage_messages=True
                    )
            
            # Add custom visible roles if specified
            if self.button_data.ticket_visible_roles:
                role_ids = [rid.strip() for rid in self.button_data.ticket_visible_roles.split(',') if rid.strip()]
                for role_id in role_ids:
                    try:
                        role = guild.get_role(int(role_id))
                        if role:
                            overwrites[role] = discord.PermissionOverwrite(
                                read_messages=True, send_messages=True, manage_messages=True
                            )
                    except ValueError:
                        pass  # Invalid role ID
            
            ticket_channel = await guild.create_text_channel(
                name=channel_name, category=category, overwrites=overwrites
            )
            
            # Save to database
            new_ticket = Ticket(
                ticket_id=next_ticket_id,
                channel_id=str(ticket_channel.id),
                server_id=str(guild.id),
                creator_id=str(interaction.user.id),
                button_id=self.button_data.id,
                questions_answers=answers  # JSON string of answers
            )
            session.add(new_ticket)
            session.commit()
            
            # Send welcome message
            embed = discord.Embed(
                title=f"🎫 Ticket #{next_ticket_id}",
                description=self.button_data.ticket_description or f"Thank you for creating a ticket, {interaction.user.mention}!\nOur staff will be with you shortly.",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Created by", value=interaction.user.mention, inline=True)
            embed.add_field(name="Ticket ID", value=f"#{next_ticket_id}", inline=True)
            
            # Add question answers if provided
            if answers:
                import json
                try:
                    qa_data = json.loads(answers)
                    qa_text = "\n".join([f"**{qa['question']}**\n{qa['answer']}" for qa in qa_data])
                    embed.add_field(name="📝 Information Provided", value=qa_text, inline=False)
                except:
                    pass
            
            view = TicketControlView(new_ticket.id)
            await ticket_channel.send(embed=embed, view=view)
            
            # Send response (either initial response or followup depending on how we got here)
            response_text = f"✅ Ticket created! Please check {ticket_channel.mention}"
            if interaction.response.is_done():
                await interaction.followup.send(response_text, ephemeral=True)
            else:
                await interaction.response.send_message(response_text, ephemeral=True)
            
        except Exception as e:
            print(f"Error creating ticket: {e}")
            error_text = "❌ An error occurred while creating your ticket. Please try again."
            if interaction.response.is_done():
                await interaction.followup.send(error_text, ephemeral=True)
            else:
                await interaction.response.send_message(error_text, ephemeral=True)
        finally:
            session.close()

class TicketQuestionsModal(discord.ui.Modal):
    def __init__(self, button_data, questions):
        super().__init__(title="Ticket Information", timeout=300)
        self.button_data = button_data
        self.questions = []
        self.question_data = []
        
        # Parse questions and example answers
        raw_questions = questions[:5]  # Limit to 5 questions due to Discord modal limits
        for question_text in raw_questions:
            # Parse format: "Question text [Example answer]"
            if '[' in question_text and ']' in question_text:
                question_part = question_text.split('[')[0].strip()
                example_part = question_text.split('[')[1].split(']')[0].strip()
            else:
                question_part = question_text.strip()
                example_part = f"Please answer: {question_part}"
            
            self.questions.append(question_part)
            self.question_data.append({
                'question': question_part,
                'example': example_part
            })
        
        # Add text inputs for each question
        for i, q_data in enumerate(self.question_data):
            text_input = discord.ui.TextInput(
                label=q_data['question'][:45],  # Discord label limit
                placeholder=q_data['example'][:100],  # Use example as placeholder
                required=True,
                max_length=1000,
                style=discord.TextStyle.paragraph if len(q_data['question']) > 50 else discord.TextStyle.short
            )
            self.add_item(text_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Collect answers
        answers = []
        for i, item in enumerate(self.children):
            if isinstance(item, discord.ui.TextInput):
                answers.append({
                    "question": self.questions[i],
                    "answer": item.value
                })
        
        # Convert to JSON for storage
        import json
        answers_json = json.dumps(answers)
        
        # Create the ticket with answers
        ticket_button = TicketButton(self.button_data)
        await ticket_button.create_ticket(interaction, answers_json)

class RoleButton(discord.ui.Button):
    def __init__(self, button_data):
        style_map = {
            'primary': discord.ButtonStyle.primary,
            'secondary': discord.ButtonStyle.secondary,
            'success': discord.ButtonStyle.success,
            'danger': discord.ButtonStyle.danger
        }
        
        super().__init__(
            label=button_data.label,
            style=style_map.get(button_data.style, discord.ButtonStyle.secondary),
            emoji=button_data.emoji if button_data.emoji else None,
            custom_id=f"role_btn_{button_data.id}"
        )
        self.button_data = button_data
    
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        try:
            role = interaction.guild.get_role(int(self.button_data.role_id))
            if not role:
                await interaction.followup.send("❌ Role not found!", ephemeral=True)
                return
            
            if self.button_data.role_action == 'add':
                if role in interaction.user.roles:
                    await interaction.followup.send(f"❌ You already have the {role.name} role!", ephemeral=True)
                else:
                    await interaction.user.add_roles(role)
                    await interaction.followup.send(f"✅ Added the {role.name} role!", ephemeral=True)
            else:
                if role not in interaction.user.roles:
                    await interaction.followup.send(f"❌ You don't have the {role.name} role!", ephemeral=True)
                else:
                    await interaction.user.remove_roles(role)
                    await interaction.followup.send(f"✅ Removed the {role.name} role!", ephemeral=True)
                    
        except discord.Forbidden:
            await interaction.followup.send("❌ I don't have permission to manage this role!", ephemeral=True)
        except Exception as e:
            print(f"Error managing role: {e}")
            await interaction.followup.send("❌ An error occurred while managing your role.", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self, ticket_db_id):
        super().__init__(timeout=None)
        self.ticket_db_id = ticket_db_id
    
    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = get_session(str(interaction.guild_id))
        try:
            ticket = session.query(Ticket).get(self.ticket_db_id)
            if not ticket:
                await interaction.response.send_message("❌ Ticket not found!", ephemeral=True)
                return
            
            # Check permissions
            is_creator = str(interaction.user.id) == ticket.creator_id
            is_staff = any(role.name.lower() in ['staff', 'admin', 'mod', 'support'] 
                          for role in interaction.user.roles)
            
            if not (is_creator or is_staff):
                await interaction.response.send_message("❌ You don't have permission to close this ticket!", ephemeral=True)
                return
            
            # Update ticket
            ticket.status = "closed"
            ticket.closed_at = datetime.utcnow()
            ticket.closed_by = str(interaction.user.id)
            session.commit()
            
            embed = discord.Embed(
                title="🔒 Ticket Closed",
                description=f"Ticket #{ticket.ticket_id} has been closed by {interaction.user.mention}",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            
            await interaction.response.send_message(embed=embed)
            await interaction.followup.send("This channel will be deleted in 10 seconds...", ephemeral=True)
            
            await asyncio.sleep(10)
            await interaction.channel.delete()
            
        except Exception as e:
            print(f"Error closing ticket: {e}")
            await interaction.response.send_message("❌ An error occurred while closing the ticket.", ephemeral=True)
        finally:
            session.close()

# Button Setup Modal
class ButtonSetupModal(discord.ui.Modal):
    def __init__(self, message_id, button_type):
        super().__init__(title=f"Setup {button_type.title()} Button")
        self.message_id = message_id
        self.button_type = button_type
        
        self.label = discord.ui.TextInput(
            label="Button Label",
            placeholder="Enter the text on the button...",
            required=True,
            max_length=80
        )
        self.add_item(self.label)
        
        self.emoji = discord.ui.TextInput(
            label="Button Emoji",
            placeholder="Enter an emoji (optional)...",
            required=False,
            max_length=10
        )
        self.add_item(self.emoji)
        
        self.style = discord.ui.TextInput(
            label="Button Style",
            placeholder="primary, secondary, success, or danger",
            required=False,
            default="secondary",
            max_length=20
        )
        self.add_item(self.style)
        
        if button_type == 'ticket':
            self.name_format = discord.ui.TextInput(
                label="Ticket Name Format",
                placeholder="ticket-{id} or support-{user}-{id}",
                required=True,
                default="ticket-{id}",
                max_length=50
            )
            self.add_item(self.name_format)
            
            self.description = discord.ui.TextInput(
                label="Ticket Welcome Message",
                placeholder="Message shown when ticket is created...",
                required=False,
                style=discord.TextStyle.paragraph,
                max_length=1000
            )
            self.add_item(self.description)
        else:
            self.role_info = discord.ui.TextInput(
                label="Role ID and Action",
                placeholder="role_id,add or role_id,remove",
                required=True,
                max_length=50
            )
            self.add_item(self.role_info)
    
    async def on_submit(self, interaction: discord.Interaction):
        session = get_session(str(interaction.guild_id))
        try:
            interactive_msg = session.query(InteractiveMessage).get(self.message_id)
            if not interactive_msg:
                await interaction.response.send_message("❌ Interactive message not found!", ephemeral=True)
                return
            
            button = MessageButton(
                message_id=self.message_id,
                label=self.label.value,
                emoji=self.emoji.value if self.emoji.value else None,
                style=self.style.value if self.style.value in ['primary', 'secondary', 'success', 'danger'] else 'secondary',
                button_type=self.button_type
            )
            
            if self.button_type == 'ticket':
                button.ticket_name_format = self.name_format.value
                button.ticket_description = self.description.value if self.description.value else None
                button.ticket_id_start = 1
            else:
                try:
                    role_id, action = self.role_info.value.split(',')
                    button.role_id = role_id.strip()
                    button.role_action = action.strip()
                except ValueError:
                    await interaction.response.send_message("❌ Invalid role format! Use: role_id,add or role_id,remove", ephemeral=True)
                    return
            
            session.add(button)
            session.commit()
            
            await interaction.response.send_message(f"✅ {self.button_type.title()} button added successfully! Use 'Update & Refresh' or '/editintmsg' to manage more buttons.", ephemeral=True)
            
        except Exception as e:
            print(f"Error adding button: {e}")
            await interaction.response.send_message("❌ An error occurred while adding the button.", ephemeral=True)
        finally:
            session.close()

async def setup_ticket(interaction: discord.Interaction, button_id: str):
    """Set up a new ticket"""
    try:
        # Create ticket record
        session = get_session(str(interaction.guild_id))
        try:
            ticket = Ticket(
                ticket_id=f"TICKET-{int(time.time())}",
                channel_id=str(interaction.channel_id),
                server_id=str(interaction.guild_id),
                creator_id=str(interaction.user.id),
                button_id=button_id,
                status="open"
            )
            session.add(ticket)
            session.commit()
            return ticket
        except Exception as e:
            print(f"Error creating ticket: {e}")
            session.rollback()
            raise
        finally:
            session.close()
    except Exception as e:
        print(f"Error in setup_ticket: {e}")
        return None

async def close_ticket(interaction: discord.Interaction):
    """Close a ticket"""
    try:
        session = get_session(str(interaction.guild_id))
        try:
            ticket = session.query(Ticket).filter_by(
                channel_id=str(interaction.channel_id),
                status="open"
            ).first()
            
            if not ticket:
                await interaction.response.send_message("❌ No open ticket found for this channel!", ephemeral=True)
                return
            
            # Update ticket status
            ticket.status = "closed"
            ticket.closed_at = datetime.utcnow()
            ticket.closed_by = str(interaction.user.id)
            session.commit()
            
            # Send confirmation
            embed = discord.Embed(
                title="🔒 Ticket Closed",
                description=f"This ticket has been closed by {interaction.user.mention}",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            await interaction.response.send_message(embed=embed)
            
            # Delete channel after delay
            await asyncio.sleep(10)
            await interaction.channel.delete()
            
        except Exception as e:
            print(f"Error closing ticket: {e}")
            session.rollback()
            await interaction.response.send_message("❌ An error occurred while closing the ticket.", ephemeral=True)
        finally:
            session.close()
    except Exception as e:
        print(f"Error in close_ticket: {e}")
        await interaction.response.send_message("❌ An error occurred while closing the ticket.", ephemeral=True)

# ... existing code ... 