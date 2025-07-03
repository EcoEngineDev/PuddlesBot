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
    
    # Start automatic voice scanning
    asyncio.create_task(auto_voice_scan_startup())

async def auto_voice_scan_startup():
    """Automatically scan voice channels when bot starts up and periodically"""
    # Wait for bot to be ready
    await _client.wait_until_ready()
    
    # Initial scan after bot startup
    await asyncio.sleep(5)  # Give bot time to fully initialize
    await auto_scan_voice_channels()
    
    # Set up periodic scanning (every 10 minutes)
    while not _client.is_closed():
        await asyncio.sleep(600)  # 10 minutes
        await auto_scan_voice_channels()

async def auto_scan_voice_channels():
    """Scan all voice channels across all guilds and start tracking eligible users"""
    try:
        total_tracked = 0
        guilds_scanned = 0
        
        for guild in _client.guilds:
            guild_tracked = 0
            
            for channel in guild.voice_channels:
                if len(channel.members) < 2:
                    continue  # Skip channels with less than 2 people
                    
                human_members = [m for m in channel.members if not m.bot]
                if len(human_members) < 2:
                    continue  # Need at least 2 humans
                    
                # Start tracking each human member
                for member in human_members:
                    guild_id = guild.id
                    user_id = member.id
                    
                    # Check if already being tracked
                    if guild_id in voice_tracker.voice_sessions and user_id in voice_tracker.voice_sessions[guild_id]:
                        continue  # Already tracked
                        
                    # Start tracking
                    voice_tracker.user_joined_voice(guild_id, user_id, channel)
                    guild_tracked += 1
                    total_tracked += 1
                    
            if guild_tracked > 0:
                print(f"🎙️ AUTO-SCAN: Started tracking {guild_tracked} users in {guild.name}")
                guilds_scanned += 1
                
        if total_tracked > 0:
            print(f"🎙️ AUTO-SCAN COMPLETE: Started tracking {total_tracked} users across {guilds_scanned} guilds")
        
    except Exception as e:
        print(f"❌ Error in auto voice scan: {e}")
        print(f"   Full error: {traceback.format_exc()}")

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

# ============= VOICE TRACKING =============

