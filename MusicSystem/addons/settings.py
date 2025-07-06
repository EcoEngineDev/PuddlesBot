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

from typing import (
    Dict,
    List,
    Any,
    Union
)

class Settings:
    def __init__(self, settings: Dict) -> None:
        self.token: str = settings.get("token")
        self.client_id: int = int(settings.get("client_id", 0))
        self.genius_token: str = settings.get("genius_token")
        self.mongodb_url: str = settings.get("mongodb_url")
        self.mongodb_name: str = settings.get("mongodb_name")
        
        self.invite_link: str = "https://discord.gg/wRCgB7vBQv"
        
        # Handle nodes with proper boolean conversion
        nodes = settings.get("nodes", {})
        for node in nodes.values():
            if "secure" in node:
                node["secure"] = self._parse_bool(node["secure"])
        self.nodes: Dict[str, Dict[str, Union[str, int, bool]]] = nodes
        
        self.max_queue: int = settings.get("default_max_queue", 1000)
        self.bot_prefix: str = settings.get("prefix", "")
        self.activity: List[Dict[str, str]] = settings.get("activity", [{"listen": "/help"}])
        
        # Handle logging with proper boolean conversion
        logging_settings = settings.get("logging", {})
        if "file" in logging_settings and "enable" in logging_settings["file"]:
            logging_settings["file"]["enable"] = self._parse_bool(logging_settings["file"]["enable"])
        self.logging: Dict[Union[str, Dict[str, Union[str, bool]]]] = logging_settings
        
        self.embed_color: int = int(settings.get("embed_color", "0xb3b3b3"), 16)
        self.bot_access_user: List[int] = settings.get("bot_access_user", [])
        self.sources_settings: Dict[Dict[str, str]] = settings.get("sources_settings", {})
        self.cooldowns_settings: Dict[str, List[int]] = settings.get("cooldowns", {})
        self.aliases_settings: Dict[str, List[str]] = settings.get("aliases", {})
        
        # Handle controller with proper boolean conversion
        controller = settings.get("default_controller", {})
        if "disableButtonText" in controller:
            controller["disableButtonText"] = self._parse_bool(controller["disableButtonText"])
        self.controller: Dict[str, Dict[str, Any]] = controller
        
        self.voice_status_template: str = settings.get("default_voice_status_template", "")
        self.lyrics_platform: str = settings.get("lyrics_platform", "A_ZLyrics").lower()
        
        # Handle IPC client with proper boolean conversion
        ipc_settings = settings.get("ipc_client", {})
        for key in ["enable", "secure"]:
            if key in ipc_settings:
                ipc_settings[key] = self._parse_bool(ipc_settings[key])
        self.ipc_client: Dict[str, Union[str, bool, int]] = ipc_settings
        
        self.version: str = settings.get("version", "")

    def _parse_bool(self, value) -> bool:
        """Convert various boolean representations to Python bool"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 't', 'yes', 'y', 'on', '1')
        if isinstance(value, int):
            return bool(value)
        return False