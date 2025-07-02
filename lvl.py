import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta
from database import get_session, Base, UserLevel, LevelSettings, LevelRewards
import asyncio
import random
import math
import time
from typing import Optional, Dict, List, Tuple
import functools
import traceback

# Store reference to the client
_client = None

def setup_leveling_system(client):
    """Initialize the leveling system with client reference"""
    global _client
    _client = client

def log_command(func):
    @functools.wraps(func)
    async def wrapper(interaction: discord.Interaction, *args, **kwargs):
        try:
            print(f"Executing leveling command: {func.__name__}")
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

# ============= DATABASE MODELS =============
# Database models are imported from database.py

# ============= VOICE TRACKING =============

class VoiceTracker:
    def __init__(self):
        self.voice_sessions: Dict[int, Dict[int, datetime]] = {}  # guild_id -> {user_id: join_time}
        
    def user_joined_voice(self, guild_id: int, user_id: int, channel: discord.VoiceChannel):
        """Track when a user joins a voice channel"""
        if guild_id not in self.voice_sessions:
            self.voice_sessions[guild_id] = {}
            
        # Only track if there are other people in the channel (anti-AFK)
        if len(channel.members) > 1:
            self.voice_sessions[guild_id][user_id] = datetime.utcnow()
            print(f"👥 Voice tracking started for {user_id} in guild {guild_id}")
        else:
            print(f"🚫 Not tracking voice for {user_id} - alone in channel")
            
    def user_left_voice(self, guild_id: int, user_id: int) -> Optional[int]:
        """Calculate voice time when user leaves and award XP"""
        if guild_id in self.voice_sessions and user_id in self.voice_sessions[guild_id]:
            join_time = self.voice_sessions[guild_id][user_id]
            duration = (datetime.utcnow() - join_time).total_seconds() / 60  # minutes
            del self.voice_sessions[guild_id][user_id]
            print(f"🎙️ Voice session ended for {user_id}: {duration:.1f} minutes")
            return max(1, int(duration))  # At least 1 minute
        return None
        
    def user_moved_voice(self, guild_id: int, user_id: int, old_channel: Optional[discord.VoiceChannel], new_channel: Optional[discord.VoiceChannel]):
        """Handle when user moves between voice channels"""
        if old_channel:
            # Award XP for time in old channel
            voice_time = self.user_left_voice(guild_id, user_id)
            if voice_time:
                asyncio.create_task(self._award_voice_xp(guild_id, user_id, voice_time))
                
        if new_channel:
            # Start tracking in new channel
            self.user_joined_voice(guild_id, user_id, new_channel)
            
    async def _award_voice_xp(self, guild_id: int, user_id: int, minutes: int):
        """Award voice XP for time spent in voice"""
        session = get_session()
        try:
            # Get settings
            settings = session.query(LevelSettings).filter_by(guild_id=str(guild_id)).first()
            if not settings or not settings.voice_xp_enabled:
                return
                
            # Calculate XP
            base_xp = minutes * settings.voice_xp_rate
            xp_to_award = int(base_xp * settings.multiplier)
            
            # Get or create user level
            user_level = session.query(UserLevel).filter_by(
                user_id=str(user_id), 
                guild_id=str(guild_id)
            ).first()
            
            if not user_level:
                user_level = UserLevel(
                    user_id=str(user_id),
                    guild_id=str(guild_id)
                )
                session.add(user_level)
                
            # Award XP and update stats
            old_level = user_level.voice_level
            user_level.voice_xp += xp_to_award
            user_level.total_voice_time += minutes
            user_level.last_voice_update = datetime.utcnow()
            user_level.voice_level = calculate_level(user_level.voice_xp)
            
            session.commit()
            
            # Check for level up
            if user_level.voice_level > old_level:
                await self._handle_level_up(guild_id, user_id, old_level, user_level.voice_level, "voice")
                
            print(f"🎙️ Awarded {xp_to_award} voice XP to {user_id} (Level {user_level.voice_level})")
            
        except Exception as e:
            print(f"Error awarding voice XP: {e}")
            session.rollback()
        finally:
            session.close()
            
    async def _handle_level_up(self, guild_id: int, user_id: int, old_level: int, new_level: int, xp_type: str):
        """Handle level up notifications and rewards"""
        try:
            guild = _client.get_guild(guild_id)
            if not guild:
                return
                
            user = guild.get_member(user_id)
            if not user:
                return
                
            session = get_session()
            try:
                settings = session.query(LevelSettings).filter_by(guild_id=str(guild_id)).first()
                
                # Send level up message
                if settings and settings.level_up_messages:
                    embed = discord.Embed(
                        title="🎉 Level Up!",
                        description=f"{user.mention} reached **{xp_type.title()} Level {new_level}**!",
                        color=discord.Color.gold()
                    )
                    embed.set_thumbnail(url=user.display_avatar.url)
                    
                    channel = None
                    if settings.level_up_channel:
                        channel = guild.get_channel(int(settings.level_up_channel))
                    
                    if not channel and hasattr(_client, 'last_active_channel'):
                        channel = _client.last_active_channel.get(guild_id)
                        
                    if channel:
                        await channel.send(embed=embed)
                        
                # Check for role rewards
                rewards = session.query(LevelRewards).filter_by(guild_id=str(guild_id)).all()
                for reward in rewards:
                    should_give_role = False
                    
                    if reward.text_level > 0 and reward.voice_level > 0:
                        # Both required
                        user_data = session.query(UserLevel).filter_by(
                            user_id=str(user_id), guild_id=str(guild_id)
                        ).first()
                        if user_data and user_data.text_level >= reward.text_level and user_data.voice_level >= reward.voice_level:
                            should_give_role = True
                    elif reward.text_level > 0 and xp_type == "text" and new_level >= reward.text_level:
                        should_give_role = True
                    elif reward.voice_level > 0 and xp_type == "voice" and new_level >= reward.voice_level:
                        should_give_role = True
                        
                    if should_give_role:
                        role = guild.get_role(int(reward.role_id))
                        if role and role not in user.roles:
                            await user.add_roles(role, reason=f"Level reward: {xp_type} level {new_level}")
                            print(f"🏆 Gave role {role.name} to {user.name} for reaching level {new_level}")
                            
                            if reward.dm_user:
                                try:
                                    dm_embed = discord.Embed(
                                        title="🏆 Level Reward!",
                                        description=f"You've been awarded the **{role.name}** role in **{guild.name}** for reaching {xp_type} level {new_level}!",
                                        color=discord.Color.gold()
                                    )
                                    await user.send(embed=dm_embed)
                                except discord.Forbidden:
                                    pass
                                    
            finally:
                session.close()
                
        except Exception as e:
            print(f"Error handling level up: {e}")