class VoiceTracker:
    def __init__(self):
        self.voice_sessions: Dict[int, Dict[int, datetime]] = {}  # guild_id -> {user_id: join_time}
        
    def user_joined_voice(self, guild_id: int, user_id: int, channel: discord.VoiceChannel):
        """Track when a user joins a voice channel"""
        print(f"🎙️ VOICE JOIN: User {user_id} joined {channel.name} in guild {guild_id}")
        print(f"   Channel members: {len(channel.members)} total")
        
        if guild_id not in self.voice_sessions:
            self.voice_sessions[guild_id] = {}
            
        # Only track if there are other people in the channel (anti-AFK)
        if len(channel.members) > 1:
            self.voice_sessions[guild_id][user_id] = datetime.utcnow()
            print(f"   ✅ Voice tracking started for user {user_id} - {len(channel.members)} people in channel")
        else:
            print(f"   🚫 Not tracking voice for user {user_id} - alone in channel")
            
    def user_left_voice(self, guild_id: int, user_id: int) -> Optional[int]:
        """Calculate voice time when user leaves and award XP"""
        print(f"🎙️ VOICE LEAVE: User {user_id} left voice in guild {guild_id}")
        
        if guild_id in self.voice_sessions and user_id in self.voice_sessions[guild_id]:
            join_time = self.voice_sessions[guild_id][user_id]
            duration = (datetime.utcnow() - join_time).total_seconds() / 60  # minutes
            del self.voice_sessions[guild_id][user_id]
            print(f"   Voice session duration: {duration:.1f} minutes")
            if duration >= 1:
                minutes_to_award = int(duration)
                print(f"   ✅ Awarding {minutes_to_award} minutes of voice time")
                return minutes_to_award
            else:
                print(f"   ⚠️ Session too short ({duration:.1f} min), not awarding XP")
                return None
        else:
            print(f"   🚫 User {user_id} was not being tracked in guild {guild_id}")
            print(f"   Current sessions: {list(self.voice_sessions.get(guild_id, {}).keys())}")
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
        print(f"🎙️ VOICE XP: Attempting to award {minutes} minutes to user {user_id} in guild {guild_id}")
        
        session = get_session(str(guild_id))
        try:
            # Get settings
            settings = session.query(LevelSettings).filter_by(guild_id=str(guild_id)).first()
            if not settings:
                print(f"   Creating new settings for guild {guild_id}")
                settings = LevelSettings(guild_id=str(guild_id))
                session.add(settings)
                session.flush()
                
            if not settings.voice_xp_enabled:
                print(f"   Voice XP disabled for guild {guild_id}")
                return
                
            # Calculate XP
            base_xp = minutes * settings.voice_xp_rate
            xp_to_award = int(base_xp * settings.multiplier)
            print(f"   Voice XP calculation: {minutes} min * {settings.voice_xp_rate} rate * {settings.multiplier} multiplier = {xp_to_award} XP")
            
            # Get or create user level
            user_level = session.query(UserLevel).filter_by(
                user_id=str(user_id), 
                guild_id=str(guild_id)
            ).first()
            
            if not user_level:
                print(f"   Creating new user level record for user {user_id}")
                user_level = UserLevel(
                    user_id=str(user_id),
                    guild_id=str(guild_id),
                    text_xp=0,
                    voice_xp=0,
                    text_level=0,
                    voice_level=0,
                    total_messages=0,
                    total_voice_time=0
                )
                session.add(user_level)
                session.flush()
                
            # Award XP and update stats
            old_level = user_level.voice_level
            old_xp = user_level.voice_xp
            old_voice_time = user_level.total_voice_time
            
            user_level.voice_xp += xp_to_award
            user_level.total_voice_time += minutes
            user_level.last_voice_update = datetime.utcnow()
            user_level.voice_level = calculate_level(user_level.voice_xp)
            
            print(f"   Voice XP updated: {old_xp} -> {user_level.voice_xp}")
            print(f"   Voice time updated: {old_voice_time} -> {user_level.total_voice_time} minutes")
            print(f"   Voice level updated: {old_level} -> {user_level.voice_level}")
            
            session.commit()
            
            # Check for level up
            if user_level.voice_level > old_level:
                print(f"   🎉 Voice level up! {old_level} -> {user_level.voice_level}")
                await self._handle_level_up(guild_id, user_id, old_level, user_level.voice_level, "voice")
                
            print(f"   ✅ Successfully awarded {xp_to_award} voice XP to user {user_id}")
            
        except Exception as e:
            print(f"❌ Error awarding voice XP: {e}")
            print(f"   Full error: {traceback.format_exc()}")
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
                
            session = get_session(str(guild_id))
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
    session = get_session(str(guild_id))
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
    session = get_session(str(member.guild.id))
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

# ============= EVENT HANDLERS =============

async def handle_message_xp(message: discord.Message):
    """Handle XP gain from messages"""
    if message.author.bot or not message.guild:
        return
        
    print(f"💬 MESSAGE XP: Processing message from {message.author.name} ({message.author.id}) in {message.guild.name}")
    
    session = get_session(str(message.guild.id))
    try:
        # Check permissions and cooldown
        print(f"   Step 1: Checking permissions and cooldown")
        can_get_xp = await should_give_xp(message.author, message.channel)
        can_gain_now = await can_gain_text_xp(message.author.id, message.guild.id)
        
        print(f"   Can get XP: {can_get_xp}")
        print(f"   Can gain now (cooldown): {can_gain_now}")
        
        if not can_get_xp or not can_gain_now:
            print(f"   ❌ Cannot gain XP - permissions: {can_get_xp}, cooldown: {can_gain_now}")
            return
            
        # Get or create settings
        print(f"   Step 2: Getting or creating settings")
        settings = session.query(LevelSettings).filter_by(guild_id=str(message.guild.id)).first()
        if not settings:
            print(f"   Creating new settings for guild {message.guild.id}")
            settings = LevelSettings(guild_id=str(message.guild.id))
            session.add(settings)
            session.flush()
            
        if not settings.text_xp_enabled:
            print(f"   Text XP disabled for guild {message.guild.id}")
            return
            
        # Calculate XP to award
        print(f"   Step 3: Calculating XP")
        base_xp = random.randint(settings.text_xp_min, settings.text_xp_max)
        xp_to_award = int(base_xp * settings.multiplier)
        print(f"   Base XP: {base_xp}, Multiplier: {settings.multiplier}, Final XP: {xp_to_award}")
        
        # Get or create user level
        print(f"   Step 4: Getting or creating user level")
        user_level = session.query(UserLevel).filter_by(
            user_id=str(message.author.id),
            guild_id=str(message.guild.id)
        ).first()
        
        if not user_level:
            print(f"   Creating new user level record for user {message.author.id}")
            user_level = UserLevel(
                user_id=str(message.author.id),
                guild_id=str(message.guild.id),
                text_xp=0,
                voice_xp=0,
                text_level=0,
                voice_level=0,
                total_messages=0,
                total_voice_time=0
            )
            session.add(user_level)
            session.flush()
            
        # Award XP
        print(f"   Step 5: Awarding XP")
        old_level = user_level.text_level
        old_xp = user_level.text_xp
        old_msg_count = user_level.total_messages
        
        user_level.text_xp += xp_to_award
        user_level.total_messages += 1
        user_level.last_text_xp = datetime.utcnow()
        user_level.text_level = calculate_level(user_level.text_xp)
        
        print(f"   Text XP updated: {old_xp} -> {user_level.text_xp}")
        print(f"   Message count updated: {old_msg_count} -> {user_level.total_messages}")
        print(f"   Text level updated: {old_level} -> {user_level.text_level}")
        
        session.commit()
        print(f"   ✅ Database committed successfully")
        
        # Check for level up
        if user_level.text_level > old_level:
            print(f"   🎉 Text level up! {old_level} -> {user_level.text_level}")
            # Store the channel for level up messages
            if not hasattr(_client, 'last_active_channel'):
                _client.last_active_channel = {}
            _client.last_active_channel[message.guild.id] = message.channel
            
            await voice_tracker._handle_level_up(
                message.guild.id, message.author.id, old_level, user_level.text_level, "text"
            )
            
        print(f"   ✅ Successfully awarded {xp_to_award} text XP to {message.author.name}")
        
    except Exception as e:
        print(f"❌ Error in handle_message_xp: {e}")
        print(f"   Full error: {traceback.format_exc()}")
        session.rollback()
    finally:
        session.close()

