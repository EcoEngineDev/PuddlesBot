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
        # Get server language
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        # Try to resolve as channel first
        guild = interaction.guild
        member = interaction.user
        channel = discord.utils.get(guild.voice_channels, name=channel_or_user)
        if channel:
            if member.voice:
                await member.move_to(channel)
                moved_msg = language.get_text("moveme_moved_to", user_lang, channel=channel.mention)
                await interaction.response.send_message(moved_msg, ephemeral=True)
            else:
                not_in_voice = language.get_text("moveme_not_in_voice", user_lang)
                await interaction.response.send_message(not_in_voice, ephemeral=True)
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
                moved_msg = language.get_text("moveme_moved_to", user_lang, channel=user.voice.channel.mention)
                await interaction.response.send_message(moved_msg, ephemeral=True)
            else:
                not_in_voice = language.get_text("moveme_not_in_voice", user_lang)
                await interaction.response.send_message(not_in_voice, ephemeral=True)
        else:
            channel_not_found = language.get_text("moveme_channel_not_found", user_lang)
            await interaction.response.send_message(channel_not_found, ephemeral=True)

    @app_commands.command(name="profile", description="View your or someone else's customizable personal global profile card.")
    @app_commands.describe(user="User to view profile for")
    async def profile(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        user = user or interaction.user
        embed = discord.Embed(title=language.get_text("profile_title_with_name", user_lang, user_name=user.display_name), color=discord.Color.blue())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name=language.get_text("profile_user_id", user_lang), value=user.id, inline=True)
        embed.add_field(name=language.get_text("profile_account_created", user_lang), value=user.created_at.strftime('%Y-%m-%d'), inline=True)
        embed.add_field(name=language.get_text("profile_joined_server", user_lang), value=user.joined_at.strftime('%Y-%m-%d') if user.joined_at else language.get_text("profile_na", user_lang), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="user", description="Shows information, such as ID and join date, about yourself or a user.")
    @app_commands.describe(user="User to show info for")
    async def user(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        user = user or interaction.user
        embed = discord.Embed(title=language.get_text("user_info_title", user_lang, user_name=user.display_name), color=discord.Color.green())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name=language.get_text("user_id", user_lang), value=user.id, inline=True)
        embed.add_field(name=language.get_text("user_account_created", user_lang), value=user.created_at.strftime('%Y-%m-%d'), inline=True)
        embed.add_field(name=language.get_text("user_joined_server", user_lang), value=user.joined_at.strftime('%Y-%m-%d') if user.joined_at else language.get_text("user_na", user_lang), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="avatar", description="Get a user's avatar.")
    @app_commands.describe(user="User to get avatar for")
    async def avatar(self, interaction: discord.Interaction, user: Optional[discord.Member] = None):
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        user = user or interaction.user
        embed = discord.Embed(title=language.get_text("avatar_title", user_lang, user_name=user.display_name), color=discord.Color.purple())
        embed.set_image(url=user.display_avatar.url)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="server", description="Shows information about the server.")
    async def server(self, interaction: discord.Interaction):
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        guild = interaction.guild
        embed = discord.Embed(title=language.get_text("server_info_title", user_lang, server_name=guild.name), color=discord.Color.blurple())
        embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
        embed.add_field(name=language.get_text("server_id", user_lang), value=guild.id, inline=True)
        embed.add_field(name=language.get_text("server_owner", user_lang), value=guild.owner.mention if guild.owner else language.get_text("server_na", user_lang), inline=True)
        embed.add_field(name=language.get_text("server_created_at", user_lang), value=guild.created_at.strftime('%Y-%m-%d'), inline=True)
        embed.add_field(name=language.get_text("server_members", user_lang), value=guild.member_count, inline=True)
        embed.add_field(name=language.get_text("server_channels", user_lang), value=len(guild.channels), inline=True)
        embed.add_field(name=language.get_text("server_roles", user_lang), value=len(guild.roles), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="roles", description="Get a list of server roles and member counts.")
    async def roles(self, interaction: discord.Interaction):
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        guild = interaction.guild
        roles = [role for role in guild.roles if not role.is_default()]
        roles = sorted(roles, key=lambda r: r.position, reverse=True)
        
        # Create role list as text instead of fields to avoid 25 field limit
        role_text = ""
        for role in roles:
            role_text += f"**{role.name}** - {len(role.members)} {language.get_text('roles_members', user_lang)}\n"
        
        # Split into multiple embeds if the text is too long (Discord description limit is 4096 characters)
        if len(role_text) > 4000:
            # Split roles into chunks
            chunks = []
            current_chunk = ""
            for role in roles:
                role_line = f"**{role.name}** - {len(role.members)} {language.get_text('roles_members', user_lang)}\n"
                if len(current_chunk + role_line) > 4000:
                    chunks.append(current_chunk)
                    current_chunk = role_line
                else:
                    current_chunk += role_line
            if current_chunk:
                chunks.append(current_chunk)
            
            # Send first embed with note about multiple pages
            embed = discord.Embed(
                title=language.get_text("roles_title_page", user_lang, total_roles=len(roles), current_page=1, total_pages=len(chunks)), 
                description=chunks[0],
                color=discord.Color.teal()
            )
            embed.set_footer(text=language.get_text("roles_showing_page", user_lang, showing_roles=len(chunks[0].split(chr(10)))-1, total_roles=len(roles)))
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
            # Send remaining embeds as followups
            for i, chunk in enumerate(chunks[1:], 2):
                embed = discord.Embed(
                    title=language.get_text("roles_title_page_simple", user_lang, current_page=i, total_pages=len(chunks)), 
                    description=chunk,
                    color=discord.Color.teal()
                )
                embed.set_footer(text=language.get_text("roles_showing_more", user_lang, showing_roles=len(chunk.split(chr(10)))-1))
                await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            # Single embed is sufficient
            embed = discord.Embed(
                title=language.get_text("roles_title", user_lang, total_roles=len(roles)), 
                description=role_text or language.get_text("roles_no_custom_roles", user_lang),
                color=discord.Color.teal()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="ban", description="Bans a member.")
    @app_commands.describe(user="User to ban", time="Ban duration (m/h/d/mo/y)", reason="Reason for ban")
    async def ban(self, interaction: discord.Interaction, user: discord.Member, time: Optional[str] = None, reason: Optional[str] = None):
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message(language.get_text("ban_no_permission", user_lang), ephemeral=True)
            return
        try:
            dm_message = language.get_text("ban_dm_message", user_lang, server_name=interaction.guild.name)
            if reason:
                dm_message += language.get_text("ban_dm_reason", user_lang, reason=reason)
            await user.send(dm_message)
        except Exception:
            pass
        await interaction.guild.ban(user, reason=reason)
        ban_message = language.get_text("ban_success", user_lang, user_mention=user.mention)
        if reason:
            ban_message += language.get_text("ban_reason", user_lang, reason=reason)
        await interaction.response.send_message(ban_message, ephemeral=True)

    @app_commands.command(name="kick", description="Kicks a member.")
    @app_commands.describe(user="User to kick", reason="Reason for kick")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: Optional[str] = None):
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message(language.get_text("kick_no_permission", user_lang), ephemeral=True)
            return
        try:
            dm_message = language.get_text("kick_dm_message", user_lang, server_name=interaction.guild.name)
            if reason:
                dm_message += language.get_text("kick_dm_reason", user_lang, reason=reason)
            await user.send(dm_message)
        except Exception:
            pass
        await interaction.guild.kick(user, reason=reason)
        kick_message = language.get_text("kick_success", user_lang, user_mention=user.mention)
        if reason:
            kick_message += language.get_text("kick_reason", user_lang, reason=reason)
        await interaction.response.send_message(kick_message, ephemeral=True)

    @app_commands.command(name="purge", description="Cleans up channel messages.")
    @app_commands.describe(
        number="Number of messages to delete (default 100)",
        user="User to clear messages for",
        bots="Clear only bot messages (yes/no)"
    )
    async def purge(self, interaction: discord.Interaction, number: Optional[int] = 100, user: Optional[discord.Member] = None, bots: Optional[str] = None):
        import language
        user_lang = language.get_server_language(interaction.guild_id)
        
        if not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message(language.get_text("purge_no_permission", user_lang), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        def check(msg):
            if user:
                return msg.author.id == user.id
            if bots and bots.lower() in ("yes", "y", "true", "1"):
                return msg.author.bot
            return True
        deleted = await interaction.channel.purge(limit=number, check=check, bulk=True)
        await interaction.followup.send(language.get_text("purge_success", user_lang, deleted_count=len(deleted)), ephemeral=True)

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