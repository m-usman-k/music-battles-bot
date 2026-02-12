import discord
from discord.ext import commands
from utils.constants import COLOR_INFO

class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help(self, ctx):
        """Displays the help message with coin system details."""
        embed = discord.Embed(
            title="Music Battles Bot - Help",
            description="Participate in music battles by topping up your coins.",
            color=COLOR_INFO
        )

        embed.add_field(
            name="Coin Commands",
            value=(
                "`!buy_coins <amount>` - Purchase coins via Stripe/PayPal ($1 = 1 Coin).\n"
                "`!balance` - Check your current coin balance."
            ),
            inline=False
        )

        embed.add_field(
            name="Battle Commands",
            value=(
                "`!enter` - Upload music + use this command in a pool channel (costs coins).\n"
                "`!vote <num>` - Vote for an entrant (in voting channels).\n"
                "`!battles` - List active battles.\n"
                "`!pool_stats` - View prize pools."
            ),
            inline=False
        )
        
        if ctx.author.guild_permissions.administrator:
            embed.add_field(
                name="Admin Commands",
                value=(
                    "`!setup_server` / `!delete_setup` - Manage server structure.\n"
                    "`!add_coins @user <amt>` - Manually give coins.\n"
                    "`!start_battle <id>` - Move battle to voting phase.\n"
                    "`!payouts` - View winners and amounts owed."
                ),
                inline=False
            )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(HelpCommand(bot))
