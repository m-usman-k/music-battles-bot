import discord
from discord.ext import commands, tasks
from utils.database import get_db
from utils.constants import VOTING_DURATION_HOURS, PLATFORM_FEE_PERCENT, WINNER_PAYOUT_PERCENT, COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO, VOTER_ROLE_NAME
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('music_battles.voting')

class Voting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_votes.start()

    def cog_unload(self):
        self.check_votes.cancel()

    @tasks.loop(minutes=1)
    async def check_votes(self):
        """Background task to check for battles whose voting period has ended."""
        now = datetime.utcnow()
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT battle_id, voting_channel_id, genre, pool_amount FROM battles WHERE status = 'voting' AND voting_ends_at <= ?",
                (now.isoformat(),)
            )
            rows = await cursor.fetchall()
            
            for row in rows:
                battle_id, channel_id, genre, pool_amount = row
                await self.end_voting(battle_id, channel_id, genre, pool_amount)

    async def end_voting(self, battle_id, channel_id, genre, pool_amount):
        """Tally votes and announce the winner."""
        async with get_db() as db:
            cursor = await db.execute(
                """
                SELECT entrant_id, COUNT(*) as vote_count 
                FROM votes 
                WHERE battle_id = ? 
                GROUP BY entrant_id 
                ORDER BY vote_count DESC
                """,
                (battle_id,)
            )
            results = await cursor.fetchall()
            
            if not results:
                await db.execute("UPDATE battles SET status = 'completed' WHERE battle_id = ?", (battle_id,))
                await db.commit()
                return

            winner_entrant_id, winner_votes = results[0]
            
            cursor = await db.execute(
                "SELECT u.username, u.user_id, e.track_link FROM entrants e JOIN users u ON e.user_id = u.user_id WHERE e.entrant_id = ?",
                (winner_entrant_id,)
            )
            winner_row = await cursor.fetchone()
            winner_name, winner_id, track_link = winner_row

            cursor = await db.execute("SELECT COUNT(*) FROM entrants WHERE battle_id = ? AND payment_status = 'paid'", (battle_id,))
            num_paid = (await cursor.fetchone())[0]
            total_pool = num_paid * pool_amount
            payout = total_pool * WINNER_PAYOUT_PERCENT
            fee = total_pool * PLATFORM_FEE_PERCENT

            await db.execute("UPDATE battles SET status = 'completed' WHERE battle_id = ?", (battle_id,))
            await db.commit()

            channel = self.bot.get_channel(channel_id)
            if channel:
                embed = discord.Embed(title="Battle Results", color=discord.Color.gold())
                embed.add_field(name="Winner", value=f"<@{winner_id}> ({winner_name})", inline=False)
                embed.add_field(name="Total Votes", value=f"`{winner_votes}`", inline=True)
                embed.add_field(name="Total Pool", value=f"`${total_pool:.2f}`", inline=True)
                embed.add_field(name="Winner Payout (70%)", value=f"`${payout:.2f}`", inline=True)
                embed.add_field(name="Platform Fee (30%)", value=f"`${fee:.2f}`", inline=True)
                embed.add_field(name="Winning Track", value=f"[Download/Listen]({track_link})", inline=False)
                
                await channel.send(embed=embed)
                await channel.set_permissions(channel.guild.default_role, send_messages=False)

            results_channel = discord.utils.get(channel.guild.text_channels, name="results-winners")
            if results_channel:
                await results_channel.send(embed=embed)

    @commands.command(name="vote")
    async def vote(self, ctx, entrant_num: int):
        """Vote for an entrant in the current voting channel."""
        if len(ctx.author.roles) <= 1:
            embed = discord.Embed(
                title="Access Denied", 
                description="Only members with a role are allowed to vote.", 
                color=COLOR_ERROR
            )
            return await ctx.send(embed=embed)

        async with get_db() as db:
            cursor = await db.execute("SELECT battle_id FROM battles WHERE voting_channel_id = ? AND status = 'voting'", (ctx.channel.id,))
            row = await cursor.fetchone()
            if not row:
                embed = discord.Embed(title="Error", description="This is not an active voting channel.", color=COLOR_ERROR)
                return await ctx.send(embed=embed)
            
            battle_id = row[0]
            
            cursor = await db.execute("SELECT 1 FROM votes WHERE battle_id = ? AND voter_id = ?", (battle_id, ctx.author.id))
            if await cursor.fetchone():
                embed = discord.Embed(title="Error", description="You have already voted in this battle.", color=COLOR_ERROR)
                return await ctx.send(embed=embed)

            cursor = await db.execute(
                "SELECT entrant_id FROM entrants WHERE battle_id = ? AND payment_status = 'paid' AND disqualified = 0 LIMIT 1 OFFSET ?",
                (battle_id, entrant_num - 1)
            )
            entrant_row = await cursor.fetchone()
            if not entrant_row:
                embed = discord.Embed(title="Error", description="Invalid entrant number.", color=COLOR_ERROR)
                return await ctx.send(embed=embed)
            
            entrant_id = entrant_row[0]
            
            await db.execute(
                "INSERT INTO votes (battle_id, voter_id, entrant_id) VALUES (?, ?, ?)",
                (battle_id, ctx.author.id, entrant_id)
            )
            await db.commit()
            
            embed = discord.Embed(
                title="Vote Recorded", 
                description=f"Your vote for entrant `{entrant_num}` has been recorded.", 
                color=COLOR_SUCCESS
            )
            await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Voting(bot))
