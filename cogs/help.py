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
                "`/enter <track>` - Join a battle (upload music as attachment).\n"
                "`/battles` - List all currently active battles.\n"
                "`/pools [genre]` - View prize pools (optional: filter by genre)."
            ),
            inline=False
        )
        
        if interaction.user.guild_permissions.administrator:
            embed.add_field(
                name="Admin Commands",
                value=(
                    "`/setup_server` / `/delete_setup` - Full server management.\n"
                    "`/decide_winner <genre> <amt>` - Instantly end & pick winner.\n"
                    "`/remove_entrant @user <genre> <amt>` - Remove & refund.\n"
                    "`/start_battle <genre> <amt>` - Move to the voting phase.\n"
                    "`/close_pool <genre> <amt>` - Close entries for a pool.\n"
                    "`/disqualify @user <id>` - Remove an entrant (no refund).\n"
                    "`/add_coins @user <amt>` - Manually credit coins.\n"
                    "`/payouts` - View pending winner payouts.\n"
                    "`/sync` - Sync slash commands manually."
                ),
                inline=False
            )
        
        # Ephemerality is controlled by the global deferrer in main.py
        await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCommand(bot))
