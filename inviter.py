import discord
from discord import app_commands
from discord.app_commands import checks
import functools
from typing import Callable, Any, Optional
import traceback
from datetime import datetime
from database import get_session, get_engine, Base
from sqlalchemy import Column, Integer, String, DateTime, Boolean, desc, func
from sqlalchemy.ext.declarative import declarative_base

# Store reference to the client
_client = None

def setup_inviter_system(client):
    """Initialize the invite tracking system with client reference"""
    global _client
    _client = client
    print("✅ Inviter system initialized with client reference")

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
                    f"An error occurred while executing the command: {str(e)}",
                    ephemeral=True
                )
            raise
    return wrapper

# Database Models
Base = declarative_base()

class InviteTracker(Base):
    """Track invite codes and their creators"""
    __tablename__ = 'invite_tracker'
    
    id = Column(Integer, primary_key=True)
    guild_id = Column(String, nullable=False)
    invite_code = Column(String, nullable=False, unique=True)
    inviter_id = Column(String, nullable=False)  # User who created the invite
    channel_id = Column(String, nullable=False)  # Channel invite was created for
    uses = Column(Integer, default=0)  # Current uses of the invite
    created_at = Column(DateTime, default=datetime.utcnow)

class InviteJoin(Base):
    """Track when users join through specific invites"""
    __tablename__ = 'invite_joins'
    
    id = Column(Integer, primary_key=True)
    guild_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    inviter_id = Column(String, nullable=False)  # Who invited them
    invite_code = Column(String, nullable=False)
    joined_at = Column(DateTime, default=datetime.utcnow)
    has_left = Column(Boolean, default=False)
    left_at = Column(DateTime, nullable=True)

class InviteStats(Base):
    """Aggregate invite statistics per user per guild"""
    __tablename__ = 'invite_stats'
    
    id = Column(Integer, primary_key=True)
    guild_id = Column(String, nullable=False)
    inviter_id = Column(String, nullable=False)
    total_invites = Column(Integer, default=0)  # Total people invited
    total_leaves = Column(Integer, default=0)   # Total people who left after being invited
    net_invites = Column(Integer, default=0)    # total_invites - total_leaves
    last_updated = Column(DateTime, default=datetime.utcnow)

class InviteAdmin(Base):
    """Track users who can manage invite system"""
    __tablename__ = 'invite_admins'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=False)
    server_id = Column(String, nullable=False)
    added_by = Column(String, nullable=False)
    added_at = Column(DateTime, default=datetime.utcnow)

# Create tables
def init_invite_db(server_id):
    """Initialize invite database tables"""
    try:
        Base.metadata.create_all(bind=get_engine(server_id))
        print(f"✅ Invite database initialized for server {server_id}")
    except Exception as e:
        print(f"❌ Error initializing invite database: {e}")

# Invite tracking cache to store current invites
guild_invites_cache = {}

async def update_invite_cache(guild):
    """Update the invite cache for a guild"""
    try:
        invites = await guild.invites()
        guild_invites_cache[guild.id] = {invite.code: invite.uses for invite in invites}
        print(f"📊 Updated invite cache for {guild.name}: {len(invites)} invites")
    except discord.Forbidden:
        print(f"❌ No permission to fetch invites for {guild.name}")
    except Exception as e:
        print(f"❌ Error updating invite cache for {guild.name}: {e}")

async def sync_invite_database(guild):
    """Sync current Discord invites with database"""
    init_invite_db(str(guild.id))
    session = get_session(str(guild.id))
    try:
        invites = await guild.invites()
        
        for invite in invites:
            # Check if invite exists in database
            db_invite = session.query(InviteTracker).filter_by(
                invite_code=invite.code
            ).first()
            
            if not db_invite:
                # Add new invite to database
                db_invite = InviteTracker(
                    guild_id=str(guild.id),
                    invite_code=invite.code,
                    inviter_id=str(invite.inviter.id) if invite.inviter else "0",
                    channel_id=str(invite.channel.id),
                    uses=invite.uses,
                    created_at=invite.created_at or datetime.utcnow()
                )
                session.add(db_invite)
            else:
                # Update uses if changed
                db_invite.uses = invite.uses
        
        session.commit()
        print(f"✅ Synced {len(invites)} invites for {guild.name}")
        
    except discord.Forbidden:
        print(f"❌ No permission to sync invites for {guild.name}")
    except Exception as e:
        print(f"❌ Error syncing invites for {guild.name}: {e}")
        session.rollback()
    finally:
        session.close()