async def handle_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    """Handle voice state changes for XP tracking"""
    if member.bot:
        return
        
    guild_id = member.guild.id
    user_id = member.id
    
    # Debug voice state change
    before_channel = before.channel.name if before.channel else "None"
    after_channel = after.channel.name if after.channel else "None"
    print(f"🔄 VOICE STATE: {member.name} ({user_id}) in {member.guild.name}")
    print(f"   Before: {before_channel}")
    print(f"   After: {after_channel}")
    
    try:
        # User left voice completely
        if before.channel and not after.channel:
            print(f"   📤 User left voice completely")
            voice_time = voice_tracker.user_left_voice(guild_id, user_id)
            if voice_time:
                await voice_tracker._award_voice_xp(guild_id, user_id, voice_time)
                
        # User joined voice from being disconnected
        elif not before.channel and after.channel:
            print(f"   📥 User joined voice from disconnected")
            voice_tracker.user_joined_voice(guild_id, user_id, after.channel)
            
            # Check if this join made the channel eligible for tracking other users
            await auto_check_channel_tracking(after.channel)
            
        # User moved between channels
        elif before.channel and after.channel and before.channel != after.channel:
            print(f"   🔄 User moved between channels")
            voice_tracker.user_moved_voice(guild_id, user_id, before.channel, after.channel)
            
            # Check both channels for tracking eligibility
            await auto_check_channel_tracking(before.channel)
            await auto_check_channel_tracking(after.channel)
            
        # User stayed in same channel but something changed (mute, deafen, etc.)
        elif before.channel == after.channel and after.channel:
            channel_members = len(after.channel.members)
            print(f"   ⚡ Same channel state change - {channel_members} members in {after.channel.name}")
            
            # If user is now alone, stop tracking
            if channel_members == 1 and user_id in voice_tracker.voice_sessions.get(guild_id, {}):
                print(f"   🚫 User is now alone, stopping tracking")
                voice_time = voice_tracker.user_left_voice(guild_id, user_id)
                if voice_time:
                    await voice_tracker._award_voice_xp(guild_id, user_id, voice_time)
                    
            # If user is no longer alone, start tracking
            elif channel_members > 1 and user_id not in voice_tracker.voice_sessions.get(guild_id, {}):
                print(f"   👥 User is no longer alone, starting tracking")
                voice_tracker.user_joined_voice(guild_id, user_id, after.channel)
            else:
                print(f"   ➡️ No tracking change needed")
                
    except Exception as e:
        print(f"❌ Error in voice state handling: {e}")
        print(f"   Full error: {traceback.format_exc()}")

