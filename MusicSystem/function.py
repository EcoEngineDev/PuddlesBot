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

import discord, json, os, copy, logging
import traceback

from discord.ext import commands
from time import strptime
from addons import Settings

from typing import (
    Optional,
    Union,
    Dict,
    Any
)

from motor.motor_asyncio import (
    AsyncIOMotorClient,
    AsyncIOMotorCollection,
)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

if not os.path.exists(os.path.join(ROOT_DIR, "settings.json")):
    raise Exception("Settings file not set!")

#--------------- Cache Var ---------------
settings: Settings = None
logger: logging.Logger = logging.getLogger("vocard")

MONGO_DB = None
SETTINGS_DB = None
USERS_DB = None
LOCAL_LANGS = {}
MISSING_TRANSLATOR = {}

LANGS: dict[str, dict[str, str]] = {} #Stores all the languages in ./langs
SETTINGS_BUFFER: dict[int, dict[str, Any]] = {} #Cache guild language
USERS_BUFFER: dict[str, dict] = {}

USER_BASE: dict[str, Any] = {
    'playlist': {
        '200': {
            'tracks':[],
            'perms': {'read': [], 'write':[], 'remove': []},
            'name':'Favourite',
            'type':'playlist'
        }
    },
    'history': [],
    'inbox':[]
}

ALLOWED_MENTIONS = discord.AllowedMentions().none()
LAST_SESSION_FILE_NAME = "last-session.json"

def load_settings() -> None:
    """Load settings from settings.json file"""
    global settings
    try:
        with open(os.path.join(ROOT_DIR, "settings.json"), encoding="utf8") as f:
            settings_data = json.load(f)
        print("[DEBUG] Loaded settings:", settings_data)
        settings = Settings(settings_data)
    except Exception as e:
        print("[DEBUG] Error loading settings:", e)
        traceback.print_exc()
        settings = Settings({})  # Initialize with empty settings as fallback

#-------------- Vocard Classes --------------
class TempCtx():
    def __init__(self, author: discord.Member, channel: discord.VoiceChannel) -> None:
        self.author: discord.Member = author
        self.channel: discord.VoiceChannel = channel
        self.guild: discord.Guild = channel.guild

#-------------- Vocard Functions --------------
def open_json(path: str) -> dict:
    try:
        with open(os.path.join(ROOT_DIR, path), encoding="utf8") as json_file:
            return json.load(json_file)
    except:
        return {}

def update_json(path: str, new_data: dict) -> None:
    data = open_json(path)
    if not data:
        data = new_data
    else:
        data.update(new_data)

    with open(os.path.join(ROOT_DIR, path), "w") as json_file:
        json.dump(data, json_file, indent=4)

def langs_setup() -> None:
    for language in os.listdir(os.path.join(ROOT_DIR, "langs")):
        if language.endswith('.json'):
            LANGS[language[:-5]] = {}
    
    for language in os.listdir(os.path.join(ROOT_DIR, "local_langs")):
        if language.endswith('.json'):
            LOCAL_LANGS[language[:-5]] = open_json(os.path.join("local_langs", language))

    # Load settings after languages are set up
    load_settings()
    return