# Global voice tracker instance
voice_tracker = VoiceTracker()

# ============= UTILITY FUNCTIONS =============

def calculate_level(xp: int) -> int:
    """Calculate level from XP using ProBot-like formula"""
    # Formula: Level = floor(sqrt(XP / 100))
    # This means: Level 1 = 100 XP, Level 2 = 400 XP, Level 3 = 900 XP, etc.
    if xp < 100:
        return 0
    return int(math.sqrt(xp / 100))

def calculate_xp_for_level(level: int) -> int:
    """Calculate XP required for a specific level"""
    if level <= 0:
        return 0
    return (level ** 2) * 100

def calculate_xp_for_next_level(current_xp: int) -> Tuple[int, int, int]:
    """Returns (current_level, xp_for_next_level, xp_needed)"""
    current_level = calculate_level(current_xp)
    next_level = current_level + 1
    xp_for_next = calculate_xp_for_level(next_level)
    xp_needed = xp_for_next - current_xp
    return current_level, xp_for_next, xp_needed

def create_progress_bar(current: int, maximum: int, length: int = 20) -> str:
    """Create a text progress bar"""
    if maximum == 0:
        return "▓" * length
        
    filled = int((current / maximum) * length)
    bar = "▓" * filled + "░" * (length - filled)
    return bar

