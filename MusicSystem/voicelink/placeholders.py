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

from __future__ import annotations

import re
import function as func
import logging

from discord import Embed, Client

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .player import Player
    from .objects import Track

def ensure_track(func) -> callable:
    def wrapper(self: Placeholders, *args, **kwargs):
        current = self.get_current()
        if not current:
            return "None"
        return func(self, current, *args, **kwargs)
    return wrapper

class Placeholders:
    def __init__(self, bot: Client, player: Player = None) -> None:
        self.bot: Client = bot
        self.player: Player = player

        self.variables = {
            "channel_name": self.channel_name,
            "track_name": self.track_name,
            "track_url": self.track_url,
            "track_author": self.track_author,
            "track_duration": self.track_duration,
            "track_thumbnail": self.track_thumbnail,
            "track_color": self.track_color,
            "track_requester_id": self.track_requester_id,
            "track_requester_name": self.track_requester_name,
            "track_requester_mention": self.track_requester_mention,
            "track_requester_avatar": self.track_requester_avatar,
            "track_source_name": self.track_source_name,
            "track_source_emoji": self.track_source_emoji,
            "queue_length": self.queue_length,
            "volume": self.volume,
            "dj": self.dj,
            "loop_mode": self.loop_mode,
            "default_embed_color": self.default_embed_color,
            "bot_icon": self.bot_icon,
            "server_invite_link": func.settings.invite_link,
            "invite_link": f"https://discord.com/oauth2/authorize?client_id={self.bot.user.id}&permissions=2184260928&scope=bot%20applications.commands"
        }
        
    def get_current(self) -> Track:
        return self.player.current if self.player else None

    def channel_name(self) -> str:
        if not self.player:
            return "None"
        return self.player.channel.name if self.player.channel else "None"
    
    @ensure_track
    def track_name(self, track: Track) -> str:
        return track.title

    @ensure_track
    def track_url(self, track: Track) -> str:
        return track.uri
    
    @ensure_track
    def track_author(self, track: Track) -> str:
        return track.author

    @ensure_track
    def track_duration(self, track: Track) -> str:
        return self.player.get_msg("live") if track.is_stream else func.time(track.length)
    
    @ensure_track
    def track_requester_id(self, track: Track) -> str:
        return str(track.requester.id if track.requester else self.bot.user.id)
    
    @ensure_track
    def track_requester_name(self, track: Track) -> str:
        return track.requester.name if track.requester else self.bot.user.display_name
    
    @ensure_track
    def track_requester_mention(self, track: Track) -> str:
        return f"<@{track.requester.id if track.requester else self.bot.user.id}>"
    
    @ensure_track
    def track_requester_avatar(self, track: Track) -> str:
        return track.requester.display_avatar.url if track.requester else self.bot.user.display_avatar.url
    
    @ensure_track
    def track_color(self, track: Track) -> int:
        return int(func.get_source(track.source, "color"), 16)
    
    @ensure_track
    def track_source_name(self, track: Track) -> str:
        return track.source
    
    @ensure_track
    def track_source_emoji(self, track: Track) -> str:
        return track.emoji
    
    def track_thumbnail(self) -> str:
        if not self.player or not self.player.current:
            return "https://i.imgur.com/dIFBwU7.png"
        
        return self.player.current.thumbnail or "https://cdn.discordapp.com/attachments/674788144931012638/823086668445384704/eq-dribbble.gif"

    def queue_length(self) -> str:
        return str(self.player.queue.count) if self.player else "0"
    
    def dj(self) -> str:
        if not self.player:
            return self.bot.user.mention
        
        if dj_id := self.player.settings.get("dj"):
            return f"<@&{dj_id}>"
        
        return self.player.dj.mention

    def volume(self) -> int:
        return self.player.volume if self.player else 0

    def loop_mode(self) -> str:
        return self.player.queue.repeat if self.player else "Off"

    def default_embed_color(self) -> int:
        return func.settings.embed_color

    def bot_icon(self) -> str:
        return self.bot.user.display_avatar.url if self.player else "https://i.imgur.com/dIFBwU7.png"
        
    def replace(self, text: str, variables: dict[str, str]) -> str:
        if not text or text.isspace(): return
        pattern = r"\{\{(.*?)\}\}"
        matches: list[str] = re.findall(pattern, text)

        for match in matches:
            parts: list[str] = match.split("??")
            expression = parts[0].strip()
            true_value, false_value = "", ""

            # Split the true and false values
            if "//" in parts[1]:
                true_value, false_value = [part.strip() for part in parts[1].split("//")]
            else:
                true_value = parts[1].strip()

            try:
                # Replace variable placeholders with their values
                expression = re.sub(r'@@(.*?)@@', lambda x: "'" + variables.get(x.group(1), '') + "'", expression)
                expression = re.sub(r"'(\d+)'", lambda x: str(int(x.group(1))), expression)
                expression = re.sub(r"'(\d+)'\s*([><=!]+)\s*(\d+)", lambda x: f"{int(x.group(1))} {x.group(2)} {int(x.group(3))}", expression)

                # Convert JSON-style booleans to Python booleans
                expression = expression.replace('false', 'False').replace('true', 'True')

                # Evaluate the expression
                result = eval(expression, {"__builtins__": None}, variables)

                # Replace the match with the true or false value based on the result
                replacement = true_value if result else false_value
                text = text.replace("{{" + match + "}}", replacement)

            except:
                text = text.replace("{{" + match + "}}", "")

        text = re.sub(r'@@(.*?)@@', lambda x: str(variables.get(x.group(1), '')), text)
        return text
    