def time(millis: int) -> str:
    seconds = (millis // 1000) % 60
    minutes = (millis // (1000 * 60)) % 60
    hours = (millis // (1000 * 60 * 60)) % 24
    days = millis // (1000 * 60 * 60 * 24)

    if days > 0:
        return "%d days, %02d:%02d:%02d" % (days, hours, minutes, seconds)
    elif hours > 0:
        return "%d:%02d:%02d" % (hours, minutes, seconds)
    else:
        return "%02d:%02d" % (minutes, seconds)

def format_time(number:str) -> int:
    try:
        try:
            num = strptime(number, '%M:%S')
        except ValueError:
            try:
                num = strptime(number, '%S')
            except ValueError:
                num = strptime(number, '%H:%M:%S')
    except:
        return 0
    
    return (int(num.tm_hour) * 3600 + int(num.tm_min) * 60 + int(num.tm_sec)) * 1000

def get_source(source: str, type: str) -> str:
    """Get source settings from settings.json"""
    try:
        # Default settings if sources_settings is not defined
        default_settings = {
            'youtube': {'emoji': '🎵', 'color': '0xFF0000'},
            'youtubemusic': {'emoji': '🎵', 'color': '0xFF0000'},
            'spotify': {'emoji': '🎧', 'color': '0x1DB954'},
            'soundcloud': {'emoji': '🔊', 'color': '0xFF7700'},
            'twitch': {'emoji': '📺', 'color': '0x9B4AFF'},
            'bandcamp': {'emoji': '🎼', 'color': '0x6F98A7'},
            'vimeo': {'emoji': '📹', 'color': '0x1ABCEA'},
            'applemusic': {'emoji': '🍎', 'color': '0xE298C4'},
            'reddit': {'emoji': '📱', 'color': '0xFF5700'},
            'tiktok': {'emoji': '📱', 'color': '0x74ECE9'},
            'others': {'emoji': '🔗', 'color': '0xb3b3b3'}
        }
        
        if not hasattr(settings, 'sources_settings'):
            source_settings = default_settings.get(source.lower(), default_settings['others'])
            return source_settings.get(type, default_settings['others'][type])
        
        source_settings = settings.sources_settings.get(source.lower(), settings.sources_settings['others'])
        return source_settings.get(type, settings.sources_settings['others'][type])
    except Exception:
        # Fallback to basic defaults if anything goes wrong
        if type == 'emoji':
            return '🎵'
        return '0xb3b3b3'  # Default color

def cooldown_check(ctx: commands.Context) -> Optional[commands.Cooldown]:
    if ctx.author.id in settings.bot_access_user:
        return None
    cooldown = settings.cooldowns_settings.get(f"{ctx.command.parent.qualified_name} {ctx.command.name}" if ctx.command.parent else ctx.command.name)
    if not cooldown:
        return None
    return commands.Cooldown(cooldown[0], cooldown[1])

def get_aliases(name: str) -> list:
    return settings.aliases_settings.get(name, [])

def check_roles() -> tuple[str, int, int]:
    return 'Normal', 5, 500

def truncate_string(text: str, length: int = 40) -> str:
    return text[:length - 3] + "..." if len(text) > length else text
    
def get_lang_non_async(guild_id: int, *keys) -> Union[list[str], str]:
    settings = SETTINGS_BUFFER.get(guild_id, {})
    lang = settings.get("lang", "EN")
    if lang in LANGS and not LANGS[lang]:
        LANGS[lang] = open_json(os.path.join("langs", f"{lang}.json"))

    if len(keys) == 1:
        return LANGS.get(lang, {}).get(keys[0], "Language pack not found!")
    return [LANGS.get(lang, {}).get(key, "Language pack not found!") for key in keys]

def format_bytes(bytes: int, unit: bool = False):
    if bytes <= 1_000_000_000:
        return f"{bytes / (1024 ** 2):.1f}" + ("MB" if unit else "")
    
    else:
        return f"{bytes / (1024 ** 3):.1f}" + ("GB" if unit else "")
    
async def get_lang(guild_id:int, *keys) -> Optional[Union[list[str], str]]:
    settings = await get_settings(guild_id)
    lang = settings.get("lang", "EN")
    if lang in LANGS and not LANGS[lang]:
        LANGS[lang] = open_json(os.path.join("langs", f"{lang}.json"))

    if len(keys) == 1:
        return LANGS.get(lang, {}).get(keys[0])
    return [LANGS.get(lang, {}).get(key) for key in keys]

async def send(
    ctx: Union[commands.Context, discord.Interaction],
    content: Union[str, discord.Embed] = None,
    *params,
    view: discord.ui.View = None,
    delete_after: float = None,
    ephemeral: bool = False
) -> Optional[discord.Message]:
    try:
        if content is None:
            content = "No content provided."

        # Determine the text to send
        if isinstance(content, discord.Embed):
            embed = content
            text = None
        else:
            try:
                text = await get_lang(ctx.guild.id, content)
                if text:
                    text = text.format(*params)
                else:
                    text = content.format(*params) if params else content
            except Exception as e:
                logger.error(f"Error formatting text in send function: {e}")
                text = content
            embed = None
            
        # Determine the sending function
        send_func = (
            ctx.send if isinstance(ctx, commands.Context) else 
            ctx.response.send_message if not ctx.response.is_done() else 
            ctx.followup.send
        )

        # Send the message
        # Build kwargs and only include optional parameters if they have values
        kwargs = {'ephemeral': ephemeral}
        if view is not None:
            kwargs['view'] = view
        if delete_after is not None:
            kwargs['delete_after'] = delete_after
            
        if embed:
            return await send_func(embed=embed, **kwargs)
        else:
            return await send_func(content=text, **kwargs)

    except Exception as e:
        import traceback
        logger.error(f"Error in send function: {e}")
        print("[DEBUG] Error in send function:", e)
        print("[DEBUG] Content:", content)
        print("[DEBUG] Params:", params)
        traceback.print_exc()
        return None

async def update_db(db: AsyncIOMotorCollection, tempStore: dict, filter: dict, data: dict) -> bool:
    for mode, action in data.items():
        for key, value in action.items():
            cursors = key.split(".")

            nested_data = tempStore
            for c in cursors[:-1]:
                nested_data = nested_data.setdefault(c, {})

            if mode == "$set":
                try:
                    nested_data[cursors[-1]] = value
                except TypeError:
                    nested_data[int(cursors[-1])] = value

            elif mode == "$unset":
                nested_data.pop(cursors[-1], None)

            elif mode == "$inc":
                nested_data[cursors[-1]] = nested_data.get(cursors[-1], 0) + value

            elif mode == "$push":
                if isinstance(value, dict) and "$each" in value:
                    nested_data.setdefault(cursors[-1], []).extend(value["$each"][value.get("$slice", len(value["$each"])):])
                else:
                    nested_data.setdefault(cursors[-1], []).extend([value])
                    
            elif mode == "$push":
                if isinstance(value, dict) and "$each" in value:
                    nested_data.setdefault(cursors[-1], []).extend(value["$each"])
                    nested_data[cursors[-1]] = nested_data[cursors[-1]][value.get("$slice", len(value["$each"])):]
                else:
                    nested_data.setdefault(cursors[-1], []).extend([value])

            elif mode == "$pull":
                if cursors[-1] in nested_data:
                    value = value.get("$in", []) if isinstance(value, dict) else [value]
                    nested_data[cursors[-1]] = [item for item in nested_data[cursors[-1]] if item not in value]
                    
            else:
                return False

    result = await db.update_one(filter, data)
    return result.modified_count > 0

async def get_settings(guild_id: int) -> dict:
    """Get guild settings with fallback to defaults"""
    try:
        if SETTINGS_DB is None:
            # Return default settings if no database
            return {
                "lang": "EN",
                "prefix": "?",
                "dj_role": None,
                "max_volume": 100,
                "vote_skip": True,
                "music_request_channel": None,
                "controller": settings.default_controller if hasattr(settings, 'default_controller') else {
                    "embeds": {
                        "active": {
                            "description": "**Now Playing: ```[@@track_name@@]```\nLink: [Click Me](@@track_url@@) | Requester: @@track_requester_mention@@ | DJ: @@dj@@**",
                            "footer": {
                                "text": "Queue Length: @@queue_length@@ | Duration: @@track_duration@@ | Volume: @@volume@@% {{loop_mode != 'Off' ?? | Repeat: @@loop_mode@@}}"
                            },
                            "image": "@@track_thumbnail@@",
                            "author": {
                                "name": "Music Controller | @@channel_name@@",
                                "icon_url": "@@bot_icon@@"
                            },
                            "color": "@@track_color@@"
                        },
                        "inactive": {
                            "title": {
                                "name": "There are no songs playing right now"
                            },
                            "description": "[Support](@@server_invite_link@@) | [Invite](@@invite_link@@)",
                            "image": "https://i.imgur.com/dIFBwU7.png",
                            "color": "@@default_embed_color@@"
                        }
                    },
                    "default_buttons": [
                        ["back", "resume", "skip", {"stop": "red"}, "add"],
                        ["tracks"]
                    ],
                    "disableButtonText": False
                }
            }
        
        data = await SETTINGS_DB.find_one({"_id": guild_id})
        if not data:
            data = {
                "lang": "EN",
                "prefix": "?",
                "dj_role": None,
                "max_volume": 100,
                "vote_skip": True,
                "music_request_channel": None,
                "controller": settings.default_controller if hasattr(settings, 'default_controller') else {
                    "embeds": {
                        "active": {
                            "description": "**Now Playing: ```[@@track_name@@]```\nLink: [Click Me](@@track_url@@) | Requester: @@track_requester_mention@@ | DJ: @@dj@@**",
                            "footer": {
                                "text": "Queue Length: @@queue_length@@ | Duration: @@track_duration@@ | Volume: @@volume@@% {{loop_mode != 'Off' ?? | Repeat: @@loop_mode@@}}"
                            },
                            "image": "@@track_thumbnail@@",
                            "author": {
                                "name": "Music Controller | @@channel_name@@",
                                "icon_url": "@@bot_icon@@"
                            },
                            "color": "@@track_color@@"
                        },
                        "inactive": {
                            "title": {
                                "name": "There are no songs playing right now"
                            },
                            "description": "[Support](@@server_invite_link@@) | [Invite](@@invite_link@@)",
                            "image": "https://i.imgur.com/dIFBwU7.png",
                            "color": "@@default_embed_color@@"
                        }
                    },
                    "default_buttons": [
                        ["back", "resume", "skip", {"stop": "red"}, "add"],
                        ["tracks"]
                    ],
                    "disableButtonText": False
                }
            }
        return data
    except Exception as e:
        logger.error(f"Error getting settings: {e}")
        return {
            "lang": "EN",
            "prefix": "?",
            "dj_role": None,
            "max_volume": 100,
            "vote_skip": True,
            "music_request_channel": None,
            "controller": settings.default_controller if hasattr(settings, 'default_controller') else {
                "embeds": {
                    "active": {
                        "description": "**Now Playing: ```[@@track_name@@]```\nLink: [Click Me](@@track_url@@) | Requester: @@track_requester_mention@@ | DJ: @@dj@@**",
                        "footer": {
                            "text": "Queue Length: @@queue_length@@ | Duration: @@track_duration@@ | Volume: @@volume@@% {{loop_mode != 'Off' ?? | Repeat: @@loop_mode@@}}"
                        },
                        "image": "@@track_thumbnail@@",
                        "author": {
                            "name": "Music Controller | @@channel_name@@",
                            "icon_url": "@@bot_icon@@"
                        },
                        "color": "@@track_color@@"
                    },
                    "inactive": {
                        "title": {
                            "name": "There are no songs playing right now"
                        },
                        "description": "[Support](@@server_invite_link@@) | [Invite](@@invite_link@@)",
                        "image": "https://i.imgur.com/dIFBwU7.png",
                        "color": "@@default_embed_color@@"
                    }
                },
                "default_buttons": [
                    ["back", "resume", "skip", {"stop": "red"}, "add"],
                    ["tracks"]
                ],
                "disableButtonText": False
            }
        }

async def update_settings(guild_id: int, data: dict[str, dict[str, Any]]) -> bool:
    # Check if database is available
    if SETTINGS_DB is None:
        return False
        
    settings = await get_settings(guild_id)
    return await update_db(SETTINGS_DB, settings, {"_id": guild_id}, data)
            
async def get_user(user_id: int, key: str = None) -> Union[dict, Any]:
    """Get user data with fallback to defaults"""
    try:
        if USERS_DB is None:
            # Return default user data if no database
            default_data = {
                "_id": user_id,
                "history": [],
                "playlists": {},
                "settings": {
                    "notify": True,
                    "vote_skip": True
                }
            }
            return default_data[key] if key else default_data
        
        data = await USERS_DB.find_one({"_id": user_id})
        if not data:
            data = {
                "_id": user_id,
                "history": [],
                "playlists": {},
                "settings": {
                    "notify": True,
                    "vote_skip": True
                }
            }
            await USERS_DB.insert_one(data)
        return data[key] if key else data
    except Exception as e:
        logger.error(f"Error getting user data: {e}")
        default_data = {
            "_id": user_id,
            "history": [],
            "playlists": {},
            "settings": {
                "notify": True,
                "vote_skip": True
            }
        }
        return default_data[key] if key else default_data

async def update_user(user_id:int, data:dict) -> bool:
    # Check if database is available
    if USERS_DB is None:
        return False
        
    playlist = await get_user(user_id, need_copy=False)
    return await update_db(USERS_DB, playlist, {"_id": user_id}, data)