async def auto_check_channel_tracking(channel: discord.VoiceChannel):
    """Check a voice channel and start tracking all eligible users"""
    if not channel:
        return
        
    try:
        human_members = [m for m in channel.members if not m.bot]
        if len(human_members) < 2:
            return  # Need at least 2 humans
            
        guild_id = channel.guild.id
        newly_tracked = 0
        
        for member in human_members:
            user_id = member.id
            
            # Check if already being tracked
            if guild_id in voice_tracker.voice_sessions and user_id in voice_tracker.voice_sessions[guild_id]:
                continue  # Already tracked
                
            # Start tracking
            voice_tracker.user_joined_voice(guild_id, user_id, channel)
            newly_tracked += 1
            
        if newly_tracked > 0:
            print(f"   🔄 AUTO-CHECK: Started tracking {newly_tracked} additional users in {channel.name}")
            
    except Exception as e:
        print(f"❌ Error in auto channel check: {e}")

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
        
        session = get_session(str(interaction.guild_id))
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
        name="testvoice",
        description="Test voice XP by simulating voice time (Admin only)"
    )
    @app_commands.describe(
        user="User to test voice XP for",
        minutes="Minutes of voice time to simulate (default 5)"
    )
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def testvoice(interaction: discord.Interaction, user: discord.Member = None, minutes: int = 5):
        target_user = user or interaction.user
        
        try:
            await interaction.response.defer()
            
            # Simulate voice XP award
            await voice_tracker._award_voice_xp(interaction.guild_id, target_user.id, minutes)
            
            embed = discord.Embed(
                title="🎙️ Voice XP Test",
                description=f"Simulated **{minutes} minutes** of voice time for {target_user.mention}",
                color=discord.Color.green()
            )
            
            # Get updated user data
            session = get_session(str(interaction.guild_id))
            try:
                user_level = session.query(UserLevel).filter_by(
                    user_id=str(target_user.id),
                    guild_id=str(interaction.guild_id)
                ).first()
                
                if user_level:
                    embed.add_field(
                        name="Current Voice Stats",
                        value=f"**Voice XP:** {user_level.voice_xp:,}\n"
                              f"**Voice Level:** {user_level.voice_level}\n"
                              f"**Total Voice Time:** {user_level.total_voice_time} minutes",
                        inline=False
                    )
                    
            finally:
                session.close()
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error testing voice XP: {str(e)}",
                ephemeral=True
            )
    
    @tree.command(
        name="testxp",
        description="Test XP system by manually awarding XP (Admin only)"
    )
    @app_commands.describe(
        user="User to award test XP to",
        type="Type of XP to award",
        amount="Amount of XP to award (optional, default 25)"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Text XP", value="text"),
        app_commands.Choice(name="Voice XP", value="voice"),
    ])
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def testxp(interaction: discord.Interaction, user: discord.Member = None, type: str = "text", amount: int = 25):
        target_user = user or interaction.user
        
        session = get_session(str(interaction.guild_id))
        try:
            # Get or create settings
            settings = session.query(LevelSettings).filter_by(guild_id=str(interaction.guild_id)).first()
            if not settings:
                settings = LevelSettings(guild_id=str(interaction.guild_id))
                session.add(settings)
                session.flush()
                
            # Get or create user level
            user_level = session.query(UserLevel).filter_by(
                user_id=str(target_user.id),
                guild_id=str(interaction.guild_id)
            ).first()
            
            if not user_level:
                user_level = UserLevel(
                    user_id=str(target_user.id),
                    guild_id=str(interaction.guild_id),
                    text_xp=0,
                    voice_xp=0,
                    text_level=0,
                    voice_level=0,
                    total_messages=0,
                    total_voice_time=0
                )
                session.add(user_level)
                session.flush()
                
            # Award XP based on type
            if type == "text":
                old_level = user_level.text_level
                old_xp = user_level.text_xp
                user_level.text_xp += amount
                user_level.total_messages += 1
                user_level.last_text_xp = datetime.utcnow()
                user_level.text_level = calculate_level(user_level.text_xp)
                xp_type_name = "Text"
            else:  # voice
                old_level = user_level.voice_level
                old_xp = user_level.voice_xp
                user_level.voice_xp += amount
                user_level.total_voice_time += 1  # Add 1 minute
                user_level.last_voice_update = datetime.utcnow()
                user_level.voice_level = calculate_level(user_level.voice_xp)
                xp_type_name = "Voice"
            
            session.commit()
            
            embed = discord.Embed(
                title="🧪 XP Test",
                description=f"Awarded **{amount} {xp_type_name} XP** to {target_user.mention}",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="Results",
                value=f"**Before:** {old_xp:,} XP (Level {old_level})\n"
                      f"**After:** {old_xp + amount:,} XP (Level {calculate_level(old_xp + amount)})",
                inline=False
            )
            
            # Check for level up
            new_level = calculate_level(old_xp + amount)
            if new_level > old_level:
                embed.add_field(
                    name="🎉 Level Up!",
                    value=f"Level {old_level} → Level {new_level}",
                    inline=False
                )
                
                # Trigger level up message
                if not hasattr(_client, 'last_active_channel'):
                    _client.last_active_channel = {}
                _client.last_active_channel[interaction.guild_id] = interaction.channel
                
                await voice_tracker._handle_level_up(
                    interaction.guild_id, target_user.id, old_level, new_level, type
                )
                
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error testing XP: {str(e)}",
                ephemeral=True
            )
            session.rollback()
        finally:
            session.close()
    
    @tree.command(
        name="debugxp",
        description="Debug XP system for a user (Admin only)"
    )
    @app_commands.describe(user="User to debug")
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def debugxp(interaction: discord.Interaction, user: discord.Member = None):
        target_user = user or interaction.user
        
        session = get_session(str(interaction.guild_id))
        try:
            # Check various conditions
            can_get_xp = await should_give_xp(target_user, interaction.channel)
            can_gain_now = await can_gain_text_xp(target_user.id, interaction.guild_id)
            
            # Get settings
            settings = session.query(LevelSettings).filter_by(guild_id=str(interaction.guild_id)).first()
            
            # Get user level
            user_level = session.query(UserLevel).filter_by(
                user_id=str(target_user.id),
                guild_id=str(interaction.guild_id)
            ).first()
            
            embed = discord.Embed(
                title="🔍 XP System Debug",
                description=f"Debug info for {target_user.mention}",
                color=discord.Color.blue()
            )
            
            # Basic checks
            embed.add_field(
                name="🚦 Basic Checks",
                value=f"**Is bot:** {target_user.bot}\n"
                      f"**Can get XP:** {can_get_xp}\n"
                      f"**Can gain now (cooldown):** {can_gain_now}",
                inline=True
            )
            
            # Settings info
            if settings:
                embed.add_field(
                    name="⚙️ Server Settings",
                    value=f"**Text XP enabled:** {settings.text_xp_enabled}\n"
                          f"**Voice XP enabled:** {settings.voice_xp_enabled}\n"
                          f"**XP range:** {settings.text_xp_min}-{settings.text_xp_max}\n"
                          f"**Voice rate:** {settings.voice_xp_rate}/min\n"
                          f"**Cooldown:** {settings.text_cooldown}s\n"
                          f"**Multiplier:** {settings.multiplier}x",
                    inline=True
                )
            else:
                embed.add_field(
                    name="⚙️ Server Settings",
                    value="No settings found (will use defaults)",
                    inline=True
                )
            
            # User data
            if user_level:
                last_text_time = user_level.last_text_xp
                last_voice_time = user_level.last_voice_update
                text_time_since = "Never" if not last_text_time else f"{int((datetime.utcnow() - last_text_time).total_seconds())}s ago"
                voice_time_since = "Never" if not last_voice_time else f"{int((datetime.utcnow() - last_voice_time).total_seconds())}s ago"
                
                embed.add_field(
                    name="👤 User Data",
                    value=f"**Text XP:** {user_level.text_xp:,} (Level {user_level.text_level})\n"
                          f"**Voice XP:** {user_level.voice_xp:,} (Level {user_level.voice_level})\n"
                          f"**Messages:** {user_level.total_messages:,}\n"
                          f"**Voice Time:** {user_level.total_voice_time:,} min\n"
                          f"**Last Text XP:** {text_time_since}\n"
                          f"**Last Voice XP:** {voice_time_since}",
                    inline=False
                )
            else:
                embed.add_field(
                    name="👤 User Data",
                    value="No user data found (new user)",
                    inline=False
                )
                
            # Voice tracking status
            guild_sessions = voice_tracker.voice_sessions.get(interaction.guild_id, {})
            if target_user.id in guild_sessions:
                start_time = guild_sessions[target_user.id]
                duration = (datetime.utcnow() - start_time).total_seconds() / 60
                voice_status = f"✅ Currently tracked ({duration:.1f} min)"
            else:
                voice_status = "❌ Not currently tracked"
                
            voice_channel_info = "Not in voice"
            if hasattr(target_user, 'voice') and target_user.voice and target_user.voice.channel:
                channel = target_user.voice.channel
                voice_channel_info = f"In {channel.name} ({len(channel.members)} members)"
                
            embed.add_field(
                name="🎙️ Voice Status",
                value=f"**Tracking:** {voice_status}\n"
                      f"**Channel:** {voice_channel_info}\n"
                      f"**Total tracked:** {len(guild_sessions)} users",
                inline=False
            )
            
            # Overall status
            overall_status = "✅ Ready to gain XP" if (can_get_xp and can_gain_now and not target_user.bot) else "❌ Cannot gain XP"
            embed.add_field(
                name="📊 Overall Status",
                value=overall_status,
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error debugging XP: {str(e)}",
                ephemeral=True
            )
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
        app_commands.Choice(name="Voice XP Enabled", value="voice_xp_enabled"),
        app_commands.Choice(name="Voice XP Rate", value="voice_xp_rate"),
        app_commands.Choice(name="XP Multiplier", value="multiplier"),
    ])
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def lvlconfig(interaction: discord.Interaction, setting: str, value: Optional[str] = None):
        session = get_session(str(interaction.guild_id))
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
                    name="🎙️ Voice XP Settings",
                    value=f"**Voice XP enabled:** {'✅' if settings.voice_xp_enabled else '❌'}\n"
                          f"**XP per minute:** {settings.voice_xp_rate}",
                    inline=True
                )
                
                embed.add_field(
                    name="⚡ General Settings",
                    value=f"**XP Multiplier:** {settings.multiplier}x",
                    inline=True
                )
                
                await interaction.response.send_message(embed=embed)
                return
            
            # Update setting
            try:
                if setting == "voice_xp_enabled":
                    new_val = value.lower() in ('true', '1', 'yes', 'on', 'enable', 'enabled')
                    settings.voice_xp_enabled = new_val
                    desc = f"Voice XP {'enabled' if new_val else 'disabled'}"
                    
                elif setting == "voice_xp_rate":
                    new_val = int(value)
                    if new_val < 1 or new_val > 50:
                        raise ValueError("Must be between 1 and 50")
                    settings.voice_xp_rate = new_val
                    desc = f"Voice XP rate set to {new_val} per minute"
                    
                elif setting == "multiplier":
                    new_val = float(value)
                    if new_val < 0.1 or new_val > 5.0:
                        raise ValueError("Must be between 0.1 and 5.0")
                    settings.multiplier = new_val
                    desc = f"XP multiplier set to {new_val}x"
                    
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

    @tree.command(
        name="voicescan",
        description="Manually scan voice channels (automatic scanning runs every 10 min)"
    )
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def voicescan(interaction: discord.Interaction):
        await interaction.response.defer()
        
        tracked_count = 0
        channel_info = []
        
        try:
            # Scan all voice channels in the guild
            for channel in interaction.guild.voice_channels:
                if len(channel.members) < 2:
                    continue  # Skip channels with less than 2 people
                    
                human_members = [m for m in channel.members if not m.bot]
                if len(human_members) < 2:
                    continue  # Need at least 2 humans
                    
                channel_info.append(f"**{channel.name}:** {len(human_members)} users")
                
                # Start tracking each human member
                for member in human_members:
                    guild_id = interaction.guild_id
                    user_id = member.id
                    
                    # Check if already being tracked
                    if guild_id in voice_tracker.voice_sessions and user_id in voice_tracker.voice_sessions[guild_id]:
                        continue  # Already tracked
                        
                    # Start tracking
                    voice_tracker.user_joined_voice(guild_id, user_id, channel)
                    tracked_count += 1
                    
            embed = discord.Embed(
                title="🎙️ Voice Channel Scan Complete",
                description=f"Started tracking **{tracked_count}** users",
                color=discord.Color.green()
            )
            
            if channel_info:
                embed.add_field(
                    name="📊 Active Voice Channels",
                    value="\n".join(channel_info),
                    inline=False
                )
            else:
                embed.add_field(
                    name="📊 Status",
                    value="No eligible voice channels found (need 2+ humans)",
                    inline=False
                )
                
            # Show current tracking status
            guild_sessions = voice_tracker.voice_sessions.get(interaction.guild_id, {})
            embed.add_field(
                name="🔍 Current Tracking",
                value=f"Total users being tracked: **{len(guild_sessions)}**",
                inline=False
            )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error scanning voice channels: {str(e)}",
                ephemeral=True
            )

# Export the setup functions
__all__ = ['setup_leveling_system', 'setup_level_commands', 'handle_message_xp', 'handle_voice_state_update'] 