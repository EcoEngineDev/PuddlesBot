import discord
from discord import app_commands
import functools
from typing import Callable, Any
import traceback

# Store reference to the client
_client = None

def setup_help_system(client):
    """Initialize the help system with client reference"""
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
                import language
                user_lang = language.get_server_language(interaction.guild_id)
                await interaction.response.send_message(
                    language.get_text("error_general", user_lang, error=str(e)),
                    ephemeral=True
                )
            raise
    return wrapper

class HelpView(discord.ui.View):
    def __init__(self, interaction: discord.Interaction):
        super().__init__(timeout=300)
        self.interaction = interaction
        self.current_page = 0
        self.pages = [
            self.get_overview_page,
            self.get_task_page,
            self.get_interactive_page,
            self.get_leveling_page,
            self.get_invite_page,
            self.get_music_page,
            self.get_utility_page,
            self.get_fun_page,
            self.get_admin_page,
            self.get_credits_page
        ]
        self.total_pages = len(self.pages)
        
        # Get language for button labels
        import language
        self.user_lang = language.get_server_language(self.interaction.guild_id)
        
        # Create localized buttons
        self.previous_button = discord.ui.Button(
            label=language.get_text("help_previous", self.user_lang),
            style=discord.ButtonStyle.secondary,
            disabled=True
        )
        self.previous_button.callback = self.previous_button_callback
        
        self.next_button = discord.ui.Button(
            label=language.get_text("help_next", self.user_lang),
            style=discord.ButtonStyle.secondary
        )
        self.next_button.callback = self.next_button_callback
        
        self.home_button = discord.ui.Button(
            label=language.get_text("help_home", self.user_lang),
            style=discord.ButtonStyle.primary
        )
        self.home_button.callback = self.home_button_callback
        
        # Add buttons to view
        self.add_item(self.previous_button)
        self.add_item(self.next_button)
        self.add_item(self.home_button)
        
        self.update_buttons()
    
    def update_buttons(self):
        # Update Previous button
        self.previous_button.disabled = (self.current_page == 0)
        # Update Next button
        self.next_button.disabled = (self.current_page >= self.total_pages - 1)
    
    def get_overview_page(self):
        import language
        user_lang = language.get_server_language(self.interaction.guild_id)
        
        embed = discord.Embed(
            title=language.get_text("help_overview_title", user_lang),
            description=language.get_text("help_overview_description", user_lang),
            color=discord.Color.blue()
        )
        
        embed.add_field(
            name=language.get_text("help_task_management", user_lang),
            value=language.get_text("help_task_management_text", user_lang),
            inline=True
        )
        
        embed.add_field(
            name=language.get_text("help_interactive_messages", user_lang),
            value=language.get_text("help_interactive_messages_text", user_lang),
            inline=True
        )
        
        embed.add_field(
            name=language.get_text("help_leveling_system", user_lang),
            value=language.get_text("help_leveling_system_text", user_lang),
            inline=True
        )
        
        embed.add_field(
            name=language.get_text("help_invite_tracking", user_lang),
            value=language.get_text("help_invite_tracking_text", user_lang),
            inline=True
        )
        
        embed.add_field(
            name=language.get_text("help_music_system", user_lang),
            value=language.get_text("help_music_system_text", user_lang),
            inline=True
        )
        
        embed.add_field(
            name=language.get_text("help_utility_commands", user_lang),
            value=language.get_text("help_utility_commands_text", user_lang),
            inline=True
        )
        
        embed.add_field(
            name=language.get_text("help_fun_commands", user_lang),
            value=language.get_text("help_fun_commands_text", user_lang),
            inline=True
        )
        
        embed.add_field(
            name=language.get_text("help_admin_commands", user_lang),
            value=language.get_text("help_admin_commands_text", user_lang),
            inline=True
        )
        
        embed.add_field(
            name=language.get_text("help_credits", user_lang),
            value=language.get_text("help_credits_text", user_lang),
            inline=True
        )
        
        embed.add_field(
            name=language.get_text("help_key_features", user_lang),
            value=language.get_text("help_key_features_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_disclaimers", user_lang),
            value=language.get_text("help_disclaimers_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_important_links", user_lang),
            value=language.get_text("help_important_links_text", user_lang),
            inline=False
        )
        
        embed.set_footer(text=language.get_text("help_page_info", user_lang, current=self.current_page + 1, total=self.total_pages))
        return embed
    
    def get_task_page(self):
        import language
        user_lang = language.get_server_language(self.interaction.guild_id)
        
        embed = discord.Embed(
            title=language.get_text("help_task_title", user_lang),
            description=language.get_text("help_task_description", user_lang),
            color=discord.Color.green()
        )
        
        embed.add_field(
            name=language.get_text("help_task_creating", user_lang),
            value=language.get_text("help_task_creating_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_task_viewing", user_lang),
            value=language.get_text("help_task_viewing_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_task_sniping", user_lang),
            value=language.get_text("help_task_sniping_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_task_permissions", user_lang),
            value=language.get_text("help_task_permissions_text", user_lang),
            inline=False
        )
        
        embed.set_footer(text=language.get_text("help_task_footer", user_lang).format(current=self.current_page + 1, total=self.total_pages))
        return embed
    
    def get_interactive_page(self):
        import language
        user_lang = language.get_server_language(self.interaction.guild_id)
        
        embed = discord.Embed(
            title=language.get_text("help_interactive_title", user_lang),
            description=language.get_text("help_interactive_description", user_lang),
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name=language.get_text("help_interactive_creation", user_lang),
            value=language.get_text("help_interactive_creation_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_interactive_management", user_lang),
            value=language.get_text("help_interactive_management_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_interactive_tickets", user_lang),
            value=language.get_text("help_interactive_tickets_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_interactive_permissions", user_lang),
            value=language.get_text("help_interactive_permissions_text", user_lang),
            inline=False
        )
        
        embed.set_footer(text=language.get_text("help_interactive_footer", user_lang).format(current=self.current_page + 1, total=self.total_pages))
        return embed
    
    def get_leveling_page(self):
        import language
        user_lang = language.get_server_language(self.interaction.guild_id)
        
        embed = discord.Embed(
            title=language.get_text("help_leveling_title", user_lang),
            description=language.get_text("help_leveling_description", user_lang),
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name=language.get_text("help_leveling_progress", user_lang),
            value=language.get_text("help_leveling_progress_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_leveling_admin", user_lang),
            value=language.get_text("help_leveling_admin_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_leveling_config", user_lang),
            value=language.get_text("help_leveling_config_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_leveling_testing", user_lang),
            value=language.get_text("help_leveling_testing_text", user_lang),
            inline=False
        )
        
        embed.set_footer(text=language.get_text("help_leveling_footer", user_lang).format(current=self.current_page + 1, total=self.total_pages))
        return embed
    
    def get_invite_page(self):
        import language
        user_lang = language.get_server_language(self.interaction.guild_id)
        
        embed = discord.Embed(
            title=language.get_text("help_invite_title", user_lang),
            description=language.get_text("help_invite_description", user_lang),
            color=discord.Color.teal()
        )
        
        embed.add_field(
            name=language.get_text("help_invite_stats", user_lang),
            value=language.get_text("help_invite_stats_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_invite_admin", user_lang),
            value=language.get_text("help_invite_admin_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_invite_system", user_lang),
            value=language.get_text("help_invite_system_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_invite_permissions", user_lang),
            value=language.get_text("help_invite_permissions_text", user_lang),
            inline=False
        )
        
        embed.set_footer(text=language.get_text("help_invite_footer", user_lang).format(current=self.current_page + 1, total=self.total_pages))
        return embed
    
    def get_music_page(self):
        import language
        user_lang = language.get_server_language(self.interaction.guild_id)
        
        embed = discord.Embed(
            title=language.get_text("help_music_title", user_lang),
            description=language.get_text("help_music_description", user_lang),
            color=discord.Color.red()
        )
        
        embed.add_field(
            name=language.get_text("help_music_playback", user_lang),
            value=language.get_text("help_music_playback_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_music_queue", user_lang),
            value=language.get_text("help_music_queue_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_music_quality", user_lang),
            value=language.get_text("help_music_quality_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_music_features", user_lang),
            value=language.get_text("help_music_features_text", user_lang),
            inline=False
        )
        
        embed.set_footer(text=language.get_text("help_music_footer", user_lang).format(current=self.current_page + 1, total=self.total_pages))
        return embed
    
    def get_utility_page(self):
        import language
        user_lang = language.get_server_language(self.interaction.guild_id)
        
        embed = discord.Embed(
            title=language.get_text("help_utility_title", user_lang),
            description=language.get_text("help_utility_description", user_lang),
            color=discord.Color.orange()
        )
        
        embed.add_field(
            name=language.get_text("help_utility_user", user_lang),
            value=language.get_text("help_utility_user_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_utility_server", user_lang),
            value=language.get_text("help_utility_server_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_utility_voice", user_lang),
            value=language.get_text("help_utility_voice_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_utility_moderation", user_lang),
            value=language.get_text("help_utility_moderation_text", user_lang),
            inline=False
        )
        
        embed.set_footer(text=language.get_text("help_utility_footer", user_lang).format(current=self.current_page + 1, total=self.total_pages))
        return embed
    
    def get_fun_page(self):
        import language
        user_lang = language.get_server_language(self.interaction.guild_id)
        
        embed = discord.Embed(
            title=language.get_text("help_fun_title", user_lang),
            description=language.get_text("help_fun_description", user_lang),
            color=discord.Color.magenta()
        )
        
        embed.add_field(
            name=language.get_text("help_fun_random", user_lang),
            value=language.get_text("help_fun_random_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_fun_games", user_lang),
            value=language.get_text("help_fun_games_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_fun_ai", user_lang),
            value=language.get_text("help_fun_ai_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_fun_navigation", user_lang),
            value=language.get_text("help_fun_navigation_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_fun_features", user_lang),
            value=language.get_text("help_fun_features_text", user_lang),
            inline=False
        )
        
        embed.set_footer(text=language.get_text("help_fun_footer", user_lang).format(current=self.current_page + 1, total=self.total_pages))
        return embed
    
    def get_admin_page(self):
        import language
        user_lang = language.get_server_language(self.interaction.guild_id)
        
        embed = discord.Embed(
            title=language.get_text("help_admin_title", user_lang),
            description=language.get_text("help_admin_description", user_lang),
            color=discord.Color.dark_red()
        )
        
        embed.add_field(
            name=language.get_text("help_admin_features", user_lang),
            value=language.get_text("help_admin_features_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_admin_openchat", user_lang),
            value=language.get_text("help_admin_openchat_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_admin_messaging", user_lang),
            value=language.get_text("help_admin_messaging_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_admin_database", user_lang),
            value=language.get_text("help_admin_database_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_admin_owner", user_lang),
            value=language.get_text("help_admin_owner_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_admin_permissions", user_lang),
            value=language.get_text("help_admin_permissions_text", user_lang),
            inline=False
        )
        
        embed.set_footer(text=language.get_text("help_admin_footer", user_lang).format(current=self.current_page + 1, total=self.total_pages))
        return embed
    
    def get_credits_page(self):
        import language
        user_lang = language.get_server_language(self.interaction.guild_id)
        
        embed = discord.Embed(
            title=language.get_text("help_credits_title", user_lang),
            description=language.get_text("help_credits_description", user_lang),
            color=discord.Color.gold()
        )
        
        embed.add_field(
            name=language.get_text("help_credits_music", user_lang),
            value=language.get_text("help_credits_music_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_credits_fun", user_lang),
            value=language.get_text("help_credits_fun_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_credits_coinflip", user_lang),
            value=language.get_text("help_credits_coinflip_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_credits_thanks", user_lang),
            value=language.get_text("help_credits_thanks_text", user_lang),
            inline=False
        )
        
        embed.add_field(
            name=language.get_text("help_credits_development", user_lang),
            value=language.get_text("help_credits_development_text", user_lang),
            inline=False
        )
        
        embed.set_footer(text=language.get_text("help_credits_footer", user_lang).format(current=self.current_page + 1, total=self.total_pages))
        return embed
    
    async def previous_button_callback(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            embed = self.pages[self.current_page]()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    async def next_button_callback(self, interaction: discord.Interaction):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self.update_buttons()
            embed = self.pages[self.current_page]()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()
    
    async def home_button_callback(self, interaction: discord.Interaction):
        self.current_page = 0
        self.update_buttons()
        embed = self.pages[self.current_page]()
        await interaction.response.edit_message(embed=embed, view=self)

@app_commands.command(
    name="help",
    description="Show all available commands with paginated navigation"
)
@log_command
async def help_command(interaction: discord.Interaction):
    """Display comprehensive help information with pagination"""
    view = HelpView(interaction)
    embed = view.pages[0]()  # Start with overview page
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

def setup_help_commands(tree):
    """Add help commands to the command tree"""
    tree.add_command(help_command)
    
    # Register help command for localization
    import language
    language.register_command("help", help_command, "help", "Show all available commands with paginated navigation")
    
    print("✅ Help commands loaded: /help (paginated)") 