async def can_gain_text_xp(user_id: int, guild_id: int) -> bool:
    """Check if user can gain text XP (anti-spam)"""
    session = get_session()
    try:
        user_level = session.query(UserLevel).filter_by(
            user_id=str(user_id), 
            guild_id=str(guild_id)
        ).first()
        
        if not user_level or not user_level.last_text_xp:
            return True
            
        settings = session.query(LevelSettings).filter_by(guild_id=str(guild_id)).first()
        cooldown = settings.text_cooldown if settings else 60
        
        time_since_last = (datetime.utcnow() - user_level.last_text_xp).total_seconds()
        return time_since_last >= cooldown
        
    finally:
        session.close()

async def should_give_xp(member: discord.Member, channel: discord.TextChannel) -> bool:
    """Check if user should receive XP based on settings"""
    session = get_session()
    try:
        settings = session.query(LevelSettings).filter_by(guild_id=str(member.guild.id)).first()
        if not settings:
            return True
            
        # Check no XP roles
        if settings.no_xp_roles:
            no_xp_role_ids = [rid.strip() for rid in settings.no_xp_roles.split(",") if rid.strip()]
            user_role_ids = [str(role.id) for role in member.roles]
            if any(role_id in user_role_ids for role_id in no_xp_role_ids):
                return False
                
        # Check no XP channels
        if settings.no_xp_channels:
            no_xp_channel_ids = [cid.strip() for cid in settings.no_xp_channels.split(",") if cid.strip()]
            if str(channel.id) in no_xp_channel_ids:
                return False
                
        return True
        
    finally:
        session.close()

# ============= MAIN LEVELING LOGIC =============

async def handle_message_xp(message: discord.Message):
    """Handle XP gain from messages"""
    if message.author.bot or not message.guild:
        return
        
    # Check if user should get XP
    if not await should_give_xp(message.author, message.channel):
        return
        
    # Check cooldown
    if not await can_gain_text_xp(message.author.id, message.guild.id):
        return
        
    session = get_session()
    try:
        # Get settings
        settings = session.query(LevelSettings).filter_by(guild_id=str(message.guild.id)).first()
        if not settings:
            settings = LevelSettings(guild_id=str(message.guild.id))
            session.add(settings)
            session.commit()
            
        if not settings.text_xp_enabled:
            return
            
        # Calculate XP
        base_xp = random.randint(settings.text_xp_min, settings.text_xp_max)
        xp_to_award = int(base_xp * settings.multiplier)
        
        # Get or create user level
        user_level = session.query(UserLevel).filter_by(
            user_id=str(message.author.id), 
            guild_id=str(message.guild.id)
        ).first()
        
        if not user_level:
            user_level = UserLevel(
                user_id=str(message.author.id),
                guild_id=str(message.guild.id)
            )
            session.add(user_level)
            
        # Award XP and update stats
        old_level = user_level.text_level
        user_level.text_xp += xp_to_award
        user_level.total_messages += 1
        user_level.last_text_xp = datetime.utcnow()
        user_level.text_level = calculate_level(user_level.text_xp)
        
        session.commit()
        
        # Check for level up
        if user_level.text_level > old_level:
            # Store last active channel for level up messages
            if not hasattr(_client, 'last_active_channel'):
                _client.last_active_channel = {}
            _client.last_active_channel[message.guild.id] = message.channel
            
            await voice_tracker._handle_level_up(
                message.guild.id, message.author.id, old_level, user_level.text_level, "text"
            )
            
    except Exception as e:
        print(f"Error handling message XP: {e}")
        session.rollback()
    finally:
        session.close()

# ============= VOICE STATE HANDLERS =============

