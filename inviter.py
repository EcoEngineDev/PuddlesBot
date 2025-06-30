import discord
from discord import app_commands
from discord.app_commands import checks
import functools
from typing import Callable, Any, Optional
import traceback
from datetime import datetime
from database import get_session
import sqlalchemy
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, desc, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

# Store reference to the client
_client = None

def setup_inviter_system(client):
    """Initialize the invite tracking system with client reference"""
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
    
    # Relationships
    joins = relationship("InviteJoin", back_populates="invite", cascade="all, delete-orphan")

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
    
    # Relationships
    invite = relationship("InviteTracker", back_populates="joins")

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

# Create tables
def init_invite_tables():
    """Initialize invite tracking tables"""
    try:
        from database import engine
        Base.metadata.create_all(engine)
        print("✅ Invite tracking tables initialized")
    except Exception as e:
        print(f"❌ Error initializing invite tracking tables: {e}")

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
    session = get_session()
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
    finally:
        session.close()

async def handle_member_join(member):
    """Handle when a member joins - detect which invite was used"""
    guild = member.guild
    session = get_session()
    
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
                    net_invites=1
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
    finally:
        session.close()

async def handle_member_leave(member):
    """Handle when a member leaves - update leave statistics"""
    guild = member.guild
    session = get_session()
    
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
                inviter = await _client.fetch_user(int(join_record.inviter_id))
                inviter_name = inviter.display_name if inviter else "Unknown"
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

# Commands

@app_commands.command(
    name="topinvite",
    description="Show the top 10 inviters in this server"
)
@log_command
async def topinvite(interaction: discord.Interaction):
    """Show top inviters with their statistics"""
    session = get_session()
    try:
        # Get top 10 inviters by net invites
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
                user = await _client.fetch_user(int(stats.inviter_id))
                username = user.display_name if user else f"Unknown User (ID: {stats.inviter_id})"
            except:
                username = f"Unknown User (ID: {stats.inviter_id})"
            
            # Determine emoji based on ranking
            if i == 1:
                emoji = "🥇"
            elif i == 2:
                emoji = "🥈"
            elif i == 3:
                emoji = "🥉"
            else:
                emoji = f"{i}."
            
            embed.add_field(
                name=f"{emoji} {username}",
                value=f"**Invites:** {stats.total_invites}\n"
                      f"**Leaves:** {stats.total_leaves}\n"
                      f"**Net:** {stats.net_invites}",
                inline=True
            )
        
        # Add server totals
        total_invites = sum(s.total_invites for s in top_inviters)
        total_leaves = sum(s.total_leaves for s in top_inviters)
        total_net = sum(s.net_invites for s in top_inviters)
        
        embed.add_field(
            name="📈 Server Totals",
            value=f"**Total Invites:** {total_invites}\n"
                  f"**Total Leaves:** {total_leaves}\n"
                  f"**Net Invites:** {total_net}",
            inline=False
        )
        
        embed.set_footer(text="💡 Net Invites = Total Invites - People Who Left")
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        print(f"Error in topinvite command: {e}")
        await interaction.response.send_message(
            "❌ An error occurred while fetching invite statistics.",
            ephemeral=True
        )
    finally:
        session.close()

