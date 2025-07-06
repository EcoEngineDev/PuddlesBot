import discord
from discord import app_commands
from discord.ext import commands
from typing import Optional, Union
import asyncio

class Utils(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="moveme", description="Moves you to another voice channel.")
    @app_commands.describe(channel_or_user="Channel name or user to move to")
    async def moveme(self, interaction: discord.Interaction, channel_or_user: str):
        # Try to resolve as channel first
        guild = interaction.guild
        member = interaction.user
        channel = discord.utils.get(guild.voice_channels, name=channel_or_user)
        if channel:
            if member.voice:
                await member.move_to(channel)
                await interaction.response.send_message(f"Moved you to {channel.mention}", ephemeral=True)
            else:
                await interaction.response.send_message("You are not in a voice channel!", ephemeral=True)
            return
        # Try to resolve as user
        user = None
        if channel_or_user.startswith("<@") and channel_or_user.endswith(">"):
            user_id = int(channel_or_user.replace("<@", "").replace(">", "").replace("!", ""))
            user = guild.get_member(user_id)
        else:
            try:
                user = await guild.fetch_member(int(channel_or_user))
            except:
                user = discord.utils.get(guild.members, name=channel_or_user)
        if user and user.voice and user.voice.channel:
            if member.voice:
                await member.move_to(user.voice.channel)
                await interaction.response.send_message(f"Moved you to {user.voice.channel.mention}", ephemeral=True)
            else:
                await interaction.response.send_message("You are not in a voice channel!", ephemeral=True)
        else:
            await interaction.response.send_message("Could not find a valid channel or user in a voice channel.", ephemeral=True)

    @app_commands.command(name="profile", description="View your or someone else's customizable personal global profile card.")
    @app_commands.describe(user="User to view profile for")
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        user = user or interaction.user
        embed = discord.Embed(title=f"Profile: {user.display_name}", color=discord.Color.blue())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User ID", value=user.id, inline=True)
        embed.add_field(name="Account Created", value=user.created_at.strftime('%Y-%m-%d'), inline=True)
        embed.add_field(name="Joined Server", value=user.joined_at.strftime('%Y-%m-%d') if user.joined_at else "N/A", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="user", description="Shows information, such as ID and join date, about yourself or a user.")
    @app_commands.describe(user="User to show info for")
    async def user(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        user = user or interaction.user
        embed = discord.Embed(title=f"User Info: {user.display_name}", color=discord.Color.green())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User ID", value=user.id, inline=True)
        embed.add_field(name="Account Created", value=user.created_at.strftime('%Y-%m-%d'), inline=True)
        embed.add_field(name="Joined Server", value=user.joined_at.strftime('%Y-%m-%d') if user.joined_at else "N/A", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="avatar", description="Get a user's avatar.")
    @app_commands.describe(user="User to get avatar for")
    async def avatar(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        user = user or interaction.user
        embed = discord.Embed(title=f"Avatar: {user.display_name}", color=discord.Color.purple())
        embed.set_image(url=user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="server", description="Shows information about the server.")
    async def server(self, interaction: discord.Interaction):
        guild = interaction.guild
        embed = discord.Embed(title=f"Server Info: {guild.name}", color=discord.Color.blurple())
        embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
        embed.add_field(name="Server ID", value=guild.id, inline=True)
        embed.add_field(name="Owner", value=guild.owner.mention if guild.owner else "N/A", inline=True)
        embed.add_field(name="Created At", value=guild.created_at.strftime('%Y-%m-%d'), inline=True)
        embed.add_field(name="Members", value=guild.member_count, inline=True)
        embed.add_field(name="Channels", value=len(guild.channels), inline=True)
        embed.add_field(name="Roles", value=len(guild.roles), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="roles", description="Get a list of server roles and member counts.")
    async def roles(self, interaction: discord.Interaction):
        guild = interaction.guild
        roles = [role for role in guild.roles if not role.is_default()]
        roles = sorted(roles, key=lambda r: r.position, reverse=True)
        
        # Create role list as text instead of fields to avoid 25 field limit
        role_text = ""
        for role in roles:
            role_text += f"**{role.name}** - {len(role.members)} members\n"
        
        # Split into multiple embeds if the text is too long (Discord description limit is 4096 characters)
        if len(role_text) > 4000:
            # Split roles into chunks
            chunks = []
            current_chunk = ""
            for role in roles:
                role_line = f"**{role.name}** - {len(role.members)} members\n"
                if len(current_chunk + role_line) > 4000:
                    chunks.append(current_chunk)
                    current_chunk = role_line
                else:
                    current_chunk += role_line
            if current_chunk:
                chunks.append(current_chunk)
            
            # Send first embed with note about multiple pages
            embed = discord.Embed(
                title=f"Server Roles ({len(roles)} total) - Page 1/{len(chunks)}", 
                description=chunks[0],
                color=discord.Color.teal()
            )
            embed.set_footer(text=f"Showing {len(chunks[0].split(chr(10)))-1} of {len(roles)} roles")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Send remaining embeds as followups
            for i, chunk in enumerate(chunks[1:], 2):
                embed = discord.Embed(
                    title=f"Server Roles - Page {i}/{len(chunks)}", 
                    description=chunk,
                    color=discord.Color.teal()
                )
                embed.set_footer(text=f"Showing {len(chunk.split(chr(10)))-1} more roles")
                await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # Single embed is sufficient
            embed = discord.Embed(
                title=f"Server Roles ({len(roles)} total)", 
                description=role_text or "No custom roles found.",
                color=discord.Color.teal()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ban", description="Bans a member.")
    @app_commands.describe(user="User to ban", time="Ban duration (m/h/d/mo/y)", reason="Reason for ban")
    async def ban(self, interaction: discord.Interaction, user: discord.Member, time: Optional[str] = None, reason: Optional[str] = None):
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("You do not have permission to ban members.", ephemeral=True)
            return
        try:
            dm_message = f"You have been banned from {interaction.guild.name}."
            if reason:
                dm_message += f"\nReason: {reason}"
            await user.send(dm_message)
        except Exception:
            pass
        await interaction.guild.ban(user, reason=reason)
        await interaction.response.send_message(f"{user.mention} has been banned.{' Reason: ' + reason if reason else ''}", ephemeral=True)

    @app_commands.command(name="kick", description="Kicks a member.")
    @app_commands.describe(user="User to kick", reason="Reason for kick")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message("You do not have permission to kick members.", ephemeral=True)
            return
        try:
            dm_message = f"You have been kicked from {interaction.guild.name}."
            if reason:
                dm_message += f"\nReason: {reason}"
            await user.send(dm_message)
        except Exception:
            pass
        await interaction.guild.kick(user, reason=reason)
        await interaction.response.send_message(f"{user.mention} has been kicked.{' Reason: ' + reason if reason else ''}", ephemeral=True)

    @app_commands.command(name="purge", description="Cleans up channel messages.")
    @app_commands.describe(
        number="Number of messages to delete (default 100)",
        user="User to clear messages for",
        bots="Clear only bot messages (yes/no)"
    )
    async def purge(self, interaction: discord.Interaction, number: Optional[int] = 100, user: Optional[discord.Member] = None, bots: Optional[str] = None):
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("You do not have permission to manage messages.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        def check(msg):
            if user:
                return msg.author.id == user.id
            if bots and bots.lower() in ("yes", "y", "true", "1"):
                return msg.author.bot
            return True
        deleted = await interaction.channel.purge(limit=number, check=check, bulk=True)
        await interaction.followup.send(f"Deleted {len(deleted)} messages.", ephemeral=True)

def setup_utils_commands(tree: app_commands.CommandTree, bot):
    utils_cog = Utils(bot)
    tree.add_command(utils_cog.moveme)
    tree.add_command(utils_cog.profile)
    tree.add_command(utils_cog.user)
    tree.add_command(utils_cog.avatar)
    tree.add_command(utils_cog.server)
    tree.add_command(utils_cog.roles)
    tree.add_command(utils_cog.ban)
    tree.add_command(utils_cog.kick)
    tree.add_command(utils_cog.purge) 