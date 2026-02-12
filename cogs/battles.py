import discord
from discord.ext import commands
from utils.database import get_db
from utils.constants import GENRES, POOLS, COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO, CREATOR_ROLE_NAME
import asyncio
import logging

logger = logging.getLogger('music_battles.battles')

class Battles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_or_create_role(self, guild, role_name):
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            role = await guild.create_role(name=role_name, color=discord.Color.blue())
        return role

    @commands.command(name="setup_server")
    @commands.has_permissions(administrator=True)
    async def setup_server(self, ctx):
        """Initial server setup: creates categories and pool channels."""
        embed = discord.Embed(title="Server Setup", description="Setting up server structure...", color=COLOR_INFO)
        status_msg = await ctx.send(embed=embed)
        
        general_channels = ["live-stats", "results-winners", "announcements"]
        for ch_name in general_channels:
            ch = discord.utils.get(ctx.guild.text_channels, name=ch_name)
            if not ch: ch = await ctx.guild.create_text_channel(ch_name)
            await ch.set_permissions(ctx.guild.default_role, send_messages=False)
            await ch.set_permissions(ctx.guild.me, send_messages=True)

        from utils.constants import VOTER_ROLE_NAME
        await self._get_or_create_role(ctx.guild, CREATOR_ROLE_NAME)
        await self._get_or_create_role(ctx.guild, VOTER_ROLE_NAME)

        for genre in GENRES:
            category = discord.utils.get(ctx.guild.categories, name=genre)
            if not category: category = await ctx.guild.create_category(genre)
            for pool in POOLS:
                channel_name = f"{int(pool)}-pool"
                channel = discord.utils.get(category.text_channels, name=channel_name)
                if not channel:
                    channel = await ctx.guild.create_text_channel(channel_name, category=category)
                    welcome_embed = discord.Embed(
                        title=f"Welcome to {genre} ${pool} Pool",
                        description=f"Entry Fee: **{int(pool)} Coins**.\n\n1. Upload your music file.\n2. Type `!enter`.\n\nIf you need coins, use `!buy_coins <amount>`.",
                        color=COLOR_SUCCESS
                    )
                    await channel.send(embed=welcome_embed)

        embed.description = "Server setup complete!"
        embed.color = COLOR_SUCCESS
        await status_msg.edit(embed=embed)

    @commands.command(name="enter")
    async def enter_battle(self, ctx):
        """Enter a battle using Coins."""
        if not ctx.channel.category or ctx.channel.category.name not in GENRES:
            embed = discord.Embed(title="Error", description="Use this command in a genre pool channel.", color=COLOR_ERROR)
            return await ctx.send(embed=embed)
        
        genre = ctx.channel.category.name
        try:
            pool_amount = float(ctx.channel.name.split('-')[0])
            required_coins = int(pool_amount)
        except:
            embed = discord.Embed(title="Error", description="Invalid pool channel structure.", color=COLOR_ERROR)
            return await ctx.send(embed=embed)

        if not ctx.message.attachments:
            embed = discord.Embed(title="Error", description="Please upload your music file with `!enter`.", color=COLOR_ERROR)
            return await ctx.send(embed=embed)

        track_url = ctx.message.attachments[0].url

        async with get_db() as db:
            cursor = await db.execute("SELECT coins FROM users WHERE user_id = ?", (ctx.author.id,))
            row = await cursor.fetchone()
            user_coins = row[0] if row else 0

            if user_coins < required_coins:
                embed = discord.Embed(
                    title="Insufficient Balance", 
                    description=f"This battle requires **{required_coins} coins**.\nYour Balance: **{user_coins} coins**.\n\nUse `!buy_coins {required_coins}` to top up.", 
                    color=COLOR_ERROR
                )
                return await ctx.send(embed=embed)

            await db.execute("UPDATE users SET coins = coins - ? WHERE user_id = ?", (required_coins, ctx.author.id))
            
            cursor = await db.execute("SELECT battle_id FROM battles WHERE genre = ? AND pool_amount = ? AND status = 'pending'", (genre, pool_amount))
            row = await cursor.fetchone()
            battle_id = row[0] if row else None
            
            if not battle_id:
                cursor = await db.execute("INSERT INTO battles (genre, pool_amount, status) VALUES (?, ?, 'pending')", (genre, pool_amount))
                battle_id = cursor.lastrowid
            
            await db.execute(
                "INSERT INTO entrants (battle_id, user_id, track_link, payment_status) VALUES (?, ?, ?, 'paid')",
                (battle_id, ctx.author.id, track_url)
            )
            
            await db.execute(
                "INSERT INTO pool_totals (genre, pool_type, total_amount, entrant_count) VALUES (?, ?, ?, 1) "
                "ON CONFLICT(genre, pool_type) DO UPDATE SET total_amount = total_amount + ?, entrant_count = entrant_count + 1",
                (genre, pool_amount, pool_amount, pool_amount)
            )
            await db.commit()

        creator_role = await self._get_or_create_role(ctx.guild, CREATOR_ROLE_NAME)
        if creator_role not in ctx.author.roles: await ctx.author.add_roles(creator_role)

        embed = discord.Embed(
            title="Entry Successful",
            description=f"You've entered the **{genre} ${pool_amount}** battle.\n**{required_coins}** coins have been deducted from your balance.",
            color=COLOR_SUCCESS
        )
        await ctx.send(embed=embed)

    @commands.command(name="battles")
    async def list_battles(self, ctx):
        async with get_db() as db:
            cursor = await db.execute("SELECT battle_id, genre, pool_amount, status FROM battles WHERE status != 'completed'")
            rows = await cursor.fetchall()
            if not rows:
                embed = discord.Embed(title="Active Battles", description="No active battles found.", color=COLOR_INFO)
                return await ctx.send(embed=embed)
                
            embed = discord.Embed(title="Active Battles", color=COLOR_INFO)
            for bid, genre, pool, status in rows:
                embed.add_field(name=f"Battle #{bid}", value=f"**Genre:** {genre}\n**Pool:** ${pool}\n**Status:** `{status}`", inline=True)
            await ctx.send(embed=embed)

    @commands.command(name="delete_setup")
    @commands.has_permissions(administrator=True)
    async def delete_setup(self, ctx):
        """Deletes all categories and channels created during setup."""
        embed = discord.Embed(
            title="Delete Setup", 
            description="Deleting all battle categories and channels...", 
            color=COLOR_ERROR
        )
        status_msg = await ctx.send(embed=embed)

        general_channels = ["live-stats", "results-winners", "announcements"]
        for ch_name in general_channels:
            channel = discord.utils.get(ctx.guild.text_channels, name=ch_name)
            if channel:
                await channel.delete()

        for genre in GENRES:
            category = discord.utils.get(ctx.guild.categories, name=genre)
            if category:
                for channel in category.channels:
                    await channel.delete()
                await category.delete()
            
            battle_category = discord.utils.get(ctx.guild.categories, name=f"{genre} Battles")
            if battle_category:
                for channel in battle_category.channels:
                    await channel.delete()
                await battle_category.delete()

        embed.description = "All battle-related channels and categories have been deleted."
        embed.color = COLOR_SUCCESS
        await status_msg.edit(embed=embed)

async def setup(bot):
    await bot.add_cog(Battles(bot))
