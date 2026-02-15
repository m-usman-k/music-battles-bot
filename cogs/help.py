import discord
from discord.ext import commands
from discord import app_commands
from utils.constants import COLOR_INFO
import logging

logger = logging.getLogger('music_battles.help')

class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="help")
    async def help_command(self, interaction: discord.Interaction):
        """Displays all available commands and their usage."""
        # defer() is now handled globally in main.py
        
        embed = discord.Embed(
            title="Music Battle Bot - Help",
            description="Welcome to the Music Battle Bot! Here are the available commands:",
            color=COLOR_INFO
        )

        embed.add_field(
            name="Coin Commands",
            value=(
                "`/buy_coins <amount>` - Purchase coins via Stripe/PayPal.\n"
                "`/balance` - Check your coin balance."
            ),
            inline=False
        )

        embed.add_field(
            name="Battle Commands",
            value=(
                "`/enter <track>` - Upload music + use this command in a pool channel.\n"
                "`/vote <num>` - Vote for an entrant (in voting channels).\n"
                "`/battles` - List active battles.\n"
                "`/balance` - Check your coin balance."
            ),
            inline=False
        )
        
        if interaction.user.guild_permissions.administrator:
            embed.add_field(
                name="Admin Commands",
                value=(
                    "`/setup_server` / `/delete_setup` - Manage server.\n"
                    "`/add_coins @user <amt>` - Manually give coins.\n"
                    "`/balance @user` - Check another user's balance.\n"
                    "`/start_battle <id>` - Start voting phase.\n"
                    "`/close_pool <genre> <amt>` - Close a pool.\n"
                    "`/disqualify @user <id>` - Remove entrant.\n"
                    "`/payouts` - View amounts owed.\n"
                    "`/sync` - Sync command tree."
                ),
                inline=False
            )
        
        # Ephemerality is controlled by the global deferrer in main.py
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCommand(bot))
