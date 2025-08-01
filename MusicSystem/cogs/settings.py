"""MIT License

Copyright (c) 2023 - present Vocard Development

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import discord
import voicelink
import psutil
import function as func

from discord import app_commands
from discord.ext import commands
from function import (
    LANGS,
    send,
    update_settings,
    get_settings,
    get_lang,
    time as ctime,
    get_aliases,
    cooldown_check,
    format_bytes
)

from views import DebugView, HelpView, EmbedBuilderView

def status_icon(status: bool) -> str:
    return "✅" if status else "❌"

class Settings(commands.Cog, name="settings"):
    def __init__(self, bot) -> None:
        self.bot: commands.Bot = bot
        self.description = "This category is only available to admin permissions on the server."
    
    @commands.hybrid_group(
        name="settings",
        aliases=get_aliases("settings"),
        invoke_without_command=True
    )
    async def settings(self, ctx: commands.Context):
        view = HelpView(self.bot, ctx.author)
        embed = view.build_embed(self.qualified_name)
        view.response = await send(ctx, embed, view=view)
    
    @settings.command(name="toggle", aliases=get_aliases("toggle"))
    @app_commands.describe(feature="Choose which feature to toggle")
    @app_commands.choices(feature=[
        app_commands.Choice(name="24/7 Mode", value="247"),
        app_commands.Choice(name="Vote System", value="vote"),
        app_commands.Choice(name="Controller", value="controller"),
        app_commands.Choice(name="Controller Messages", value="controller_msg"),
        app_commands.Choice(name="Duplicate Tracks", value="duplicate")
    ])
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def toggle_feature(self, ctx: commands.Context, feature: str):
        "Toggle various music system features on/off"
        settings = await get_settings(ctx.guild.id)
        
        if feature == "247":
            toggle = settings.get('24/7', False)
            await update_settings(ctx.guild.id, {"$set": {'24/7': not toggle}})
            await send(ctx, '247', await get_lang(ctx.guild.id, "enabled" if not toggle else "disabled"))
        
        elif feature == "vote":
            toggle = settings.get('votedisable', True)
            await update_settings(ctx.guild.id, {"$set": {'votedisable': not toggle}})
            await send(ctx, 'bypassVote', await get_lang(ctx.guild.id, "enabled" if not toggle else "disabled"))
        
        elif feature == "controller":
            toggle = not settings.get('controller', True)
            player: voicelink.Player = ctx.guild.voice_client
            if player and toggle is False and player.controller:
                try:
                    await player.controller.delete()
                except:
                    discord.ui.View.from_message(player.controller).stop()
            await update_settings(ctx.guild.id, {"$set": {'controller': toggle}})
            await send(ctx, 'togglecontroller', await get_lang(ctx.guild.id, "enabled" if toggle else "disabled"))
        
        elif feature == "controller_msg":
            toggle = not settings.get('controller_msg', True)
            await update_settings(ctx.guild.id, {"$set": {'controller_msg': toggle}})
            await send(ctx, 'toggleControllerMsg', await get_lang(ctx.guild.id, "enabled" if toggle else "disabled"))
        
        elif feature == "duplicate":
            toggle = not settings.get('duplicateTrack', False)
            player: voicelink.Player = ctx.guild.voice_client
            if player:
                player.queue._allow_duplicate = toggle
            await update_settings(ctx.guild.id, {"$set": {'duplicateTrack': toggle}})
            await send(ctx, "toggleDuplicateTrack", await get_lang(ctx.guild.id, "disabled" if toggle else "enabled"))

    @settings.command(name="set", aliases=get_aliases("set"))
    @app_commands.describe(
        setting="Choose which setting to change",
        value="New value for the setting"
    )
    @app_commands.choices(setting=[
        app_commands.Choice(name="Language", value="language"),
        app_commands.Choice(name="Prefix", value="prefix"),
        app_commands.Choice(name="Volume", value="volume"),
        app_commands.Choice(name="Queue Mode", value="queue"),
        app_commands.Choice(name="DJ Role", value="dj"),
        app_commands.Choice(name="Stage Announce", value="stage")
    ])
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def set_setting(self, ctx: commands.Context, setting: str, value: str = None):
        "Change various music system settings"
        if setting == "language":
            language = value.upper()
            if language not in LANGS:
                return await send(ctx, "languageNotFound")
            await update_settings(ctx.guild.id, {"$set": {'lang': language}})
            await send(ctx, 'changedLanguage', language)
        
        elif setting == "prefix":
            if not self.bot.intents.message_content:
                return await send(ctx, "missingIntents", "MESSAGE_CONTENT", ephemeral=True)
            await update_settings(ctx.guild.id, {"$set": {"prefix": value}})
            await send(ctx, "setPrefix", value, value)
        
        elif setting == "volume":
            try:
                vol = int(value)
                if not 1 <= vol <= 150:
                    raise ValueError
            except ValueError:
                return await send(ctx, "invalidVolume")
            
            player: voicelink.Player = ctx.guild.voice_client
            if player:
                await player.set_volume(vol, ctx.author)
            await update_settings(ctx.guild.id, {"$set": {'volume': vol}})
            await send(ctx, 'setVolume', vol)
        
        elif setting == "queue":
            mode = "FairQueue" if value.lower() == "fairqueue" else "Queue"
            await update_settings(ctx.guild.id, {"$set": {"queueType": mode}})
            await send(ctx, "setqueue", mode)
        
        elif setting == "dj":
            if value.lower() == "none":
                await update_settings(ctx.guild.id, {"$unset": {'dj': None}})
                await send(ctx, 'setDJ', "None")
            else:
                try:
                    role = await commands.RoleConverter().convert(ctx, value)
                    await update_settings(ctx.guild.id, {"$set": {'dj': role.id}})
                    await send(ctx, 'setDJ', f"<@&{role.id}>")
                except:
                    await send(ctx, "invalidRole")
        
        elif setting == "stage":
            await update_settings(ctx.guild.id, {"$set": {'stage_announce_template': value}})
            await send(ctx, "setStageAnnounceTemplate")

    @settings.command(name="view", aliases=get_aliases("view"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def view(self, ctx: commands.Context):
        "Show all the bot settings in your server."
        settings = await get_settings(ctx.guild.id)

        texts = await get_lang(ctx.guild.id, "settingsMenu", "settingsTitle", "settingsValue", "settingsTitle2", "settingsValue2", "settingsTitle3", "settingsPermTitle", "settingsPermValue")
        embed = discord.Embed(color=func.settings.embed_color)
        embed.set_author(name=texts[0].format(ctx.guild.name), icon_url=self.bot.user.display_avatar.url)
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)

        dj_role = ctx.guild.get_role(settings.get('dj', 0))
        embed.add_field(name=texts[1], value=texts[2].format(
            settings.get('prefix', func.settings.bot_prefix) or 'None',
            settings.get('lang', 'EN'),
            settings.get('controller', True),
            dj_role.name if dj_role else 'None',
            settings.get('votedisable', False),
            settings.get('24/7', False),
            settings.get('volume', 100),
            ctime(settings.get('playTime', 0) * 60 * 1000),
            inline=True)
        )
        embed.add_field(name=texts[3], value=texts[4].format(
            settings.get("queueType", "Queue"),
            func.settings.max_queue,
            settings.get("duplicateTrack", True)
        ))

        if stage_template := settings.get("stage_announce_template"):
            embed.add_field(name=texts[5], value=f"```{stage_template}```", inline=False)

        perms = ctx.guild.me.guild_permissions
        embed.add_field(name=texts[6], value=texts[7].format(
                status_icon(perms.administrator),
                status_icon(perms.manage_guild),
                status_icon(perms.manage_channels),
                status_icon(perms.manage_messages)
            ),
            inline=False
        )
        await send(ctx, embed)

    @settings.command(name="customcontroller", aliases=get_aliases("customcontroller"))
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def customcontroller(self, ctx: commands.Context):
        "Customizes music controller embeds."
        settings = await get_settings(ctx.guild.id)
        controller_settings = settings.get("default_controller", func.settings.controller)

        view = EmbedBuilderView(ctx, controller_settings.get("embeds").copy())
        view.response = await send(ctx, view.build_embed(), view=view)

    @settings.command(name="setupchannel", aliases=get_aliases("setupchannel"))
    @app_commands.describe(
        channel="Provide a request channel. If not, a text channel will be generated."
    )
    @commands.has_permissions(manage_guild=True)
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.guild)
    async def setupchannel(self, ctx: commands.Context, channel: discord.TextChannel = None) -> None:
        "Sets up a dedicated channel for song requests in your server."
        if not self.bot.intents.message_content:
            return await send(ctx, "missingIntents", "MESSAGE_CONTENT", ephemeral=True)
        
        if not channel:
            try:
                overwrites = {
                    ctx.guild.me: discord.PermissionOverwrite(
                        read_messages=True,
                        manage_messages=True
                    )
                }
                channel = await ctx.guild.create_text_channel("vocard-song-requests", overwrites=overwrites)
            except:
                return await send(ctx, "noCreatePermission")

        channel_perms = channel.permissions_for(ctx.me)
        if not channel_perms.text() and not channel_perms.manage_messages:
            return await send(ctx, "noCreatePermission")
        
        settings = await func.get_settings(ctx.guild.id)
        controller = settings.get("default_controller", func.settings.controller).get("embeds", {}).get("inactive", {})        
        message = await channel.send(embed=voicelink.build_embed(controller, voicelink.Placeholders(self.bot)))

        await update_settings(ctx.guild.id, {"$set": {'music_request_channel': {
            "text_channel_id": channel.id,
            "controller_msg_id": message.id,
        }}})
        await send(ctx, "createSongRequestChannel", channel.mention)

    @app_commands.command(name="debug")
    async def debug(self, interaction: discord.Interaction):
        if interaction.user.id not in func.settings.bot_access_user:
            return await interaction.response.send_message("You are not able to use this command!")

        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(func.ROOT_DIR)

        available_memory, total_memory = memory.available, memory.total
        used_disk_space, total_disk_space = disk.used, disk.total
        embed = discord.Embed(title="📄 Debug Panel", color=func.settings.embed_color)
        embed.description = "```==    System Info    ==\n" \
                            f"• CPU:     {psutil.cpu_freq().current}Mhz ({psutil.cpu_percent()}%)\n" \
                            f"• RAM:     {format_bytes(total_memory - available_memory)}/{format_bytes(total_memory, True)} ({memory.percent}%)\n" \
                            f"• DISK:    {format_bytes(total_disk_space - used_disk_space)}/{format_bytes(total_disk_space, True)} ({disk.percent}%)```"

        embed.add_field(
            name="🤖 Bot Information",
            value=f"```• VERSION: {func.settings.version}\n" \
                  f"• LATENCY: {self.bot.latency:.2f}ms\n" \
                  f"• GUILDS:  {len(self.bot.guilds)}\n" \
                  f"• USERS:   {sum([guild.member_count or 0 for guild in self.bot.guilds])}\n" \
                  f"• PLAYERS: {len(self.bot.voice_clients)}```",
            inline=False
        )

        node: voicelink.Node
        for name, node in voicelink.NodePool._nodes.items():
            if node._available:
                total_memory = node.stats.used + node.stats.free
                embed.add_field(
                    name=f"{name} Node - 🟢 Connected",
                    value=f"```• ADDRESS: {node._host}:{node._port}\n" \
                        f"• PLAYERS: {len(node._players)}\n" \
                        f"• CPU:     {node.stats.cpu_process_load:.1f}%\n" \
                        f"• RAM:     {format_bytes(node.stats.free)}/{format_bytes(total_memory, True)} ({(node.stats.free/total_memory) * 100:.1f}%)\n"
                        f"• LATENCY: {node.latency:.2f}ms\n" \
                        f"• UPTIME:  {func.time(node.stats.uptime)}```"
                )
            else:
                embed.add_field(
                    name=f"{name} Node - 🔴 Disconnected",
                    value=f"```• ADDRESS: {node._host}:{node._port}\n" \
                        f"• PLAYERS: {len(node._players)}\nNo extra data is available for display```",
                )

        await interaction.response.send_message(embed=embed, view=DebugView(self.bot), ephemeral=True)

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Settings(bot))