async def handle_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Handle voice state changes for XP tracking"""
    if member.bot:
        return
        
    guild_id = member.guild.id
    user_id = member.id
    
    # User left voice
    if before.channel and not after.channel:
        voice_time = voice_tracker.user_left_voice(guild_id, user_id)
        if voice_time:
            await voice_tracker._award_voice_xp(guild_id, user_id, voice_time)
            
    # User joined voice
    elif not before.channel and after.channel:
        voice_tracker.user_joined_voice(guild_id, user_id, after.channel)
        
    # User moved channels
    elif before.channel != after.channel:
        voice_tracker.user_moved_voice(guild_id, user_id, before.channel, after.channel)
        
    # User became alone or no longer alone
    elif before.channel == after.channel and after.channel:
        channel_members = len(after.channel.members)
        
        # If user is now alone, stop tracking
        if channel_members == 1 and user_id in voice_tracker.voice_sessions.get(guild_id, {}):
            voice_time = voice_tracker.user_left_voice(guild_id, user_id)
            if voice_time:
                await voice_tracker._award_voice_xp(guild_id, user_id, voice_time)
                
        # If user is no longer alone, start tracking
        elif channel_members > 1 and user_id not in voice_tracker.voice_sessions.get(guild_id, {}):
            voice_tracker.user_joined_voice(guild_id, user_id, after.channel)

# ============= COMMAND SETUP =============

def setup_level_commands(tree: app_commands.CommandTree):
    """Setup leveling system commands"""
    
    @tree.command(
        name="rank",
        description="View your rank card or someone else's in the server"
    )
    @app_commands.describe(user="The user to view (optional)")
    @log_command
    async def rank(interaction: discord.Interaction, user: Optional[discord.Member] = None):
        target_user = user or interaction.user
        
        session = get_session()
        try:
            user_level = session.query(UserLevel).filter_by(
                user_id=str(target_user.id),
                guild_id=str(interaction.guild_id)
            ).first()
            
            if not user_level:
                if target_user == interaction.user:
                    await interaction.response.send_message(
                        "You haven't earned any XP yet! Start chatting to gain levels! 💬",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        f"{target_user.display_name} hasn't earned any XP yet!",
                        ephemeral=True
                    )
                return
                
            # Calculate progress for next levels
            text_level, text_next_xp, text_needed = calculate_xp_for_next_level(user_level.text_xp)
            voice_level, voice_next_xp, voice_needed = calculate_xp_for_next_level(user_level.voice_xp)
            
            # Calculate server rank
            all_users = session.query(UserLevel).filter_by(guild_id=str(interaction.guild_id)).all()
            sorted_users = sorted(all_users, key=lambda x: x.text_xp + x.voice_xp, reverse=True)
            rank = next((i + 1 for i, u in enumerate(sorted_users) if u.user_id == str(target_user.id)), 0)
            
            # Create beautiful rank card embed
            embed = discord.Embed(
                title=f"📊 {target_user.display_name}'s Rank Card",
                color=discord.Color.from_rgb(114, 137, 218)
            )
            embed.set_thumbnail(url=target_user.display_avatar.url)
            
            # Server rank and total XP
            total_xp = user_level.text_xp + user_level.voice_xp
            embed.add_field(
                name="🏆 Server Rank",
                value=f"**#{rank}** out of {len(all_users)} users",
                inline=True
            )
            embed.add_field(
                name="⭐ Total XP",
                value=f"**{total_xp:,}** XP",
                inline=True
            )
            embed.add_field(
                name="📈 Activity",
                value=f"**{user_level.total_messages:,}** messages\n**{user_level.total_voice_time:,}** min voice",
                inline=True
            )
            
            # Text level progress
            text_current_level_xp = calculate_xp_for_level(text_level)
            text_progress_xp = user_level.text_xp - text_current_level_xp
            text_level_xp_needed = text_next_xp - text_current_level_xp
            text_progress_bar = create_progress_bar(text_progress_xp, text_level_xp_needed, 15)
            
            embed.add_field(
                name="💬 Text Level",
                value=f"**Level {text_level}**\n"
                      f"`{text_progress_bar}` {text_progress_xp}/{text_level_xp_needed}\n"
                      f"*{text_needed:,} XP to level {text_level + 1}*",
                inline=True
            )
            
            # Voice level progress
            voice_current_level_xp = calculate_xp_for_level(voice_level)
            voice_progress_xp = user_level.voice_xp - voice_current_level_xp
            voice_level_xp_needed = voice_next_xp - voice_current_level_xp
            voice_progress_bar = create_progress_bar(voice_progress_xp, voice_level_xp_needed, 15)
            
            embed.add_field(
                name="🎙️ Voice Level", 
                value=f"**Level {voice_level}**\n"
                      f"`{voice_progress_bar}` {voice_progress_xp}/{voice_level_xp_needed}\n"
                      f"*{voice_needed:,} XP to level {voice_level + 1}*",
                inline=True
            )
            
            # Progress visualization
            embed.add_field(
                name="📊 XP Breakdown",
                value=f"💬 Text: **{user_level.text_xp:,}** XP\n"
                      f"🎙️ Voice: **{user_level.voice_xp:,}** XP",
                inline=True
            )
            
            embed.set_footer(text=f"Keep chatting and joining voice channels to level up! • {interaction.guild.name}")
            
            await interaction.response.send_message(embed=embed)
            
        finally:
            session.close()
    
    @tree.command(
        name="top",
        description="Display the top members by text, voice, or total XP"
    )
    @app_commands.describe(
        type="Type of leaderboard to show",
        timeframe="Timeframe for the leaderboard (future feature)"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Total XP", value="total"),
        app_commands.Choice(name="Text XP", value="text"),
        app_commands.Choice(name="Voice XP", value="voice"),
    ])
    @log_command
    async def top(interaction: discord.Interaction, type: str = "total", timeframe: Optional[str] = None):
        session = get_session()
        try:
            users = session.query(UserLevel).filter_by(guild_id=str(interaction.guild_id)).all()
            
            if not users:
                await interaction.response.send_message(
                    "No users have earned XP yet! Be the first to start chatting! 🎉",
                    ephemeral=True
                )
                return
                
            # Sort users based on type
            if type == "text":
                sorted_users = sorted(users, key=lambda x: x.text_xp, reverse=True)
                title = "💬 Top Text Levels"
                xp_attr = "text_xp"
                level_attr = "text_level"
            elif type == "voice":
                sorted_users = sorted(users, key=lambda x: x.voice_xp, reverse=True)
                title = "🎙️ Top Voice Levels"
                xp_attr = "voice_xp"
                level_attr = "voice_level"
            else:
                sorted_users = sorted(users, key=lambda x: x.text_xp + x.voice_xp, reverse=True)
                title = "🏆 Top Users (Total XP)"
                xp_attr = None
                level_attr = None
                
            # Take top 10
            top_users = sorted_users[:10]
            
            embed = discord.Embed(
                title=title,
                description=f"Top users in **{interaction.guild.name}**",
                color=discord.Color.gold()
            )
            
            leaderboard_text = ""
            for i, user_data in enumerate(top_users, 1):
                try:
                    member = interaction.guild.get_member(int(user_data.user_id))
                    if not member:
                        continue
                        
                    # Medal emojis for top 3
                    medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
                    
                    if xp_attr:
                        xp = getattr(user_data, xp_attr)
                        level = getattr(user_data, level_attr)
                        leaderboard_text += f"{medal} **{member.display_name}** - Level {level} ({xp:,} XP)\n"
                    else:
                        total_xp = user_data.text_xp + user_data.voice_xp
                        total_level = max(user_data.text_level, user_data.voice_level)
                        leaderboard_text += f"{medal} **{member.display_name}** - Level {total_level} ({total_xp:,} XP)\n"
                        
                except Exception as e:
                    print(f"Error processing user {user_data.user_id}: {e}")
                    continue
                    
            if not leaderboard_text:
                leaderboard_text = "No active users found!"
                
            embed.description = leaderboard_text
            embed.set_footer(text="Keep being active to climb the leaderboard! 🚀")
            
            await interaction.response.send_message(embed=embed)
            
        finally:
            session.close()

    # Admin commands for XP management
    @tree.command(
        name="setxp",
        description="Set a user's XP (Admin only)"
    )
    @app_commands.describe(
        user="User to modify",
        type="Type of XP to set",
        amount="Amount of XP to set"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Text XP", value="text"),
        app_commands.Choice(name="Voice XP", value="voice"),
    ])
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def setxp(interaction: discord.Interaction, user: discord.Member, type: str, amount: int):
        if amount < 0:
            await interaction.response.send_message("XP amount must be positive!", ephemeral=True)
            return
            
        session = get_session()
        try:
            user_level = session.query(UserLevel).filter_by(
                user_id=str(user.id),
                guild_id=str(interaction.guild_id)
            ).first()
            
            if not user_level:
                user_level = UserLevel(
                    user_id=str(user.id),
                    guild_id=str(interaction.guild_id)
                )
                session.add(user_level)
                
            if type == "text":
                user_level.text_xp = amount
                user_level.text_level = calculate_level(amount)
                xp_type_name = "Text"
            else:
                user_level.voice_xp = amount
                user_level.voice_level = calculate_level(amount)
                xp_type_name = "Voice"
                
            session.commit()
            
            embed = discord.Embed(
                title="✅ XP Updated",
                description=f"Set {user.mention}'s {xp_type_name} XP to **{amount:,}** (Level {calculate_level(amount)})",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed)
            
        finally:
            session.close()
            
    @tree.command(
        name="setlevel",
        description="Set a user's level (Admin only)"
    )
    @app_commands.describe(
        user="User to modify",
        type="Type of level to set",
        level="Level to set"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Text Level", value="text"),
        app_commands.Choice(name="Voice Level", value="voice"),
    ])
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def setlevel(interaction: discord.Interaction, user: discord.Member, type: str, level: int):
        if level < 0 or level > 100:
            await interaction.response.send_message("Level must be between 0 and 100!", ephemeral=True)
            return
            
        xp_amount = calculate_xp_for_level(level)
        
        session = get_session()
        try:
            user_level = session.query(UserLevel).filter_by(
                user_id=str(user.id),
                guild_id=str(interaction.guild_id)
            ).first()
            
            if not user_level:
                user_level = UserLevel(
                    user_id=str(user.id),
                    guild_id=str(interaction.guild_id)
                )
                session.add(user_level)
                
            if type == "text":
                user_level.text_xp = xp_amount
                user_level.text_level = level
                xp_type_name = "Text"
            else:
                user_level.voice_xp = xp_amount
                user_level.voice_level = level
                xp_type_name = "Voice"
                
            session.commit()
            
            embed = discord.Embed(
                title="✅ Level Updated",
                description=f"Set {user.mention}'s {xp_type_name} Level to **{level}** ({xp_amount:,} XP)",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed)
            
        finally:
            session.close()

    # Additional admin commands for leveling management
    @tree.command(
        name="lvlreset",
        description="Reset a user's levels and XP (Admin only)"
    )
    @app_commands.describe(
        user="User to reset",
        type="Type of data to reset"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="All XP & Levels", value="all"),
        app_commands.Choice(name="Text XP Only", value="text"),
        app_commands.Choice(name="Voice XP Only", value="voice"),
    ])
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def lvlreset(interaction: discord.Interaction, user: discord.Member, type: str = "all"):
        session = get_session()
        try:
            user_level = session.query(UserLevel).filter_by(
                user_id=str(user.id),
                guild_id=str(interaction.guild_id)
            ).first()
            
            if not user_level:
                await interaction.response.send_message(
                    f"{user.display_name} has no leveling data to reset!",
                    ephemeral=True
                )
                return
                
            if type == "all":
                user_level.text_xp = 0
                user_level.voice_xp = 0
                user_level.text_level = 0
                user_level.voice_level = 0
                user_level.total_messages = 0
                user_level.total_voice_time = 0
                reset_desc = "all XP and levels"
            elif type == "text":
                user_level.text_xp = 0
                user_level.text_level = 0
                user_level.total_messages = 0
                reset_desc = "text XP and level"
            else:  # voice
                user_level.voice_xp = 0
                user_level.voice_level = 0
                user_level.total_voice_time = 0
                reset_desc = "voice XP and level"
                
            session.commit()
            
            embed = discord.Embed(
                title="🔄 Level Data Reset",
                description=f"Reset {user.mention}'s {reset_desc}",
                color=discord.Color.orange()
            )
            
            await interaction.response.send_message(embed=embed)
            
        finally:
            session.close()
    
    @tree.command(
        name="lvlconfig",
        description="Configure server leveling settings (Admin only)"
    )
    @app_commands.describe(
        setting="Setting to view or configure",
        value="New value for the setting (leave empty to view current)"
    )
    @app_commands.choices(setting=[
        app_commands.Choice(name="View All Settings", value="view"),
        app_commands.Choice(name="Text XP Min", value="text_xp_min"),
        app_commands.Choice(name="Text XP Max", value="text_xp_max"),
        app_commands.Choice(name="Voice XP Rate", value="voice_xp_rate"),
        app_commands.Choice(name="Text Cooldown", value="text_cooldown"),
        app_commands.Choice(name="XP Multiplier", value="multiplier"),
        app_commands.Choice(name="Level Up Messages", value="level_up_messages"),
    ])
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def lvlconfig(interaction: discord.Interaction, setting: str, value: Optional[str] = None):
        session = get_session()
        try:
            # Get or create settings
            settings = session.query(LevelSettings).filter_by(guild_id=str(interaction.guild_id)).first()
            if not settings:
                settings = LevelSettings(guild_id=str(interaction.guild_id))
                session.add(settings)
                session.commit()
            
            if setting == "view" or value is None:
                # Show current settings
                embed = discord.Embed(
                    title="⚙️ Leveling System Configuration",
                    description=f"Settings for **{interaction.guild.name}**",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="📝 Text XP Settings",
                    value=f"**Min XP per message:** {settings.text_xp_min}\n"
                          f"**Max XP per message:** {settings.text_xp_max}\n"
                          f"**Cooldown:** {settings.text_cooldown} seconds",
                    inline=True
                )
                
                embed.add_field(
                    name="🎙️ Voice XP Settings",
                    value=f"**XP per minute:** {settings.voice_xp_rate}\n"
                          f"**Voice XP enabled:** {'✅' if settings.voice_xp_enabled else '❌'}",
                    inline=True
                )
                
                embed.add_field(
                    name="⚡ General Settings",
                    value=f"**XP Multiplier:** {settings.multiplier}x\n"
                          f"**Level up messages:** {'✅' if settings.level_up_messages else '❌'}\n"
                          f"**Text XP enabled:** {'✅' if settings.text_xp_enabled else '❌'}",
                    inline=True
                )
                
                await interaction.response.send_message(embed=embed)
                return
            
            # Update setting
            try:
                if setting == "text_xp_min":
                    new_val = int(value)
                    if new_val < 1 or new_val > 100:
                        raise ValueError("Must be between 1 and 100")
                    settings.text_xp_min = new_val
                    desc = f"Text XP minimum set to {new_val}"
                    
                elif setting == "text_xp_max":
                    new_val = int(value)
                    if new_val < 1 or new_val > 100:
                        raise ValueError("Must be between 1 and 100")
                    settings.text_xp_max = new_val
                    desc = f"Text XP maximum set to {new_val}"
                    
                elif setting == "voice_xp_rate":
                    new_val = int(value)
                    if new_val < 1 or new_val > 50:
                        raise ValueError("Must be between 1 and 50")
                    settings.voice_xp_rate = new_val
                    desc = f"Voice XP rate set to {new_val} per minute"
                    
                elif setting == "text_cooldown":
                    new_val = int(value)
                    if new_val < 30 or new_val > 300:
                        raise ValueError("Must be between 30 and 300 seconds")
                    settings.text_cooldown = new_val
                    desc = f"Text XP cooldown set to {new_val} seconds"
                    
                elif setting == "multiplier":
                    new_val = float(value)
                    if new_val < 0.1 or new_val > 5.0:
                        raise ValueError("Must be between 0.1 and 5.0")
                    settings.multiplier = new_val
                    desc = f"XP multiplier set to {new_val}x"
                    
                elif setting == "level_up_messages":
                    new_val = value.lower() in ('true', '1', 'yes', 'on', 'enable', 'enabled')
                    settings.level_up_messages = new_val
                    desc = f"Level up messages {'enabled' if new_val else 'disabled'}"
                    
                else:
                    await interaction.response.send_message("Invalid setting!", ephemeral=True)
                    return
                    
                session.commit()
                
                embed = discord.Embed(
                    title="✅ Setting Updated",
                    description=desc,
                    color=discord.Color.green()
                )
                
                await interaction.response.send_message(embed=embed)
                
            except ValueError as e:
                await interaction.response.send_message(
                    f"❌ Invalid value: {str(e)}",
                    ephemeral=True
                )
                
        except Exception as e:
            print(f"Error in lvlconfig: {e}")
            await interaction.response.send_message(
                "An error occurred while updating settings.",
                ephemeral=True
            )
        finally:
            session.close()

# Export the setup functions
__all__ = ['setup_leveling_system', 'setup_level_commands', 'handle_message_xp', 'handle_voice_state_update'] 