def build_embed(raw: dict[str, dict], placeholder: Placeholders) -> Embed:
    logger = logging.getLogger("vocard.embed")
    embed = Embed()
    try:
        rv = {key: func() if callable(func) else func for key, func in placeholder.variables.items()}
        
        # Description - Handle this first to ensure it's always set
        try:
            desc = placeholder.replace(raw.get("description", ""), rv)
            if not desc or not isinstance(desc, str) or desc.isspace():
                desc = "No description available"  # More meaningful default
            embed.description = desc
        except Exception as e:
            logger.warning(f"Failed to set embed description: {e}")
            embed.description = "No description available"  # Fallback on error
        
        # Author
        if author := raw.get("author"):
            try:
                name = placeholder.replace(author.get("name", ""), rv) or " "
                url = placeholder.replace(author.get("url", ""), rv) or discord.Embed.Empty
                icon_url = placeholder.replace(author.get("icon_url", ""), rv) or discord.Embed.Empty
                embed.set_author(name=name, url=url, icon_url=icon_url)
            except Exception as e:
                logger.warning(f"Failed to set embed author: {e}")

        # Title
        if title := raw.get("title"):
            try:
                embed.title = placeholder.replace(title.get("name", ""), rv) or " "
                embed.url = placeholder.replace(title.get("url", ""), rv) or discord.Embed.Empty
            except Exception as e:
                logger.warning(f"Failed to set embed title: {e}")

        # Fields
        if fields := raw.get("fields", []):
            for f in fields:
                try:
                    name = placeholder.replace(f.get("name", ""), rv) or " "
                    value = placeholder.replace(f.get("value", ""), rv) or " "
                    inline = f.get("inline", False)
                    embed.add_field(name=name, value=value, inline=inline)
                except Exception as e:
                    logger.warning(f"Failed to add embed field: {e}")

        # Footer
        if footer := raw.get("footer"):
            try:
                text = placeholder.replace(footer.get("text", ""), rv) or " "
                icon_url = placeholder.replace(footer.get("icon_url", ""), rv) or discord.Embed.Empty
                embed.set_footer(text=text, icon_url=icon_url)
            except Exception as e:
                logger.warning(f"Failed to set embed footer: {e}")

        # Thumbnail
        if thumbnail := raw.get("thumbnail"):
            try:
                url = placeholder.replace(thumbnail, rv) or discord.Embed.Empty
                embed.set_thumbnail(url=url)
            except Exception as e:
                logger.warning(f"Failed to set embed thumbnail: {e}")

        # Image
        if image := raw.get("image"):
            try:
                url = placeholder.replace(image, rv) or discord.Embed.Empty
                embed.set_image(url=url)
            except Exception as e:
                logger.warning(f"Failed to set embed image: {e}")

        # Color
        try:
            color_val = placeholder.replace(raw.get("color", "0xb3b3b3"), rv)
            if isinstance(color_val, str) and color_val.startswith("0x"):
                embed.color = int(color_val, 16)
            else:
                embed.color = int(color_val) if color_val else 0xb3b3b3
        except Exception as e:
            logger.warning(f"Failed to set embed color: {e}")
            embed.color = 0xb3b3b3

    except Exception as e:
        logger.error(f"Failed to build embed: {e}", exc_info=e)
        # Ensure we have a valid description even if everything else fails
        if not embed.description or not isinstance(embed.description, str) or embed.description.isspace():
            embed.description = "An error occurred while building the embed"
        if not embed.color:
            embed.color = 0xb3b3b3

    # Final validation before returning
    if not embed.description or not isinstance(embed.description, str) or embed.description.isspace():
        embed.description = "No description available"
    
    return embed