@app_commands.command(
    name="showinvites",
    description="Show invite statistics for a specific user"
)
@app_commands.describe(
    user="The user to show invite statistics for"
)
@log_command
async def showinvites(interaction: discord.Interaction, user: discord.Member):
    """Show detailed invite statistics for a specific user"""
    session = get_session()
    try:
        # Get user's invite stats
        stats = session.query(InviteStats).filter_by(
            guild_id=str(interaction.guild_id),
            inviter_id=str(user.id)
        ).first()
        
        if not stats:
            await interaction.response.send_message(
                f"📊 No invite data found for {user.display_name}.\n"
                f"They haven't invited anyone to this server yet, or invite tracking started after their invites.",
                ephemeral=True
            )
            return
        
        # Get detailed join information
        joins = session.query(InviteJoin).filter_by(
            guild_id=str(interaction.guild_id),
            inviter_id=str(user.id)
        ).order_by(desc(InviteJoin.joined_at)).limit(10).all()
        
        embed = discord.Embed(
            title=f"📊 Invite Statistics for {user.display_name}",
            color=discord.Color.blue()
        )
        
        embed.set_thumbnail(url=user.display_avatar.url)
        
        # Main statistics
        embed.add_field(
            name="📈 Overview",
            value=f"**Total Invites:** {stats.total_invites}\n"
                  f"**People Left:** {stats.total_leaves}\n"
                  f"**Net Invites:** {stats.net_invites}",
            inline=True
        )
        
        # Calculate retention rate
        if stats.total_invites > 0:
            retention_rate = ((stats.total_invites - stats.total_leaves) / stats.total_invites) * 100
            embed.add_field(
                name="📊 Retention Rate",
                value=f"**{retention_rate:.1f}%**\n"
                      f"({stats.total_invites - stats.total_leaves} stayed)",
                inline=True
            )
        
        embed.add_field(
            name="🕒 Last Updated",
            value=f"<t:{int(stats.last_updated.timestamp())}:R>",
            inline=True
        )
        
        # Recent invites
        if joins:
            recent_list = []
            for join in joins[:5]:  # Show 5 most recent
                try:
                    invited_user = await _client.fetch_user(int(join.user_id))
                    user_name = invited_user.display_name if invited_user else "Unknown"
                except:
                    user_name = f"User ID: {join.user_id}"
                
                status = "✅ Still here" if not join.has_left else f"❌ Left <t:{int(join.left_at.timestamp())}:R>"
                recent_list.append(f"**{user_name}** - <t:{int(join.joined_at.timestamp())}:R>\n{status}")
            
            embed.add_field(
                name="🕐 Recent Invites",
                value="\n\n".join(recent_list),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        print(f"Error in showinvites command: {e}")
        await interaction.response.send_message(
            "❌ An error occurred while fetching invite statistics.",
            ephemeral=True
        )
    finally:
        session.close()

@app_commands.command(
    name="invitesync",
    description="Manually sync invite data (Admin only)"
)
@checks.has_permissions(administrator=True)
@log_command
async def invitesync(interaction: discord.Interaction):
    """Manually sync invite data for the current server"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        guild = interaction.guild
        await sync_invite_database(guild)
        await update_invite_cache(guild)
        
        await interaction.followup.send(
            "✅ Invite data synchronized successfully!\n"
            "The bot will now track new invites and joins.",
            ephemeral=True
        )
        
    except Exception as e:
        print(f"Error in invitesync command: {e}")
        await interaction.followup.send(
            f"❌ An error occurred while syncing invite data: {str(e)}",
            ephemeral=True
        )

@app_commands.command(
    name="invitestats",
    description="Show overall server invite statistics (Admin only)"
)
@checks.has_permissions(administrator=True)
@log_command
async def invitestats(interaction: discord.Interaction):
    """Show comprehensive server invite statistics"""
    session = get_session()
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
            description=f"Comprehensive invite data for **{interaction.guild.name}**",
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
        
        # Calculate retention rate
        if total_stats.total_invites and total_stats.total_invites > 0:
            retention_rate = ((total_stats.total_invites - total_stats.total_leaves) / total_stats.total_invites) * 100
            embed.add_field(
                name="📊 Server Retention",
                value=f"**{retention_rate:.1f}%**",
                inline=True
            )
        
        embed.set_footer(text="💡 Use /topinvite to see individual user rankings")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    except Exception as e:
        print(f"Error in invitestats command: {e}")
        await interaction.response.send_message(
            "❌ An error occurred while fetching server statistics.",
            ephemeral=True
        )
    finally:
        session.close()

def setup_inviter_commands(tree):
    """Add invite tracking commands to the command tree"""
    tree.add_command(topinvite)
    tree.add_command(showinvites)
    tree.add_command(invitesync)
    tree.add_command(invitestats)
    print("✅ Invite tracking commands loaded: /topinvite, /showinvites, /invitesync, /invitestats")

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

# Initialize database tables when module is imported
init_invite_tables() 