async def handle_member_join(member):
    """Handle when a member joins - detect which invite was used"""
    guild = member.guild
    init_invite_db(str(guild.id))
    session = get_session(str(guild.id))
    
    try:
        # Get current invites
        current_invites = await guild.invites()
        current_invite_uses = {invite.code: invite.uses for invite in current_invites}
        
        # Compare with cached invites to find which one was used
        used_invite = None
        if guild.id in guild_invites_cache:
            cached_invites = guild_invites_cache[guild.id]
            
            for code, current_uses in current_invite_uses.items():
                cached_uses = cached_invites.get(code, 0)
                if current_uses > cached_uses:
                    # This invite was used
                    used_invite = next((inv for inv in current_invites if inv.code == code), None)
                    break
        
        # Update cache
        guild_invites_cache[guild.id] = current_invite_uses
        
        if used_invite and used_invite.inviter:
            # Record the join
            invite_join = InviteJoin(
                guild_id=str(guild.id),
                user_id=str(member.id),
                inviter_id=str(used_invite.inviter.id),
                invite_code=used_invite.code,
                joined_at=datetime.utcnow()
            )
            session.add(invite_join)
            
            # Update or create invite stats
            stats = session.query(InviteStats).filter_by(
                guild_id=str(guild.id),
                inviter_id=str(used_invite.inviter.id)
            ).first()
            
            if not stats:
                stats = InviteStats(
                    guild_id=str(guild.id),
                    inviter_id=str(used_invite.inviter.id),
                    total_invites=1,
                    total_leaves=0,
                    net_invites=1,
                    last_updated=datetime.utcnow()
                )
                session.add(stats)
            else:
                stats.total_invites += 1
                stats.net_invites = stats.total_invites - stats.total_leaves
                stats.last_updated = datetime.utcnow()
            
            # Update database invite tracker
            db_invite = session.query(InviteTracker).filter_by(
                invite_code=used_invite.code
            ).first()
            if db_invite:
                db_invite.uses = used_invite.uses
            
            session.commit()
            
            print(f"👋 {member.display_name} joined {guild.name} via {used_invite.inviter.display_name}'s invite ({used_invite.code})")
            
            # Send join notification if configured
            await send_join_notification(guild, member, used_invite.inviter, used_invite.code)
        else:
            print(f"👋 {member.display_name} joined {guild.name} (invite unknown)")
            
    except Exception as e:
        print(f"❌ Error handling member join for {member.display_name}: {e}")
        print(traceback.format_exc())
        session.rollback()
    finally:
        session.close()

async def can_manage_invites(interaction: discord.Interaction) -> bool:
    """Check if user can manage invite system"""
    # Server administrators can always manage invites
    if hasattr(interaction.user, 'guild_permissions') and interaction.user.guild_permissions.administrator:
        return True
    
    # For members, check guild permissions
    if interaction.guild:
        member = interaction.guild.get_member(interaction.user.id)
        if member and member.guild_permissions.administrator:
            return True
    
    # Check if user is in invite admin whitelist
    init_invite_db(str(interaction.guild_id))
    session = get_session(str(interaction.guild_id))
    try:
        admin_record = session.query(InviteAdmin).filter_by(
            user_id=str(interaction.user.id),
            server_id=str(interaction.guild_id)
        ).first()
        return admin_record is not None
    except Exception as e:
        print(f"Error checking invite admin permissions: {e}")
        return False
    finally:
        session.close()

