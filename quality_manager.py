import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio
import yaml
from typing import Optional, Literal

class QualityManager:
    """Audio Quality Management System for Vocard Music Bot"""
    
    def __init__(self, bot):
        self.bot = bot
        self.settings_path = os.path.join('MusicSystem', 'settings.json')
        self.quality_presets_path = os.path.join('MusicSystem', 'quality_presets.json')
        self.lavalink_config_path = os.path.join('MusicSystem', 'lavalink', 'application.yml')
        self.load_settings()
    
    def load_settings(self):
        """Load current settings from file"""
        try:
            # Try to load from dedicated quality presets file first
            if os.path.exists(self.quality_presets_path):
                with open(self.quality_presets_path, 'r') as f:
                    content = f.read().strip()
                    if content and not content.isspace():
                        self.settings = json.loads(content)
                        print(f"✅ Quality settings loaded from quality_presets.json: {len(self.settings.get('quality_presets', {}))} presets available")
                        return
            
            # Fallback to main settings file
            if os.path.exists(self.settings_path):
                with open(self.settings_path, 'r') as f:
                    content = f.read().strip()
                    if content and not content.isspace():
                        self.settings = json.loads(content)
                        if 'quality_presets' in self.settings:
                            print(f"✅ Quality settings loaded from settings.json: {len(self.settings.get('quality_presets', {}))} presets available")
                            return
            
            # If no presets found, create default high-quality settings
            print("⚠️ No quality presets found, creating default high-quality configuration...")
            self.settings = self.create_default_settings()
            self.save_settings()
            
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse quality settings JSON: {e}")
            print("💡 Creating default high-quality settings...")
            self.settings = self.create_default_settings()
            self.save_settings()
        except Exception as e:
            print(f"❌ Failed to load quality settings: {e}")
            print("💡 Creating default high-quality settings...")
            self.settings = self.create_default_settings()
            self.save_settings()
    
    def create_default_settings(self):
        """Create default high-quality settings"""
        return {
            "quality_presets": {
                "ultra_high": {
                    "description": "🎵 Ultra High Quality - Maximum audio fidelity with advanced processing",
                    "buffer_size": 1200,
                    "opus_quality": 10,
                    "resampling": "HIGH",
                    "prefer_lossless": True,
                    "frame_buffer_duration": 10000,
                    "track_stuck_threshold": 8000,
                    "player_update_interval": 1,
                    "use_seek_ghosting": True,
                    "non_allocating_frame_buffer": True,
                    "send_player_updates": True,
                    "auto_reconnect": True,
                    "youtube_clients": ["MUSIC", "ANDROID_MUSIC", "ANDROID_VR", "TVHTML5EMBEDDED"],
                    "audio_format_priority": ["FLAC", "MP3_320", "MP3_256", "AAC_64"],
                    "cpu_usage": "Very High",
                    "latency": "Higher",
                    "stability": "Excellent"
                },
                "high": {
                    "description": "🎶 High Quality - Excellent audio with balanced performance",
                    "buffer_size": 1000,
                    "opus_quality": 10,
                    "resampling": "HIGH",
                    "prefer_lossless": False,
                    "frame_buffer_duration": 8000,
                    "track_stuck_threshold": 6000,
                    "player_update_interval": 1,
                    "use_seek_ghosting": True,
                    "non_allocating_frame_buffer": True,
                    "send_player_updates": True,
                    "auto_reconnect": True,
                    "youtube_clients": ["MUSIC", "ANDROID_MUSIC", "WEB", "WEBEMBEDDED"],
                    "audio_format_priority": ["MP3_320", "MP3_256", "AAC_64"],
                    "cpu_usage": "High",
                    "latency": "Moderate",
                    "stability": "Very Good"
                },
                "balanced": {
                    "description": "⚖️ Balanced - Good quality with moderate resource usage",
                    "buffer_size": 800,
                    "opus_quality": 8,
                    "resampling": "HIGH",
                    "prefer_lossless": False,
                    "frame_buffer_duration": 6000,
                    "track_stuck_threshold": 5000,
                    "player_update_interval": 2,
                    "use_seek_ghosting": True,
                    "non_allocating_frame_buffer": True,
                    "send_player_updates": True,
                    "auto_reconnect": True,
                    "youtube_clients": ["ANDROID_MUSIC", "WEB", "WEBEMBEDDED"],
                    "audio_format_priority": ["MP3_256", "MP3_128", "AAC_64"],
                    "cpu_usage": "Moderate",
                    "latency": "Low",
                    "stability": "Good"
                },
                "performance": {
                    "description": "⚡ Performance - Optimized for low resource usage",
                    "buffer_size": 600,
                    "opus_quality": 6,
                    "resampling": "MEDIUM",
                    "prefer_lossless": False,
                    "frame_buffer_duration": 4000,
                    "track_stuck_threshold": 4000,
                    "player_update_interval": 3,
                    "use_seek_ghosting": False,
                    "non_allocating_frame_buffer": True,
                    "send_player_updates": False,
                    "auto_reconnect": True,
                    "youtube_clients": ["WEB", "WEBEMBEDDED"],
                    "audio_format_priority": ["MP3_128", "MP3_64", "AAC_64"],
                    "cpu_usage": "Low",
                    "latency": "Very Low",
                    "stability": "Fair"
                }
            },
            "current_preset": "high",
            "audio_quality": {
                "buffer_size": 1000,
                "default_volume": 80,
                "volume_step": 5,
                "max_volume": 150,
                "enable_filters": True,
                "enable_equalizer": True,
                "auto_normalize": True,
                "crossfade_duration": 2000,
                "gapless_playback": True
            },
            "advanced_settings": {
                "enable_audio_enhancement": True,
                "dynamic_range_compression": False,
                "bass_boost": False,
                "treble_boost": False,
                "stereo_enhancement": False,
                "noise_reduction": False,
                "echo_cancellation": False,
                "auto_gain_control": False
            },
            "troubleshooting": {
                "enable_debug_logging": False,
                "track_performance_metrics": True,
                "auto_quality_adjustment": False,
                "fallback_on_errors": True,
                "retry_failed_tracks": True,
                "max_retries": 3
            }
        }
    
    def save_settings(self):
        """Save settings to file"""
        try:
            # Save to dedicated quality presets file
            with open(self.quality_presets_path, 'w') as f:
                json.dump(self.settings, f, indent=4)
            print(f"✅ Quality settings saved to {self.quality_presets_path}")
            return True
        except Exception as e:
            print(f"❌ Failed to save quality settings: {e}")
            return False
    
    def get_quality_presets(self):
        """Get available quality presets"""
        return self.settings.get('quality_presets', {})
    
    def get_current_preset(self):
        """Get current quality preset"""
        return self.settings.get('current_preset', 'high')
    
    def apply_preset(self, preset_name: str):
        """Apply a quality preset"""
        presets = self.get_quality_presets()
        if preset_name not in presets:
            return False, f"Preset '{preset_name}' not found"
        
        preset = presets[preset_name]
        
        # Update audio quality settings
        if 'audio_quality' not in self.settings:
            self.settings['audio_quality'] = {}
        
        self.settings['audio_quality']['buffer_size'] = preset['buffer_size']
        self.settings['current_preset'] = preset_name
        
        # Apply settings to Lavalink if possible
        self.apply_lavalink_settings(preset)
        
        success = self.save_settings()
        message = f"✅ Applied '{preset_name}' preset successfully! Restart music playback for full effect." if success else "❌ Failed to save settings"
        return success, message
    
    def apply_lavalink_settings(self, preset):
        """Apply preset settings to Lavalink configuration"""
        try:
            if not os.path.exists(self.lavalink_config_path):
                print(f"⚠️ Lavalink config not found: {self.lavalink_config_path}")
                return False
                
            with open(self.lavalink_config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Update Lavalink settings based on preset
            if 'lavalink' not in config:
                config['lavalink'] = {}
            if 'server' not in config['lavalink']:
                config['lavalink']['server'] = {}
                
            server_config = config['lavalink']['server']
            
            # Apply preset settings
            server_config['bufferDurationMs'] = preset['buffer_size']
            server_config['frameBufferDurationMs'] = preset['frame_buffer_duration']
            server_config['opusEncodingQuality'] = preset['opus_quality']
            server_config['resamplingQuality'] = preset['resampling']
            server_config['trackStuckThresholdMs'] = preset['track_stuck_threshold']
            server_config['useSeekGhosting'] = preset['use_seek_ghosting']
            server_config['playerUpdateInterval'] = preset['player_update_interval']
            server_config['nonAllocatingFrameBuffer'] = preset['non_allocating_frame_buffer']
            
            # Save updated config
            with open(self.lavalink_config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, indent=2)
                
            print(f"✅ Applied preset settings to Lavalink config")
            return True
            
        except Exception as e:
            print(f"❌ Failed to apply Lavalink settings: {e}")
            return False

def setup_quality_commands(tree: app_commands.CommandTree, bot):
    """Setup quality management commands"""
    
    quality_manager = QualityManager(bot)
    
    @tree.command(
        name="quality",
        description="Manage audio quality settings for the music system"
    )
    @app_commands.describe(
        action="Action to perform",
        preset="Quality preset to apply"
    )
    async def quality(
        interaction: discord.Interaction, 
        action: Literal["status", "preset", "info"] = "status",
        preset: Optional[Literal["ultra_high", "high", "balanced", "performance"]] = None
    ):
        """Manage audio quality settings"""
        
        if action == "status":
            # Show current quality status
            current_preset = quality_manager.get_current_preset()
            presets = quality_manager.get_quality_presets()
            
            if current_preset in presets:
                preset_info = presets[current_preset]
                
                embed = discord.Embed(
                    title="🎵 Audio Quality Status",
                    color=discord.Color.blue()
                )
                embed.add_field(
                    name="Current Preset",
                    value=f"**{current_preset.replace('_', ' ').title()}**\n{preset_info['description']}",
                    inline=False
                )
                
                # Show technical details
                audio_settings = quality_manager.settings.get('audio_quality', {})
                tech_details = (
                    f"🔊 **Buffer Size:** {preset_info['buffer_size']}ms\n"
                    f"🎛️ **Resampling:** {preset_info['resampling']}\n"
                    f"🎼 **Opus Quality:** {preset_info['opus_quality']}/10\n"
                    f"📻 **Prefer Lossless:** {'Yes' if preset_info.get('prefer_lossless') else 'No'}\n"
                    f"🔢 **Default Volume:** {audio_settings.get('default_volume', 80)}%\n"
                    f"⚡ **CPU Usage:** {preset_info['cpu_usage']}\n"
                    f"⏱️ **Latency:** {preset_info['latency']}"
                )
                
                embed.add_field(
                    name="Technical Details",
                    value=tech_details,
                    inline=False
                )
                
                embed.add_field(
                    name="Performance Impact",
                    value=f"**Stability:** {preset_info['stability']}\n"
                          f"**Audio Formats:** {', '.join(preset_info['audio_format_priority'][:2])}\n"
                          f"**YouTube Clients:** {len(preset_info['youtube_clients'])} optimized",
                    inline=False
                )
                
                embed.set_footer(text="Use /quality preset <preset_name> to change quality")
                
            else:
                embed = discord.Embed(
                    title="❌ Audio Quality Status",
                    description=f"Current preset '{current_preset}' not found in configuration. Using default high-quality settings.",
                    color=discord.Color.orange()
                )
                
                # Show available presets as fallback
                presets = quality_manager.get_quality_presets()
                if presets:
                    preset_list = "\n".join([f"• **{name.replace('_', ' ').title()}**" for name in presets.keys()])
                    embed.add_field(
                        name="Available Presets",
                        value=preset_list,
                        inline=False
                    )
                embed.set_footer(text="Use /quality preset <preset_name> to apply a preset")
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif action == "preset":
            if not preset:
                # Show available presets
                presets = quality_manager.get_quality_presets()
                current = quality_manager.get_current_preset()
                
                if not presets:
                    embed = discord.Embed(
                        title="❌ No Quality Presets Available",
                        description="Quality presets configuration not found. The system will use default high-quality settings.",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                embed = discord.Embed(
                    title="🎛️ Available Quality Presets",
                    description="Choose a quality preset that best fits your needs:",
                    color=discord.Color.green()
                )
                
                for preset_name, preset_info in presets.items():
                    is_current = " ✅" if preset_name == current else ""
                    embed.add_field(
                        name=f"{preset_name.replace('_', ' ').title()}{is_current}",
                        value=f"{preset_info['description']}\n"
                               f"**Buffer:** {preset_info['buffer_size']}ms | "
                               f"**Quality:** {preset_info['opus_quality']}/10 | "
                               f"**CPU:** {preset_info['cpu_usage']}",
                        inline=False
                    )
                
                embed.set_footer(text="Use /quality preset <preset_name> to apply a preset")
                await interaction.response.send_message(embed=embed, ephemeral=True)
            
            else:
                # Apply the specified preset
                if not interaction.user.guild_permissions.manage_guild:
                    await interaction.response.send_message(
                        "❌ You need 'Manage Server' permission to change audio quality settings!",
                        ephemeral=True
                    )
                    return
                
                success, message = quality_manager.apply_preset(preset)
                
                if success:
                    presets = quality_manager.get_quality_presets()
                    preset_info = presets[preset]
                    
                    embed = discord.Embed(
                        title="✅ Quality Preset Applied",
                        description=f"Audio quality has been set to **{preset.replace('_', ' ').title()}**",
                        color=discord.Color.green()
                    )
                    embed.add_field(
                        name="New Settings",
                        value=f"{preset_info['description']}\n"
                               f"**Buffer:** {preset_info['buffer_size']}ms\n"
                               f"**Quality:** {preset_info['opus_quality']}/10\n"
                               f"**CPU Usage:** {preset_info['cpu_usage']}\n"
                               f"**Latency:** {preset_info['latency']}",
                        inline=False
                    )
                    embed.add_field(
                        name="💡 Important Note",
                        value="• Changes will apply to new songs immediately\n"
                              "• For current song, use `/skip` or `/replay` to apply\n"
                              "• Restart Lavalink for full optimization (if self-hosted)",
                        inline=False
                    )
                    
                else:
                    embed = discord.Embed(
                        title="❌ Failed to Apply Preset",
                        description=message,
                        color=discord.Color.red()
                    )
                
                await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif action == "info":
            # Show detailed information about audio quality
            embed = discord.Embed(
                title="📊 Audio Quality Information",
                description="Understanding audio quality settings for optimal music experience:",
                color=discord.Color.blue()
            )
            
            embed.add_field(
                name="🎵 Quality Presets Explained",
                value="**Ultra High**: Maximum quality for powerful servers\n"
                      "**High**: Excellent balance (recommended)\n"
                      "**Balanced**: Good quality, moderate resources\n"
                      "**Performance**: Optimized for limited resources",
                inline=False
            )
            
            embed.add_field(
                name="🔊 Buffer Size",
                value="• Higher = smoother playback, more delay\n"
                      "• Lower = less delay, potential stuttering\n"
                      "• Range: 600ms - 1200ms",
                inline=False
            )
            
            embed.add_field(
                name="🎛️ Technical Settings",
                value="**Opus Quality**: 0-10 scale (10 = best)\n"
                      "**Resampling**: LOW/MEDIUM/HIGH quality\n"
                      "**Frame Buffer**: Audio buffering duration\n"
                      "**Seek Ghosting**: Smoother seeking experience",
                inline=False
            )
            
            embed.add_field(
                name="💡 Performance Tips",
                value="• Use **Ultra High** on dedicated servers\n"
                      "• Use **High** for most Discord bots (default)\n"
                      "• Use **Balanced** for shared hosting\n"
                      "• Use **Performance** for Raspberry Pi/low-end",
                inline=False
            )
            
            embed.set_footer(text="Use /quality preset to change settings")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @tree.command(
        name="audiostats",
        description="Show detailed audio statistics and performance metrics"
    )
    async def audiostats(interaction: discord.Interaction):
        """Show audio statistics and performance metrics"""
        
        embed = discord.Embed(
            title="📊 Audio Statistics",
            color=discord.Color.blue()
        )
        
        # Get current quality settings
        current_preset = quality_manager.get_current_preset()
        presets = quality_manager.get_quality_presets()
        
        if current_preset in presets:
            preset_info = presets[current_preset]
            embed.add_field(
                name="⚙️ Current Quality Settings",
                value=f"**Preset:** {current_preset.replace('_', ' ').title()}\n"
                      f"**Buffer:** {preset_info['buffer_size']}ms\n"
                      f"**Quality:** {preset_info['opus_quality']}/10\n"
                      f"**CPU Impact:** {preset_info['cpu_usage']}",
                inline=True
            )
        else:
            embed.add_field(
                name="⚙️ Current Quality Settings",
                value=f"**Preset:** {current_preset.replace('_', ' ').title()} (Default High Quality)\n"
                      f"**Buffer:** 1000ms\n"
                      f"**Quality:** 10/10\n"
                      f"**CPU Impact:** High",
                inline=True
            )
        
        # Try to get player information if available
        try:
            # Check if music system is loaded
            if hasattr(bot, 'cogs') and any('music' in str(cog).lower() for cog in bot.cogs.values()):
                player = None
                
                # Try to get player for current guild
                if interaction.guild:
                    voice_client = interaction.guild.voice_client
                    if voice_client:
                        embed.add_field(
                            name="🎵 Player Status",
                            value=f"**Connected:** Yes\n"
                                  f"**Playing:** {'Yes' if hasattr(voice_client, 'is_playing') and voice_client.is_playing() else 'No'}\n"
                                  f"**Channel:** {voice_client.channel.name if voice_client.channel else 'Unknown'}\n"
                                  f"**Volume:** {getattr(voice_client, 'volume', 'Unknown')}%",
                            inline=True
                        )
                    else:
                        embed.add_field(
                            name="🎵 Player Status",
                            value="Not connected to voice channel",
                            inline=True
                        )
                else:
                    embed.add_field(
                        name="🎵 Player Status",
                        value="Command not used in a server",
                        inline=True
                    )
            else:
                embed.add_field(
                    name="🎵 Music System",
                    value="Music system not loaded",
                    inline=True
                )
                
        except Exception as e:
            embed.add_field(
                name="🎵 Player Status",
                value=f"Unable to fetch player info: {str(e)[:50]}...",
                inline=True
            )
        
        # Add system information
        embed.add_field(
            name="🖥️ System Info",
            value=f"**Bot Latency:** {round(bot.latency * 1000)}ms\n"
                  f"**Guilds:** {len(bot.guilds)}\n"
                  f"**Users:** {len(bot.users)}\n"
                  f"**Commands:** {len(bot.tree.get_commands())}",
            inline=True
        )
        
        embed.set_footer(text="Use /quality to manage audio quality settings")
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Export the setup function
__all__ = ['setup_quality_commands'] 