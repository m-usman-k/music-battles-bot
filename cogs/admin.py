import discord
from discord.ext import commands
from discord import app_commands
from utils.database import get_db
from utils.constants import COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO, VOTING_DURATION_HOURS, GENRES, POOLS
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('music_battles.admin')

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="start_battle")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.choices(genre=[
        app_commands.Choice(name=g, value=g) for g in GENRES
    ])
    @app_commands.choices(pool_amount=[
        app_commands.Choice(name=f"${p}", value=float(p)) for p in POOLS
    ])
    async def start_battle(self, interaction: discord.Interaction, genre: str, pool_amount: float):
        """Move a battle to the voting phase manually."""
        # defer() is now handled globally in main.py
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT battle_id FROM battles WHERE genre = ? AND pool_amount = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
                (genre, pool_amount)
            )
            row = await cursor.fetchone()
            if not row:
                return await interaction.followup.send(f"No pending battle found for **{genre} ${pool_amount}**.")
            
            battle_id = row[0]

        battles_cog = self.bot.get_cog('Battles')
        if not battles_cog:
            return await interaction.followup.send("Battles system not loaded.")

        success, result = await battles_cog.start_battle_internal(interaction.guild, battle_id)
        
        if not success:
            embed = discord.Embed(title="Error", description=result, color=COLOR_ERROR)
            return await interaction.followup.send(embed=embed)

        success_embed = discord.Embed(title="Success", description=f"Battle #{battle_id} ({genre} ${pool_amount}) has moved to voting phase in {result.mention}", color=COLOR_SUCCESS)
        await interaction.followup.send(embed=success_embed)

    @app_commands.command(name="disqualify")
    @app_commands.checks.has_permissions(administrator=True)
    async def disqualify(self, interaction: discord.Interaction, user: discord.Member, battle_id: int):
        """Disqualify a user from a specific battle."""
        # defer() is now handled globally in main.py
        async with get_db() as db:
            await db.execute(
                "UPDATE entrants SET disqualified = 1 WHERE user_id = ? AND battle_id = ?",
                (user.id, battle_id)
            )
            await db.commit()
            
        embed = discord.Embed(
            title="Disqualified", 
            description=f"{user.mention} has been disqualified from Battle #{battle_id}.", 
            color=COLOR_SUCCESS
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="close_pool")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.choices(genre=[
        app_commands.Choice(name=g, value=g) for g in GENRES
    ])
    @app_commands.choices(pool_amount=[
        app_commands.Choice(name=f"${p}", value=float(p)) for p in POOLS
    ])
    async def close_pool(self, interaction: discord.Interaction, genre: str, pool_amount: float):
        """Close a specific pool by setting its status to 'active'."""
        # defer() is now handled globally in main.py
        async with get_db() as db:
            await db.execute(
                "UPDATE battles SET status = 'active' WHERE genre = ? AND pool_amount = ? AND status = 'pending'",
                (genre, pool_amount)
            )
            await db.commit()
            
        embed = discord.Embed(
            title="Pool Closed", 
            description=f"The {genre} ${pool_amount} pool has been closed for new entries.", 
            color=COLOR_SUCCESS
        )
        await interaction.followup.send(embed=embed)
    
    @app_commands.command(name="decide_winner")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.choices(genre=[
        app_commands.Choice(name=g, value=g) for g in GENRES
    ])
    @app_commands.choices(pool_amount=[
        app_commands.Choice(name=f"${p}", value=float(p)) for p in POOLS
    ])
    async def decide_winner(self, interaction: discord.Interaction, genre: str, pool_amount: float):
        """Instantly end a battle for a specific pool and pick a winner."""
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT battle_id, voting_channel_id FROM battles WHERE genre = ? AND pool_amount = ? AND status IN ('active', 'voting') ORDER BY created_at DESC LIMIT 1",
                (genre, pool_amount)
            )
            row = await cursor.fetchone()
            if not row:
                return await interaction.followup.send(f"No active or voting battle found for **{genre} ${pool_amount}**.")
            
            battle_id, voting_channel_id = row

        voting_cog = self.bot.get_cog('Voting')
        if not voting_cog:
            return await interaction.followup.send("Voting system not loaded.")

        await voting_cog.end_voting(battle_id, voting_channel_id, genre, pool_amount)
        await interaction.followup.send(f"Battle #{battle_id} ({genre} ${pool_amount}) has been instantly decided.")

    @app_commands.command(name="remove_entrant")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.choices(genre=[
        app_commands.Choice(name=g, value=g) for g in GENRES
    ])
    @app_commands.choices(pool_amount=[
        app_commands.Choice(name=f"${p}", value=float(p)) for p in POOLS
    ])
    async def remove_entrant(self, interaction: discord.Interaction, user: discord.Member, genre: str, pool_amount: float):
        """Remove an entrant from a pool and refund their coins."""
        # defer() is now handled globally in main.py
        async with get_db() as db:
            # 1. Fetch entrant and battle details by finding the active/pending battle for this pool
            cursor = await db.execute(
                """
                SELECT e.entrant_id, e.announcement_message_id, e.submission_message_id, 
                       b.genre, b.pool_amount, b.voting_channel_id, b.battle_id
                FROM entrants e 
                JOIN battles b ON e.battle_id = b.battle_id 
                WHERE e.user_id = ? 
                AND b.genre = ? 
                AND b.pool_amount = ? 
                AND b.status IN ('pending', 'active', 'voting')
                ORDER BY b.created_at DESC LIMIT 1
                """,
                (user.id, genre, pool_amount)
            )
            row = await cursor.fetchone()
            
            if not row:
                return await interaction.followup.send(f"No active entry found for {user.display_name} in the **{genre} ${pool_amount}** pool.")
            
            ent_id, ann_msg_id, sub_msg_id, genre, pool_amt, vote_chan_id, battle_id = row
            refund_amt = int(pool_amt)

            # 2. Database Transaction: Refund and Cleanup
            try:
                # Refund coins
                await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (refund_amt, user.id))
                
                # Update pool totals
                await db.execute(
                    "UPDATE pool_totals SET total_amount = total_amount - ?, entrant_count = entrant_count - 1 "
                    "WHERE genre = ? AND pool_type = ?",
                    (pool_amt, genre, pool_amt)
                )
                
                # Delete votes for this entrant
                await db.execute("DELETE FROM votes WHERE entrant_id = ?", (ent_id,))
                
                # Delete the entrant
                await db.execute("DELETE FROM entrants WHERE entrant_id = ?", (ent_id,))
                
                await db.commit()
                logger.info(f"Admin removed {user.name} from {genre} ${pool_amt} (Battle #{battle_id}). Refunded {refund_amt} coins.")
            except Exception as e:
                logger.error(f"Error during entrant removal database sync: {e}")
                return await interaction.followup.send("An error occurred while updating the database.")

        # 3. Discord Cleanup: Deleting messages
        # Delete announcement in pool channel
        try:
            category = discord.utils.get(interaction.guild.categories, name=genre)
            if category:
                chan_name = f"{int(pool_amt)}-pool"
                channel = discord.utils.get(category.text_channels, name=chan_name)
                if channel and ann_msg_id:
                    msg = await channel.fetch_message(ann_msg_id)
                    await msg.delete()
        except:
            pass

        # Delete submission in voting channel
        try:
            if vote_chan_id and sub_msg_id:
                channel = interaction.guild.get_channel(vote_chan_id)
                if channel:
                    msg = await channel.fetch_message(sub_msg_id)
                    await msg.delete()
        except:
            pass

        embed = discord.Embed(
            title="Entrant Removed", 
            description=f"Successfully removed {user.mention} from Battle #{battle_id} and refunded **{refund_amt} coins**.", 
            color=COLOR_SUCCESS
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="sync")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync_slash(self, interaction: discord.Interaction):
        """Sync the command tree manually (Slash Version)."""
        # defer() is now handled globally in main.py
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(f"Synced {len(synced)} command(s)")
        except Exception as e:
            await interaction.followup.send(f"Failed to sync: {e}")

    @commands.command(name="sync")
    @commands.has_permissions(administrator=True)
    async def sync_prefix(self, ctx):
        """Sync the command tree manually (Prefix Version: !sync)."""
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"Synced {len(synced)} command(s)")
        except Exception as e:
            await ctx.send(f"Failed to sync: {e}")

async def setup(bot):
    await bot.add_cog(Admin(bot))