async def handle_member_leave(member):
    """Handle when a member leaves - update leave statistics"""
    guild = member.guild
    init_invite_db(str(guild.id))
    session = get_session(str(guild.id))
    
    try:
        # Find the join record for this member
        join_record = session.query(InviteJoin).filter_by(
            guild_id=str(guild.id),
            user_id=str(member.id),
            has_left=False
        ).first()
        
        if join_record:
            # Mark as left
            join_record.has_left = True
            join_record.left_at = datetime.utcnow()
            
            # Update inviter stats
            stats = session.query(InviteStats).filter_by(
                guild_id=str(guild.id),
                inviter_id=join_record.inviter_id
            ).first()
            
            if stats:
                stats.total_leaves += 1
                stats.net_invites = stats.total_invites - stats.total_leaves
                stats.last_updated = datetime.utcnow()
            
            session.commit()
            
            try:
                if _client:
                    inviter = await _client.fetch_user(int(join_record.inviter_id))
                    inviter_name = inviter.display_name if inviter else "Unknown"
                else:
                    inviter_name = "Unknown"
            except:
                inviter_name = "Unknown"
            
            print(f"👋 {member.display_name} left {guild.name} (originally invited by {inviter_name})")
            
            # Send leave notification if configured
            await send_leave_notification(guild, member, join_record.inviter_id)
        else:
            print(f"👋 {member.display_name} left {guild.name} (no invite record found)")
            
    except Exception as e:
        print(f"❌ Error handling member leave for {member.display_name}: {e}")
        print(traceback.format_exc())
        session.rollback()
    finally:
        session.close()

async def send_join_notification(guild, member, inviter, invite_code):
    """Send notification when someone joins via invite (if configured)"""
    # This can be expanded to send notifications to a specific channel
    # For now, just log it
    pass

async def send_leave_notification(guild, member, inviter_id):
    """Send notification when someone leaves (if configured)"""
    # This can be expanded to send notifications to a specific channel
    # For now, just log it
    pass

# UI Components

class ResetInvitesConfirmView(discord.ui.View):
    """Confirmation view for resetting all invite data"""
    
    def __init__(self):
        super().__init__(timeout=60)
        self.confirmed = False
    
    @discord.ui.button(label="✅ Yes, Reset All Data", style=discord.ButtonStyle.danger)
    async def confirm_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        
        # Disable all buttons
        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True
        
        await interaction.response.edit_message(content="🔄 Resetting all invite data...", view=self)
        
        # Reset all invite data
        session = get_session(str(interaction.guild_id))
        try:
            # Delete all invite stats for this server
            session.query(InviteStats).filter_by(
                guild_id=str(interaction.guild_id)
            ).delete()
            
            # Delete all invite joins for this server
            session.query(InviteJoin).filter_by(
                guild_id=str(interaction.guild_id)
            ).delete()
            
            # Keep invite tracker entries but reset uses to 0
            invite_trackers = session.query(InviteTracker).filter_by(
                guild_id=str(interaction.guild_id)
            ).all()
            
            for tracker in invite_trackers:
                tracker.uses = 0
            
            session.commit()
            
            # Re-sync current invite data
            await sync_invite_database(interaction.guild)
            await update_invite_cache(interaction.guild)
            
            await interaction.edit_original_response(
                content="✅ **All invite data has been reset!**\n\n"
                        "• All user statistics cleared\n"
                        "• All join/leave records deleted\n"
                        "• Invite tracking restarted fresh\n\n"
                        "The system will now track new activity from this point forward.",
                view=None
            )
            
        except Exception as e:
            print(f"Error resetting invite data: {e}")
            await interaction.edit_original_response(
                content=f"❌ Error occurred while resetting data: {str(e)}",
                view=None
            )
            session.rollback()
        finally:
            session.close()
    
    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="❌ Invite data reset cancelled.",
            view=None
        )

