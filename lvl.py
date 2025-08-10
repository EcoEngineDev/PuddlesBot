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
                import language
                user_lang = language.get_server_language(interaction.guild_id)
                await interaction.response.send_message(
                    language.get_text("error_general", user_lang, error=str(e)),
                    ephemeral=True
                )
    return wrapper

# ============= VOICE TRACKING =============

def should_get_voice_xp(member: discord.Member, channel: discord.VoiceChannel) -> bool:
    """
    Check if a user should get voice XP based on various conditions:
    - Not alone in the channel
    - Not deafened
    - At least 2 real people (not bots) in the channel
    """
    if member.bot:
        return False
        
    # Check if user is deafened
    if member.voice and member.voice.deaf:
        return False
        
    # Count real people (non-bots) in the channel
    real_people = [m for m in channel.members if not m.bot]
    
    # Need at least 2 real people (including the user)
    if len(real_people) < 2:
        return False
        
    return True

class VoiceTracker:
    def __init__(self):
        self.voice_sessions: Dict[int, Dict[int, datetime]] = {}  # guild_id -> {user_id: join_time}
        self.periodic_update_task = None
        
    def start_periodic_updates(self):
        """Start periodic voice XP updates"""
        if self.periodic_update_task is None:
            self.periodic_update_task = asyncio.create_task(self._periodic_voice_xp_update())
            print("🔄 Started periodic voice XP updates")
        
    def stop_periodic_updates(self):
        """Stop periodic voice XP updates"""
        if self.periodic_update_task:
            self.periodic_update_task.cancel()
            self.periodic_update_task = None
            print("🛑 Stopped periodic voice XP updates")
        
    def user_joined_voice(self, guild_id: int, user_id: int, channel: discord.VoiceChannel):
        """Track when a user joins a voice channel"""
        print(f"🎙️ VOICE JOIN: User {user_id} joined {channel.name} in guild {guild_id}")
        print(f"   Channel members: {len(channel.members)} total")
        
        if guild_id not in self.voice_sessions:
            self.voice_sessions[guild_id] = {}
            
        # Get the member object to check conditions
        member = channel.guild.get_member(user_id)
        if not member:
            print(f"   🚫 Could not find member {user_id} in guild {guild_id}")
            return
            
        # Check if user should get voice XP
        if should_get_voice_xp(member, channel):
            self.voice_sessions[guild_id][user_id] = datetime.utcnow()
            real_people = [m for m in channel.members if not m.bot]
            print(f"   ✅ Voice tracking started for user {user_id} - {len(real_people)} real people in channel")
            
            # Start periodic updates if not already running
            self.start_periodic_updates()
        else:
            # Check why they're not eligible
            if member.voice and member.voice.deaf:
                print(f"   🚫 Not tracking voice for user {user_id} - user is deafened")
            else:
                real_people = [m for m in channel.members if not m.bot]
                print(f"   🚫 Not tracking voice for user {user_id} - only {len(real_people)} real people in channel (need 2+)")
            
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
                # Create task for async award
                asyncio.create_task(self._award_voice_xp(guild_id, user_id, voice_time))
                
        if new_channel:
            # Start tracking in new channel
            self.user_joined_voice(guild_id, user_id, new_channel)
            
    async def _periodic_voice_xp_update(self):
        """Periodically award voice XP to users who are in voice channels"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                current_time = datetime.utcnow()
                users_to_award = []
                users_to_remove = []
                
                # Check all active voice sessions
                for guild_id, sessions in self.voice_sessions.items():
                    for user_id, join_time in sessions.items():
                        # Get the guild and member to check current conditions
                        guild = _client.get_guild(guild_id) if _client else None
                        if not guild:
                            users_to_remove.append((guild_id, user_id))
                            continue
                            
                        member = guild.get_member(user_id)
                        if not member or not member.voice or not member.voice.channel:
                            users_to_remove.append((guild_id, user_id))
                            continue
                            
                        # Check if user should still get voice XP
                        if not should_get_voice_xp(member, member.voice.channel):
                            users_to_remove.append((guild_id, user_id))
                            continue
                            
                        duration = (current_time - join_time).total_seconds() / 60  # minutes
                        
                        # Award XP every minute (minimum 1 minute)
                        if duration >= 1:
                            minutes_to_award = int(duration)
                            users_to_award.append((guild_id, user_id, minutes_to_award))
                            
                            # Update join time to current time (reset the timer)
                            self.voice_sessions[guild_id][user_id] = current_time
                
                # Remove users who no longer qualify
                for guild_id, user_id in users_to_remove:
                    if guild_id in self.voice_sessions and user_id in self.voice_sessions[guild_id]:
                        del self.voice_sessions[guild_id][user_id]
                        print(f"🔄 Removed user {user_id} from voice tracking - no longer eligible")
                
                # Award XP to all users
                for guild_id, user_id, minutes in users_to_award:
                    try:
                        await self._award_voice_xp(guild_id, user_id, minutes)
                    except Exception as e:
                        print(f"❌ Error in periodic voice XP update for user {user_id}: {e}")
                        
            except asyncio.CancelledError:
                print("🛑 Periodic voice XP update task cancelled")
                break
            except Exception as e:
                print(f"❌ Error in periodic voice XP update: {e}")
                await asyncio.sleep(60)  # Wait before retrying
            
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
                
            if not settings.voice_xp_enabled:  # type: ignore
                print(f"   Voice XP disabled for guild {guild_id}")
                return
                
            # Calculate XP
            base_xp = minutes * settings.voice_xp_rate  # type: ignore
            xp_to_award = int(base_xp * settings.multiplier)  # type: ignore
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
            old_level = int(user_level.voice_level) if user_level.voice_level is not None else 0  # type: ignore
            old_xp = int(user_level.voice_xp) if user_level.voice_xp is not None else 0  # type: ignore
            old_voice_time = int(user_level.total_voice_time) if user_level.total_voice_time is not None else 0  # type: ignore
            
            user_level.voice_xp = old_xp + xp_to_award  # type: ignore
            user_level.total_voice_time = old_voice_time + minutes  # type: ignore
            user_level.last_voice_update = datetime.utcnow()  # type: ignore
            user_level.voice_level = calculate_level(old_xp + xp_to_award)  # type: ignore
            
            print(f"   Voice XP updated: {old_xp} -> {user_level.voice_xp}")
            print(f"   Voice time updated: {old_voice_time} -> {user_level.total_voice_time} minutes")
            print(f"   Voice level updated: {old_level} -> {user_level.voice_level}")
            
            session.commit()
            
            # Check for level up
            new_level = calculate_level(old_xp + xp_to_award)
            if new_level > old_level:
                print(f"   🎉 Voice level up! {old_level} -> {new_level}")
                await self._handle_level_up(guild_id, user_id, old_level, new_level, "voice")
                
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
            
        # User moved between channels
        elif before.channel and after.channel and before.channel != after.channel:
            print(f"   🔄 User moved between channels")
            voice_tracker.user_moved_voice(guild_id, user_id, before.channel, after.channel)
            
        # User stayed in same channel but something changed (mute, deafen, etc.)
        elif before.channel == after.channel and after.channel:
            print(f"   ⚡ Same channel state change in {after.channel.name}")
            
            # Check if user should still get voice XP
            should_get_xp = should_get_voice_xp(member, after.channel)
            currently_tracked = user_id in voice_tracker.voice_sessions.get(guild_id, {})
            
            if should_get_xp and not currently_tracked:
                print(f"   ✅ User now qualifies for voice XP, starting tracking")
                voice_tracker.user_joined_voice(guild_id, user_id, after.channel)
            elif not should_get_xp and currently_tracked:
                print(f"   🚫 User no longer qualifies for voice XP, stopping tracking")
                voice_time = voice_tracker.user_left_voice(guild_id, user_id)
                if voice_time:
                    await voice_tracker._award_voice_xp(guild_id, user_id, voice_time)
            else:
                print(f"   ➡️ No tracking change needed")
                
    except Exception as e:
        print(f"❌ Error in voice state handling: {e}")
        print(f"   Full error: {traceback.format_exc()}")

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
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
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
                        language.get_text("leveling_no_xp", user_lang),
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        language.get_text("leveling_other_no_xp", user_lang, user_name=target_user.display_name),
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
                title=language.get_text("leveling_rank_title", user_lang, user_name=target_user.display_name),
                color=discord.Color.from_rgb(114, 137, 218)
            )
            embed.set_thumbnail(url=target_user.display_avatar.url)
            
            # Server rank and total XP
            total_xp = user_level.text_xp + user_level.voice_xp
            embed.add_field(
                name=language.get_text("leveling_server_rank", user_lang),
                value=f"**#{rank}** out of {len(all_users)} users",
                inline=True
            )
            embed.add_field(
                name=language.get_text("leveling_total_xp", user_lang),
                value=f"**{total_xp:,}** XP",
                inline=True
            )
            embed.add_field(
                name=language.get_text("leveling_activity", user_lang),
                value=f"**{user_level.total_messages:,}** messages\n**{user_level.total_voice_time:,}** min voice",
                inline=True
            )
            
            # Text level progress
            text_current_level_xp = calculate_xp_for_level(text_level)
            text_progress_xp = user_level.text_xp - text_current_level_xp
            text_level_xp_needed = text_next_xp - text_current_level_xp
            text_progress_bar = create_progress_bar(text_progress_xp, text_level_xp_needed, 15)
            
            embed.add_field(
                name=language.get_text("leveling_text_level", user_lang),
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
                name=language.get_text("leveling_voice_level", user_lang), 
                value=f"**Level {voice_level}**\n"
                      f"`{voice_progress_bar}` {voice_progress_xp}/{voice_level_xp_needed}\n"
                      f"*{voice_needed:,} XP to level {voice_level + 1}*",
                inline=True
            )
            
            # Progress visualization
            embed.add_field(
                name=language.get_text("leveling_xp_breakdown", user_lang),
                value=f"💬 Text: **{user_level.text_xp:,}** XP\n"
                      f"🎙️ Voice: **{user_level.voice_xp:,}** XP",
                inline=True
            )
            
            embed.set_footer(text=language.get_text("leveling_footer", user_lang, server_name=interaction.guild.name))
            
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
        name="voicestatus",
        description="Check current voice tracking status (Admin only)"
    )
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def voicestatus(interaction: discord.Interaction):
        """Check the current voice tracking status"""
        try:
            await interaction.response.defer()
            
            guild_id = interaction.guild_id
            guild_sessions = voice_tracker.voice_sessions.get(guild_id, {})
            
            embed = discord.Embed(
                title="🎙️ Voice Tracking Status",
                description=f"Voice tracking status for **{interaction.guild.name}**",
                color=discord.Color.blue()
            )
            
            # Overall status
            embed.add_field(
                name="📊 Overall Status",
                value=f"**Periodic Updates:** {'✅ Running' if voice_tracker.periodic_update_task and not voice_tracker.periodic_update_task.done() else '❌ Stopped'}\n"
                      f"**Active Sessions:** {len(guild_sessions)} users",
                inline=False
            )
            
            # Active voice sessions
            if guild_sessions:
                session_details = []
                current_time = datetime.utcnow()
                
                for user_id, join_time in guild_sessions.items():
                    try:
                        member = interaction.guild.get_member(user_id)
                        name = member.display_name if member else f"User {user_id}"
                        duration = (current_time - join_time).total_seconds() / 60
                        session_details.append(f"• **{name}**: {duration:.1f} minutes")
                    except Exception as e:
                        session_details.append(f"• **User {user_id}**: Error getting info")
                
                embed.add_field(
                    name="👥 Active Voice Sessions",
                    value="\n".join(session_details),
                    inline=False
                )
            else:
                embed.add_field(
                    name="👥 Active Voice Sessions",
                    value="No active voice sessions",
                    inline=False
                )
            
            # Voice channels with users
            voice_channels = [c for c in interaction.guild.voice_channels if c.members]
            if voice_channels:
                channel_info = []
                for channel in voice_channels:
                    member_count = len(channel.members)
                    real_people = [m for m in channel.members if not m.bot]
                    real_count = len(real_people)
                    tracked_count = sum(1 for member in channel.members if member.id in guild_sessions)
                    
                    # Check conditions for each real person
                    eligible_count = 0
                    for member in real_people:
                        if should_get_voice_xp(member, channel):
                            eligible_count += 1
                    
                    status_emoji = "✅" if eligible_count > 0 else "❌"
                    channel_info.append(
                        f"{status_emoji} **{channel.name}**: {member_count} total ({real_count} real, {eligible_count} eligible, {tracked_count} tracked)"
                    )
                
                embed.add_field(
                    name="🎵 Voice Channels",
                    value="\n".join(channel_info),
                    inline=False
                )
                
                # Add explanation
                embed.add_field(
                    name="📋 Eligibility Rules",
                    value="• ✅ = Channel has eligible users (2+ real people, not deafened)\n"
                          "• ❌ = No eligible users (alone, deafened, or only bots)\n"
                          "• **Real people** = Non-bot users\n"
                          "• **Eligible** = Users who can earn voice XP\n"
                          "• **Tracked** = Users currently being tracked",
                    inline=False
                )
            else:
                embed.add_field(
                    name="🎵 Voice Channels",
                    value="No users in voice channels",
                    inline=False
                )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error checking voice status: {str(e)}",
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
        name="top",
        description="Display server leaderboard by XP type"
    )
    @app_commands.describe(
        type="Type of XP to show leaderboard for",
        page="Page number to view (default: 1)"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Text XP", value="text"),
        app_commands.Choice(name="Voice XP", value="voice"),
        app_commands.Choice(name="Total XP", value="total")
    ])
    @log_command
    async def top(interaction: discord.Interaction, type: str = "total", page: int = 1):
        await interaction.response.defer()
        
        if page < 1:
            await interaction.followup.send("❌ Page number must be 1 or higher!", ephemeral=True)
            return
            
        session = get_session(str(interaction.guild_id))
        try:
            # Get all users with XP
            users = session.query(UserLevel).filter_by(guild_id=str(interaction.guild_id)).all()
            
            if not users:
                await interaction.followup.send("No users have earned XP yet!", ephemeral=True)
                return
                
            # Sort users based on XP type
            if type == "text":
                sorted_users = sorted(users, key=lambda u: u.text_xp or 0, reverse=True)
                xp_type_name = "Text"
                get_xp = lambda u: u.text_xp
                get_level = lambda u: u.text_level
            elif type == "voice":
                sorted_users = sorted(users, key=lambda u: u.voice_xp or 0, reverse=True)
                xp_type_name = "Voice"
                get_xp = lambda u: u.voice_xp
                get_level = lambda u: u.voice_level
            else:  # total
                sorted_users = sorted(users, key=lambda u: (u.text_xp or 0) + (u.voice_xp or 0), reverse=True)
                xp_type_name = "Total"
                get_xp = lambda u: (u.text_xp or 0) + (u.voice_xp or 0)
                get_level = lambda u: max(u.text_level or 0, u.voice_level or 0)
            
            # Paginate results (10 per page)
            total_pages = (len(sorted_users) + 9) // 10
            page = min(page, total_pages)
            start_idx = (page - 1) * 10
            page_users = sorted_users[start_idx:start_idx + 10]
            
            # Create leaderboard embed
            embed = discord.Embed(
                title=f"🏆 {interaction.guild.name} Leaderboard",
                description=f"Top users by {xp_type_name} XP",
                color=discord.Color.gold()
            )
            
            # Add user entries
            for idx, user_level in enumerate(page_users, start=start_idx + 1):
                try:
                    member = interaction.guild.get_member(int(user_level.user_id))
                    name = member.display_name if member else f"User {user_level.user_id}"
                    xp = get_xp(user_level)
                    level = get_level(user_level)
                    
                    medal = "👑" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"`#{idx}`"
                    embed.add_field(
                        name=f"{medal} {name}",
                        value=f"Level {level} • {xp:,} XP",
                        inline=False
                    )
                except Exception as e:
                    print(f"Error adding user to leaderboard: {e}")
                    continue
            
            embed.set_footer(text=f"Page {page}/{total_pages} • {len(sorted_users)} total users")
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in top command: {e}")
            print(traceback.format_exc())
            await interaction.followup.send(
                "❌ An error occurred while generating the leaderboard.",
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
        name="setlevel",
        description="Set a user's level directly (Admin only)"
    )
    @app_commands.describe(
        user="User to set level for",
        type="Type of level to set",
        level="Level to set (0-100)"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Text Level", value="text"),
        app_commands.Choice(name="Voice Level", value="voice"),
    ])
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def setlevel(interaction: discord.Interaction, user: discord.Member, type: str, level: int):
        await interaction.response.defer()
        
        if level < 0 or level > 100:
            await interaction.followup.send("❌ Level must be between 0 and 100!", ephemeral=True)
            return
            
        # Calculate XP needed for this level
        xp_needed = calculate_xp_for_level(level)
        
        # Use setxp command logic to set the XP
        session = get_session(str(interaction.guild_id))
        try:
            user_level = session.query(UserLevel).filter_by(
                user_id=str(user.id),
                guild_id=str(interaction.guild_id)
            ).first()
            
            if not user_level:
                user_level = UserLevel(
                    user_id=str(user.id),
                    guild_id=str(interaction.guild_id),
                    text_xp=0,
                    voice_xp=0,
                    text_level=0,
                    voice_level=0,
                    total_messages=0,
                    total_voice_time=0
                )
                session.add(user_level)
            
            # Store old values
            if type == "text":
                old_level = int(user_level.text_level) if user_level.text_level is not None else 0
                old_xp = int(user_level.text_xp) if user_level.text_xp is not None else 0
                user_level.text_level = level
                user_level.text_xp = xp_needed
                xp_type_name = "Text"
            else:  # voice
                old_level = int(user_level.voice_level) if user_level.voice_level is not None else 0
                old_xp = int(user_level.voice_xp) if user_level.voice_xp is not None else 0
                user_level.voice_level = level
                user_level.voice_xp = xp_needed
                xp_type_name = "Voice"
            
            session.commit()
            
            embed = discord.Embed(
                title="✏️ Level Modified",
                description=f"Set {user.mention}'s {xp_type_name} Level to **{level}**",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="Changes",
                value=f"**Level:** {old_level} → {level}\n"
                      f"**XP:** {old_xp:,} → {xp_needed:,}",
                inline=False
            )
            
            # Handle level up rewards if level increased
            if level > old_level:
                try:
                    if not hasattr(_client, 'last_active_channel'):
                        _client.last_active_channel = {}
                    _client.last_active_channel[interaction.guild_id] = interaction.channel
                    
                    asyncio.create_task(voice_tracker._handle_level_up(
                        interaction.guild_id, user.id, old_level, level, type
                    ))
                except Exception as e:
                    print(f"Error in level up handling: {e}")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in setlevel command: {e}")
            print(traceback.format_exc())
            await interaction.followup.send(
                f"❌ An error occurred while setting the level: {str(e)}",
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
        name="lvlreset",
        description="Reset a user's levels and XP data (Admin only)"
    )
    @app_commands.describe(
        user="User to reset data for",
        type="Type of data to reset"
    )
    @app_commands.choices(type=[
        app_commands.Choice(name="Text XP Only", value="text"),
        app_commands.Choice(name="Voice XP Only", value="voice"),
        app_commands.Choice(name="All XP Data", value="all"),
    ])
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def lvlreset(interaction: discord.Interaction, user: discord.Member, type: str):
        await interaction.response.defer()
        
        session = get_session(str(interaction.guild_id))
        try:
            user_level = session.query(UserLevel).filter_by(
                user_id=str(user.id),
                guild_id=str(interaction.guild_id)
            ).first()
            
            if not user_level:
                await interaction.followup.send(
                    f"{user.mention} has no XP data to reset!",
                    ephemeral=True
                )
                return
            
            # Store old values for confirmation message
            old_text_level = int(user_level.text_level) if user_level.text_level is not None else 0
            old_text_xp = int(user_level.text_xp) if user_level.text_xp is not None else 0
            old_voice_level = int(user_level.voice_level) if user_level.voice_level is not None else 0
            old_voice_xp = int(user_level.voice_xp) if user_level.voice_xp is not None else 0
            
            # Reset based on type
            if type == "text" or type == "all":
                user_level.text_xp = 0
                user_level.text_level = 0
                user_level.total_messages = 0
            
            if type == "voice" or type == "all":
                user_level.voice_xp = 0
                user_level.voice_level = 0
                user_level.total_voice_time = 0
            
            session.commit()
            
            # Create confirmation embed
            embed = discord.Embed(
                title="🗑️ XP Data Reset",
                description=f"Reset {user.mention}'s XP data",
                color=discord.Color.red()
            )
            
            if type == "text" or type == "all":
                embed.add_field(
                    name="📝 Text Data Reset",
                    value=f"Level {old_text_level} → 0\n"
                          f"XP {old_text_xp:,} → 0",
                    inline=True
                )
            
            if type == "voice" or type == "all":
                embed.add_field(
                    name="🎙️ Voice Data Reset",
                    value=f"Level {old_voice_level} → 0\n"
                          f"XP {old_voice_xp:,} → 0",
                    inline=True
                )
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            print(f"Error in lvlreset command: {e}")
            print(traceback.format_exc())
            await interaction.followup.send(
                f"❌ An error occurred while resetting XP data: {str(e)}",
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
        app_commands.Choice(name="Text XP Enabled", value="text_xp_enabled"),
        app_commands.Choice(name="Voice XP Enabled", value="voice_xp_enabled"),
        app_commands.Choice(name="Text XP Min", value="text_xp_min"),
        app_commands.Choice(name="Text XP Max", value="text_xp_max"),
        app_commands.Choice(name="Voice XP Rate", value="voice_xp_rate"),
        app_commands.Choice(name="Text Cooldown", value="text_cooldown"),
        app_commands.Choice(name="XP Multiplier", value="multiplier"),
        app_commands.Choice(name="Level Up Messages", value="level_up_messages"),
        app_commands.Choice(name="Level Up Channel", value="level_up_channel"),
    ])
    @app_commands.default_permissions(administrator=True)
    @log_command
    async def lvlconfig(interaction: discord.Interaction, setting: str, value: Optional[str] = None):
        await interaction.response.defer()
        
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
                    name="📝 Text XP Settings",
                    value=f"**Enabled:** {'✅' if settings.text_xp_enabled else '❌'}\n"
                          f"**XP per message:** {settings.text_xp_min}-{settings.text_xp_max}\n"
                          f"**Cooldown:** {settings.text_cooldown}s",
                    inline=True
                )
                
                embed.add_field(
                    name="🎙️ Voice XP Settings",
                    value=f"**Enabled:** {'✅' if settings.voice_xp_enabled else '❌'}\n"
                          f"**XP per minute:** {settings.voice_xp_rate}",
                    inline=True
                )
                
                embed.add_field(
                    name="⚡ General Settings",
                    value=f"**XP Multiplier:** {settings.multiplier}x\n"
                          f"**Level Up Messages:** {'✅' if settings.level_up_messages else '❌'}\n"
                          f"**Level Up Channel:** {f'<#{settings.level_up_channel}>' if settings.level_up_channel else 'Same as command'}",
                    inline=False
                )
                
                if settings.no_xp_roles:
                    no_xp_roles = [f"<@&{role_id}>" for role_id in settings.no_xp_roles.split(",") if role_id]
                    embed.add_field(
                        name="🚫 No XP Roles",
                        value="\n".join(no_xp_roles) or "None",
                        inline=False
                    )
                
                if settings.no_xp_channels:
                    no_xp_channels = [f"<#{channel_id}>" for channel_id in settings.no_xp_channels.split(",") if channel_id]
                    embed.add_field(
                        name="🚫 No XP Channels",
                        value="\n".join(no_xp_channels) or "None",
                        inline=False
                    )
                
                await interaction.followup.send(embed=embed)
                return
            
            # Update setting
            try:
                if setting in ("text_xp_enabled", "voice_xp_enabled", "level_up_messages"):
                    new_val = value.lower() in ('true', '1', 'yes', 'on', 'enable', 'enabled')
                    setattr(settings, setting, new_val)
                    desc = f"{setting.replace('_', ' ').title()} {'enabled' if new_val else 'disabled'}"
                    
                elif setting in ("text_xp_min", "text_xp_max", "voice_xp_rate", "text_cooldown"):
                    new_val = int(value)
                    if new_val < 0:
                        raise ValueError("Value cannot be negative")
                    if setting == "text_cooldown" and new_val < 1:
                        raise ValueError("Cooldown must be at least 1 second")
                    setattr(settings, setting, new_val)
                    desc = f"{setting.replace('_', ' ').title()} set to {new_val}"
                    
                elif setting == "multiplier":
                    new_val = float(value)
                    if new_val < 0.1 or new_val > 5.0:
                        raise ValueError("Must be between 0.1 and 5.0")
                    settings.multiplier = new_val
                    desc = f"XP multiplier set to {new_val}x"
                    
                elif setting == "level_up_channel":
                    if value.lower() in ('none', 'disable', 'disabled', 'remove', 'reset'):
                        settings.level_up_channel = None
                        desc = "Level up messages will be sent in the same channel as commands"
                    else:
                        # Try to get channel ID from mention or ID
                        channel_id = value.strip('<#>')
                        channel = interaction.guild.get_channel(int(channel_id))
                        if not channel:
                            raise ValueError("Invalid channel")
                        settings.level_up_channel = str(channel.id)
                        desc = f"Level up messages will be sent in {channel.mention}"
                
                else:
                    await interaction.followup.send("Invalid setting!", ephemeral=True)
                    return
                    
                session.commit()
                
                embed = discord.Embed(
                    title="✅ Setting Updated",
                    description=desc,
                    color=discord.Color.green()
                )
                
                await interaction.followup.send(embed=embed)
                
            except ValueError as e:
                await interaction.followup.send(
                    f"❌ Invalid value: {str(e)}",
                    ephemeral=True
                )
                
        except Exception as e:
            print(f"Error in lvlconfig: {e}")
            print(traceback.format_exc())
            await interaction.followup.send(
                "❌ An error occurred while updating settings.",
                ephemeral=True
            )
        finally:
            session.close()

    @tree.command(
        name="setxp",
        description="Set a user's XP directly (Admin only)"
    )
    @app_commands.describe(
        user="User to set XP for",
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
        try:
            # Defer the response immediately to prevent timeout
            await interaction.response.defer(ephemeral=False)
            
            if amount < 0:
                await interaction.followup.send("❌ XP amount cannot be negative!", ephemeral=True)
                return

            session = get_session(str(interaction.guild_id))
            try:
                # Get or create user level in a single query
                user_level = session.query(UserLevel).filter_by(
                    user_id=str(user.id),
                    guild_id=str(interaction.guild_id)
                ).first()
                
                if not user_level:
                    user_level = UserLevel(
                        user_id=str(user.id),
                        guild_id=str(interaction.guild_id),
                        text_xp=0,
                        voice_xp=0,
                        text_level=0,
                        voice_level=0,
                        total_messages=0,
                        total_voice_time=0
                    )
                    session.add(user_level)
                
                # Store old values and update new values
                if type == "text":
                    old_xp = int(user_level.text_xp) if user_level.text_xp is not None else 0
                    old_level = int(user_level.text_level) if user_level.text_level is not None else 0
                    user_level.text_xp = amount
                    user_level.text_level = calculate_level(amount)
                    xp_type_name = "Text"
                else:  # voice
                    old_xp = int(user_level.voice_xp) if user_level.voice_xp is not None else 0
                    old_level = int(user_level.voice_level) if user_level.voice_level is not None else 0
                    user_level.voice_xp = amount
                    user_level.voice_level = calculate_level(amount)
                    xp_type_name = "Voice"
                
                # Commit changes
                try:
                    session.commit()
                except Exception as e:
                    print(f"Database error in setxp: {e}")
                    session.rollback()
                    await interaction.followup.send("❌ Database error occurred while saving changes.", ephemeral=True)
                    return
                
                # Calculate new level after successful commit
                new_level = calculate_level(amount)
                
                # Create response embed
                embed = discord.Embed(
                    title="✏️ XP Modified",
                    description=f"Set {user.mention}'s {xp_type_name} XP to **{amount:,}**",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="Changes",
                    value=f"**XP:** {old_xp:,} → {amount:,}\n"
                          f"**Level:** {old_level} → {new_level}",
                    inline=False
                )
                
                # Handle level up if applicable
                if new_level != old_level:
                    embed.add_field(
                        name="📊 Level Change",
                        value=f"{'📈' if new_level > old_level else '📉'} Level {old_level} → Level {new_level}",
                        inline=False
                    )
                    
                    # Only trigger level up handling if level increased
                    if new_level > old_level:
                        try:
                            if not hasattr(_client, 'last_active_channel'):
                                _client.last_active_channel = {}
                            _client.last_active_channel[interaction.guild_id] = interaction.channel
                            
                            # Handle level up in background task to not delay response
                            asyncio.create_task(voice_tracker._handle_level_up(
                                interaction.guild_id, user.id, old_level, new_level, type
                            ))
                        except Exception as e:
                            print(f"Error in level up handling: {e}")
                            # Don't fail the command if level up handling fails
                
                await interaction.followup.send(embed=embed)
                
            except Exception as e:
                print(f"Error in setxp command: {e}")
                print(traceback.format_exc())
                await interaction.followup.send(
                    f"❌ An error occurred while processing the command: {str(e)}",
                    ephemeral=True
                )
            finally:
                session.close()
                
        except Exception as e:
            print(f"Critical error in setxp command: {e}")
            print(traceback.format_exc())
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ A critical error occurred while processing the command.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ A critical error occurred while processing the command.",
                    ephemeral=True
                )

# Export the setup functions
__all__ = ['setup_leveling_system', 'setup_level_commands', 'handle_message_xp', 'handle_voice_state_update'] 