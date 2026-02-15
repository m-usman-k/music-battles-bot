import discord
from discord.ext import commands, tasks
from discord import app_commands
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

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Handle reaction-based voting."""
        if payload.user_id == self.bot.user.id:
            return

        if str(payload.emoji) != "✅":
            # Remove invalid reactions
            guild = self.bot.get_guild(payload.guild_id)
            channel = guild.get_channel(payload.channel_id)
            if not channel: return
            try:
                message = await channel.fetch_message(payload.message_id)
                user = self.bot.get_user(payload.user_id)
                if user:
                    await message.remove_reaction(payload.emoji, user)
            except (discord.NotFound, discord.Forbidden):
                pass
            return

        async with get_db() as db:
            # Check if this message is a battle submission
            cursor = await db.execute(
                "SELECT entrant_id, battle_id FROM entrants WHERE submission_message_id = ?",
                (payload.message_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return

            entrant_id, battle_id = row

            # Insert vote (Unique constraint battle_id, voter_id handles double voting)
            try:
                await db.execute(
                    "INSERT INTO votes (battle_id, voter_id, entrant_id) VALUES (?, ?, ?)",
                    (battle_id, payload.user_id, entrant_id)
                )
                await db.commit()
                logger.info(f"Recorded reaction vote from {payload.user_id} for entrant {entrant_id}")
            except Exception as e:
                # If they already voted elsewhere in this battle, remove the new reaction
                guild = self.bot.get_guild(payload.guild_id)
                channel = guild.get_channel(payload.channel_id)
                if not channel: return
                try:
                    message = await channel.fetch_message(payload.message_id)
                    user = self.bot.get_user(payload.user_id)
                    if user:
                        await message.remove_reaction("✅", user)
                except (discord.NotFound, discord.Forbidden):
                    pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        """Handle reaction removal to sync votes."""
        if payload.user_id == self.bot.user.id:
            return

        if str(payload.emoji) != "✅":
            return

        async with get_db() as db:
            cursor = await db.execute(
                "SELECT entrant_id FROM entrants WHERE submission_message_id = ?",
                (payload.message_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return

            entrant_id = row[0]
            await db.execute(
                "DELETE FROM votes WHERE entrant_id = ? AND voter_id = ?",
                (entrant_id, payload.user_id)
            )
            await db.commit()
            logger.info(f"Removed reaction vote from {payload.user_id} for entrant {entrant_id}")

async def setup(bot):
    await bot.add_cog(Voting(bot))