class EditInvitesModal(discord.ui.Modal):
    """Modal for editing user invite statistics"""
    
    def __init__(self, user: discord.Member, current_stats: Optional[InviteStats] = None):
        super().__init__(title=f"Edit Invites for {user.display_name}")
        self.user = user
        self.current_stats = current_stats
        
        # Current values or defaults
        current_invites = str(current_stats.total_invites) if current_stats else "0"
        current_leaves = str(current_stats.total_leaves) if current_stats else "0"
        
        self.invites_input = discord.ui.TextInput(
            label="Total Invites",
            placeholder="Enter the total number of people this user has invited",
            default=current_invites,
            required=True,
            max_length=10
        )
        self.add_item(self.invites_input)
        
        self.leaves_input = discord.ui.TextInput(
            label="Total Leaves",
            placeholder="Enter the total number of people who left after being invited",
            default=current_leaves,
            required=True,
            max_length=10
        )
        self.add_item(self.leaves_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate inputs
            try:
                total_invites = int(self.invites_input.value)
                total_leaves = int(self.leaves_input.value)
                
                if total_invites < 0 or total_leaves < 0:
                    raise ValueError("Values cannot be negative")
                    
                if total_leaves > total_invites:
                    await interaction.response.send_message(
                        "❌ Total leaves cannot be greater than total invites!",
                        ephemeral=True
                    )
                    return
                    
            except ValueError:
                await interaction.response.send_message(
                    "❌ Please enter valid positive numbers only!",
                    ephemeral=True
                )
                return
            
            # Update database
            session = get_session(str(interaction.guild_id))
            try:
                if self.current_stats:
                    # Update existing stats - query fresh from database
                    stats = session.query(InviteStats).filter_by(
                        id=self.current_stats.id
                    ).first()
                    
                    if stats:
                        stats.total_invites = total_invites
                        stats.total_leaves = total_leaves
                        stats.net_invites = total_invites - total_leaves
                        stats.last_updated = datetime.utcnow()
                else:
                    # Create new stats
                    new_stats = InviteStats(
                        guild_id=str(interaction.guild_id),
                        inviter_id=str(self.user.id),
                        total_invites=total_invites,
                        total_leaves=total_leaves,
                        net_invites=total_invites - total_leaves,
                        last_updated=datetime.utcnow()
                    )
                    session.add(new_stats)
                
                session.commit()
                
                net_invites = total_invites - total_leaves
                await interaction.response.send_message(
                    f"✅ **Updated invite statistics for {self.user.display_name}:**\n\n"
                    f"• **Total Invites:** {total_invites}\n"
                    f"• **Total Leaves:** {total_leaves}\n"
                    f"• **Net Invites:** {net_invites}",
                    ephemeral=True
                )
                
            except Exception as e:
                print(f"Error updating invite stats: {e}")
                print(traceback.format_exc())
                await interaction.response.send_message(
                    "❌ An error occurred while updating the statistics.",
                    ephemeral=True
                )
                session.rollback()
            finally:
                session.close()
                
        except Exception as e:
            print(f"Error in EditInvitesModal: {e}")
            print(traceback.format_exc())
            await interaction.response.send_message(
                "❌ An unexpected error occurred.",
                ephemeral=True
            )

# Commands

@app_commands.command(
    name="invite",
    description="Manage server invites and view statistics"
)
@app_commands.describe(
    action="Choose which invite action to perform",
    user="The user to show/edit invites for (if applicable)",
    value="Additional value for the action (if needed)"
)
@app_commands.choices(action=[
    app_commands.Choice(name="stats", value="stats"),           # Show server stats
    app_commands.Choice(name="top", value="top"),              # Show top inviters
    app_commands.Choice(name="show", value="show"),            # Show user stats
    app_commands.Choice(name="edit", value="edit"),            # Edit user stats
    app_commands.Choice(name="sync", value="sync"),            # Sync invite data
    app_commands.Choice(name="reset", value="reset"),          # Reset all data
    app_commands.Choice(name="admin", value="admin"),          # Add/remove admin
    app_commands.Choice(name="resetdb", value="resetdb")       # Reset database
])
@log_command
async def invite_command(interaction: discord.Interaction, action: str, user: discord.Member = None, value: str = None):
    """Combined invite management command"""
    
    if action == "stats":
        # Server stats (former invitestats)
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only administrators can view server statistics!", ephemeral=True)
            return
        
        init_invite_db(str(interaction.guild_id))
        session = get_session(str(interaction.guild_id))
        try:
            guild_id = str(interaction.guild_id)
            
            # Get total stats
            total_stats = session.query(
                func.sum(InviteStats.total_invites).label('total_invites'),
                func.sum(InviteStats.total_leaves).label('total_leaves'),
                func.sum(InviteStats.net_invites).label('net_invites'),
                func.count(InviteStats.id).label('active_inviters')
            ).filter_by(guild_id=guild_id).first()
            
            # Get recent activity (last 7 days)
            from datetime import timedelta
            week_ago = datetime.utcnow() - timedelta(days=7)
            recent_joins = session.query(InviteJoin).filter(
                InviteJoin.guild_id == guild_id,
                InviteJoin.joined_at >= week_ago
            ).count()
            
            recent_leaves = session.query(InviteJoin).filter(
                InviteJoin.guild_id == guild_id,
                InviteJoin.left_at >= week_ago,
                InviteJoin.has_left == True
            ).count()
            
            embed = discord.Embed(
                title="📊 Server Invite Statistics",
                description=f"Comprehensive invite data for **{interaction.guild.name}**" if interaction.guild else "this server",
                color=discord.Color.green()
            )
            
            embed.add_field(
                name="📈 All Time Stats",
                value=f"**Total Invites:** {total_stats.total_invites or 0}\n"
                      f"**Total Leaves:** {total_stats.total_leaves or 0}\n"
                      f"**Net Invites:** {total_stats.net_invites or 0}\n"
                      f"**Active Inviters:** {total_stats.active_inviters or 0}",
                inline=True
            )
            
            embed.add_field(
                name="📅 Last 7 Days",
                value=f"**New Joins:** {recent_joins}\n"
                      f"**Leaves:** {recent_leaves}\n"
                      f"**Net Growth:** {recent_joins - recent_leaves}",
                inline=True
            )
            
            if total_stats.total_invites and total_stats.total_invites > 0:
                retention_rate = ((total_stats.total_invites - total_stats.total_leaves) / total_stats.total_invites) * 100
                embed.add_field(
                    name="📊 Server Retention",
                    value=f"**{retention_rate:.1f}%**",
                    inline=True
                )
            
            embed.set_footer(text="💡 Use /invite top to see individual user rankings")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            print(f"Error in invite stats: {e}")
            await interaction.response.send_message("❌ An error occurred while fetching server statistics.", ephemeral=True)
        finally:
            session.close()

    elif action == "top":
        # Show top inviters (former topinvite)
        init_invite_db(str(interaction.guild_id))
        session = get_session(str(interaction.guild_id))
        try:
            top_inviters = session.query(InviteStats).filter_by(
                guild_id=str(interaction.guild_id)
            ).order_by(desc(InviteStats.net_invites)).limit(10).all()
            
            if not top_inviters:
                await interaction.response.send_message(
                    "📊 No invite data found for this server yet!\n"
                    "Invite tracking starts when the bot is online and users join through invites.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title="🏆 Top Inviters",
                description=f"Top invite statistics for **{interaction.guild.name}**",
                color=discord.Color.gold()
            )
            
            for i, stats in enumerate(top_inviters, 1):
                try:
                    if _client:
                        user = await _client.fetch_user(int(stats.inviter_id))
                        username = user.display_name if user else f"Unknown User (ID: {stats.inviter_id})"
                    else:
                        member = interaction.guild.get_member(int(stats.inviter_id))
                        username = member.display_name if member else f"Unknown User (ID: {stats.inviter_id})"
                except:
                    username = f"Unknown User (ID: {stats.inviter_id})"
                
                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                
                embed.add_field(
                    name=f"{emoji} {username}",
                    value=f"**Invites:** {stats.total_invites}\n"
                          f"**Leaves:** {stats.total_leaves}\n"
                          f"**Net:** {stats.net_invites}",
                    inline=True
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Error in invite top: {e}")
            await interaction.response.send_message("❌ An error occurred while fetching top inviters.", ephemeral=True)
        finally:
            session.close()

    elif action == "show":
        # Show user stats (former showinvites)
        if not user:
            await interaction.response.send_message("❌ Please specify a user to show invite statistics for!", ephemeral=True)
            return
            
        init_invite_db(str(interaction.guild_id))
        session = get_session(str(interaction.guild_id))
        try:
            stats = session.query(InviteStats).filter_by(
                guild_id=str(interaction.guild_id),
                inviter_id=str(user.id)
            ).first()
            
            if not stats:
                await interaction.response.send_message(
                    f"📊 No invite data found for {user.display_name}.",
                    ephemeral=True
                )
                return
            
            embed = discord.Embed(
                title=f"📊 Invite Statistics for {user.display_name}",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=user.display_avatar.url)
            
            embed.add_field(
                name="📈 Overview",
                value=f"**Total Invites:** {stats.total_invites}\n"
                      f"**People Left:** {stats.total_leaves}\n"
                      f"**Net Invites:** {stats.net_invites}",
                inline=True
            )
            
            if stats.total_invites > 0:
                retention_rate = ((stats.total_invites - stats.total_leaves) / stats.total_invites) * 100
                embed.add_field(
                    name="📊 Retention Rate",
                    value=f"**{retention_rate:.1f}%**\n"
                          f"({stats.total_invites - stats.total_leaves} stayed)",
                    inline=True
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            print(f"Error in invite show: {e}")
            await interaction.response.send_message("❌ An error occurred while fetching user statistics.", ephemeral=True)
        finally:
            session.close()

    elif action == "edit":
        # Edit user stats (former editinvites)
        if not await can_manage_invites(interaction):
            await interaction.response.send_message("❌ You don't have permission to edit invite statistics!", ephemeral=True)
            return
            
        if not user:
            await interaction.response.send_message("❌ Please specify a user to edit invite statistics for!", ephemeral=True)
            return
            
        init_invite_db(str(interaction.guild_id))
        session = get_session(str(interaction.guild_id))
        try:
            current_stats = session.query(InviteStats).filter_by(
                guild_id=str(interaction.guild_id),
                inviter_id=str(user.id)
            ).first()
            
            modal = EditInvitesModal(user, current_stats)
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            print(f"Error in invite edit: {e}")
            await interaction.response.send_message("❌ An error occurred while loading user statistics.", ephemeral=True)
        finally:
            session.close()

    elif action == "sync":
        # Sync invite data (former invitesync)
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only administrators can sync invite data!", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        try:
            guild = interaction.guild
            init_invite_db(str(guild.id))
            await sync_invite_database(guild)
            await update_invite_cache(guild)
            
            await interaction.followup.send("✅ Invite data synchronized successfully!", ephemeral=True)
            
        except Exception as e:
            print(f"Error in invite sync: {e}")
            await interaction.followup.send(f"❌ An error occurred while syncing invite data: {str(e)}", ephemeral=True)

    elif action == "reset":
        # Reset invite data (former resetinvites)
        if not await can_manage_invites(interaction):
            await interaction.response.send_message("❌ You don't have permission to reset invite data!", ephemeral=True)
            return
            
        view = ResetInvitesConfirmView()
        embed = discord.Embed(
            title="⚠️ Reset All Invite Data",
            description="**This will permanently delete:**\n"
                      "• All user invite statistics\n"
                      "• All join/leave tracking records\n"
                      "• All historical invite data\n\n"
                      "**This action CANNOT be undone!**",
            color=discord.Color.red()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    elif action == "admin":
        # Add/remove admin (former invw)
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only administrators can manage invite admins!", ephemeral=True)
            return
            
        if not user:
            await interaction.response.send_message("❌ Please specify a user to add/remove as invite admin!", ephemeral=True)
            return
            
        if not value or value.lower() not in ['add', 'remove']:
            await interaction.response.send_message("❌ Please specify 'add' or 'remove' as the value!", ephemeral=True)
            return
            
        init_invite_db(str(interaction.guild_id))
        session = get_session(str(interaction.guild_id))
        try:
            existing_admin = session.query(InviteAdmin).filter_by(
                user_id=str(user.id),
                server_id=str(interaction.guild_id)
            ).first()
            
            if value.lower() == 'add':
                if existing_admin:
                    await interaction.response.send_message(f"❌ {user.display_name} is already an invite admin!", ephemeral=True)
                    return
                    
                new_admin = InviteAdmin(
                    user_id=str(user.id),
                    server_id=str(interaction.guild_id),
                    added_by=str(interaction.user.id)
                )
                session.add(new_admin)
                session.commit()
                
                await interaction.response.send_message(
                    f"✅ Added {user.display_name} as an invite admin!",
                    ephemeral=True
                )
                
            else:  # remove
                if not existing_admin:
                    await interaction.response.send_message(f"❌ {user.display_name} is not an invite admin!", ephemeral=True)
                    return
                    
                session.delete(existing_admin)
                session.commit()
                
                await interaction.response.send_message(
                    f"✅ Removed {user.display_name} from invite admins!",
                    ephemeral=True
                )
                
        except Exception as e:
            print(f"Error in invite admin: {e}")
            await interaction.response.send_message("❌ An error occurred while managing invite admins.", ephemeral=True)
            session.rollback()
        finally:
            session.close()

    elif action == "resetdb":
        # Reset database (former invitereset)
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only administrators can reset the invite database!", ephemeral=True)
            return
            
        await interaction.response.defer(ephemeral=True)
        try:
            Base.metadata.drop_all(bind=get_engine(str(interaction.guild_id)), tables=[
                InviteTracker.__table__,
                InviteJoin.__table__,
                InviteStats.__table__,
                InviteAdmin.__table__
            ])
            
            Base.metadata.create_all(bind=get_engine(str(interaction.guild_id)), tables=[
                InviteTracker.__table__,
                InviteJoin.__table__,
                InviteStats.__table__,
                InviteAdmin.__table__
            ])
            
            guild = interaction.guild
            await sync_invite_database(guild)
            await update_invite_cache(guild)
            
            await interaction.followup.send(
                "⚠️ **Invite tracking database reset successfully!**\n"
                "All previous data has been deleted and tables recreated.",
                ephemeral=True
            )
            
        except Exception as e:
            print(f"Error in invite resetdb: {e}")
            await interaction.followup.send(f"❌ An error occurred while resetting database: {str(e)}", ephemeral=True)

def setup_inviter_commands(tree):
    """Add invite tracking commands to the command tree"""
    tree.add_command(invite_command)
    print("✅ Invite tracking commands loaded: /invite [action]")

# Event handlers that need to be called from main.py
async def on_member_join(member):
    """Event handler for member joins"""
    await handle_member_join(member)

async def on_member_remove(member):
    """Event handler for member leaves"""  
    await handle_member_leave(member)

async def on_guild_join(guild):
    """Event handler for when bot joins a guild"""
    print(f"🎉 Joined new guild: {guild.name}")
    await sync_invite_database(guild)
    await update_invite_cache(guild)

async def on_ready():
    """Event handler for bot ready - sync all guilds"""
    if _client:
        print("🔄 Syncing invite data for all guilds...")
        for guild in _client.guilds:
            await sync_invite_database(guild)
            await update_invite_cache(guild)
        print("✅ Invite tracking system ready!")
    else:
        print("⚠️ Client not set up for invite tracking system") 