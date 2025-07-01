import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import asyncio
from typing import Optional, Literal

class QualityManager:
    """Audio Quality Management System for Vocard Music Bot"""
    
    def __init__(self, bot):
        self.bot = bot
        self.settings_path = os.path.join('MusicSystem', 'settings.json')
        self.load_settings()
    
    def load_settings(self):
        """Load current settings from file"""
        try:
            if not os.path.exists(self.settings_path):
                print(f"⚠️ Settings file not found: {self.settings_path}")
                self.settings = {}
                return
                
            with open(self.settings_path, 'r') as f:
                content = f.read().strip()
                if not content or content.isspace():
                    print(f"⚠️ Settings file is empty: {self.settings_path}")
                    self.settings = {}
                    return
                    
                self.settings = json.loads(content)
        except json.JSONDecodeError as e:
            print(f"❌ Failed to parse quality settings JSON: {e}")
            print("💡 Settings file may be corrupted. Using default settings.")
            self.settings = {}
        except Exception as e:
            print(f"❌ Failed to load quality settings: {e}")
            self.settings = {}
    
    def save_settings(self):
        """Save settings to file"""
        try:
            with open(self.settings_path, 'w') as f:
                json.dump(self.settings, f, indent=4)
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
        
        return self.save_settings(), "Preset applied successfully"

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
                    value=f"**{current_preset.title()}**\n{preset_info['description']}",
                    inline=False
                )
                
                # Show technical details
                audio_settings = quality_manager.settings.get('audio_quality', {})
                tech_details = (
                    f"🔊 **Buffer Size:** {preset_info['buffer_size']}ms\n"
                    f"🎛️ **Resampling:** {preset_info['resampling']}\n"
                    f"🎼 **Opus Quality:** {preset_info['opus_quality']}/10\n"
                    f"📻 **Prefer Lossless:** {'Yes' if preset_info.get('prefer_lossless') else 'No'}\n"
                    f"🔢 **Default Volume:** {audio_settings.get('default_volume', 80)}%"
                )
                
                embed.add_field(
                    name="Technical Details",
                    value=tech_details,
                    inline=False
                )
                
                embed.set_footer(text="Use /quality preset <preset_name> to change quality")
                
            else:
                embed = discord.Embed(
                    title="❌ Audio Quality Status",
                    description="Current preset not found in configuration",
                    color=discord.Color.red()
                )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        
        elif action == "preset":
            if not preset:
                # Show available presets
                presets = quality_manager.get_quality_presets()
                current = quality_manager.get_current_preset()
                
                embed = discord.Embed(
                    title="🎛️ Available Quality Presets",
                    description="Choose a quality preset that best fits your needs:",
                    color=discord.Color.green()
                )
                
                for preset_name, preset_info in presets.items():
                    is_current = " ✅" if preset_name == current else ""
                    embed.add_field(
                        name=f"{preset_name.title()}{is_current}",
                        value=f"{preset_info['description']}\n"
                               f"Buffer: {preset_info['buffer_size']}ms | "
                               f"Quality: {preset_info['opus_quality']}/10",
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
                        description=f"Audio quality has been set to **{preset.title()}**",
                        color=discord.Color.green()
                    )
                    embed.add_field(
                        name="New Settings",
                        value=f"{preset_info['description']}\n"
                               f"Buffer: {preset_info['buffer_size']}ms\n"
                               f"Quality: {preset_info['opus_quality']}/10",
                        inline=False
                    )
                    embed.set_footer(text="Changes will apply to new songs. Restart current song to apply immediately.")
                    
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
                name="🔊 Buffer Size",
                value="Higher values = smoother playback but more delay\n"
                      "Lower values = less delay but potential stuttering",
                inline=False
            )
            
            embed.add_field(
                name="🎛️ Resampling Quality",
                value="**HIGH**: Best quality, high CPU usage\n"
                      "**MEDIUM**: Balanced quality and performance\n"
                      "**LOW**: Performance mode, lower quality",
                inline=False
            )
            
            embed.add_field(
                name="🎼 Opus Quality",
                value="Scale from 0-10 where 10 is highest quality\n"
                      "Higher values use more CPU but sound better",
                inline=False
            )
            
            embed.add_field(
                name="💡 Recommendations",
                value="• **Ultra High**: For high-end servers with powerful CPU\n"
                      "• **High**: Recommended for most servers (balanced)\n" 
                      "• **Balanced**: Good compromise for busy servers\n"
                      "• **Performance**: For resource-limited environments",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @tree.command(
        name="audiostats",
        description="Show detailed audio statistics and performance metrics"
    )
    async def audiostats(interaction: discord.Interaction):
        """Show audio statistics and performance metrics"""
        
        # Get current player information if available
        if hasattr(bot, 'voicelink') and bot.voicelink:
            try:
                # Try to get player for current guild
                player = bot.voicelink.get_player(interaction.guild.id)
                
                embed = discord.Embed(
                    title="📊 Audio Statistics",
                    color=discord.Color.blue()
                )
                
                if player and player.is_connected():
                    embed.add_field(
                        name="🎵 Player Status",
                        value=f"**Connected:** {'Yes' if player.is_connected() else 'No'}\n"
                              f"**Playing:** {'Yes' if player.is_playing() else 'No'}\n"
                              f"**Paused:** {'Yes' if player.is_paused() else 'No'}\n"
                              f"**Volume:** {getattr(player, 'volume', 'Unknown')}%",
                        inline=True
                    )
                    
                    if hasattr(player, 'current') and player.current:
                        track = player.current
                        embed.add_field(
                            name="🎶 Current Track",
                            value=f"**Title:** {track.title[:30]}...\n"
                                  f"**Source:** {track.source}\n"
                                  f"**Duration:** {track.duration // 1000}s",
                            inline=True
                        )
                else:
                    embed.add_field(
                        name="🎵 Player Status",
                        value="No active player in this server",
                        inline=False
                    )
                
                # Add quality settings
                current_preset = quality_manager.get_current_preset()
                presets = quality_manager.get_quality_presets()
                
                if current_preset in presets:
                    preset_info = presets[current_preset]
                    embed.add_field(
                        name="⚙️ Quality Settings",
                        value=f"**Preset:** {current_preset.title()}\n"
                              f"**Buffer:** {preset_info['buffer_size']}ms\n"
                              f"**Quality:** {preset_info['opus_quality']}/10",
                        inline=True
                    )
                
                embed.set_footer(text="Use /quality to manage audio quality settings")
                
            except Exception as e:
                embed = discord.Embed(
                    title="❌ Audio Statistics",
                    description=f"Unable to fetch audio statistics: {str(e)}",
                    color=discord.Color.red()
                )
        else:
            embed = discord.Embed(
                title="❌ Audio Statistics", 
                description="Music system not initialized or not available",
                color=discord.Color.red()
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Export the setup function
__all__ = ['setup_quality_commands'] 