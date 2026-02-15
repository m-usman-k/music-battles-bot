import discord
from discord.ext import commands
from discord import app_commands
from utils.database import get_db
from utils.constants import COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO, VOTING_DURATION_HOURS
from datetime import datetime, timedelta
import logging

logger = logging.getLogger('music_battles.admin')

class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="start_battle")
    @app_commands.checks.has_permissions(administrator=True)
    async def start_battle(self, interaction: discord.Interaction, battle_id: int):
        """Move a battle to the voting phase and created a dedicated voting channel."""
        # defer() is now handled globally in main.py
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT genre, pool_amount, status FROM battles WHERE battle_id = ?",
                (battle_id,)
            )
            row = await cursor.fetchone()
            
            if not row:
                embed = discord.Embed(title="Error", description="Battle not found.", color=COLOR_ERROR)
                return await interaction.followup.send(embed=embed)
            
            genre, pool_amount, status = row
            if status != 'pending':
                embed = discord.Embed(title="Error", description=f"Battle is already `{status}`.", color=COLOR_ERROR)
                return await interaction.followup.send(embed=embed)

            cursor = await db.execute(
                "SELECT e.entrant_id, u.username, e.track_link FROM entrants e JOIN users u ON e.user_id = u.user_id WHERE e.battle_id = ? AND e.payment_status = 'paid' AND e.disqualified = 0",
                (battle_id,)
            )
            entrants = await cursor.fetchall()

            if len(entrants) < 2:
                embed = discord.Embed(title="Error", description="At least 2 paid entrants are required to start a battle.", color=COLOR_ERROR)
                return await interaction.followup.send(embed=embed)

            category_name = f"{genre} Battles"
            category = discord.utils.get(interaction.guild.categories, name=category_name)
            if not category:
                category = await interaction.guild.create_category(category_name)

            voting_channel = await interaction.guild.create_text_channel(
                f"battle-{battle_id}-voting",
                category=category
            )

            voting_ends_at = datetime.utcnow() + timedelta(hours=VOTING_DURATION_HOURS)
            
            await db.execute(
                "UPDATE battles SET status = 'voting', voting_channel_id = ?, voting_ends_at = ? WHERE battle_id = ?",
                (voting_channel.id, voting_ends_at.isoformat(), battle_id)
            )
            await db.commit()

            header_embed = discord.Embed(
                title=f"Voting Started: {genre}", 
                description=(
                    f"**Battle ID:** {battle_id}\n"
                    f"**Prize Pool:** ${pool_amount}\n"
                    f"**Voting Ends:** {VOTING_DURATION_HOURS} hours from now.\n\n"
                    "React with ✅ to vote for your favorite tracks!"
                ),
                color=COLOR_INFO
            )
            await voting_channel.send(embed=header_embed)

            for i, (entrant_id, username, track_link) in enumerate(entrants, 1):
                submission_embed = discord.Embed(
                    title=f"Submission #{i}",
                    description=f"**Artist:** {username}\n**Track:** [Listen Here]({track_link})",
                    color=COLOR_SUCCESS
                )
                msg = await voting_channel.send(embed=submission_embed)
                await msg.add_reaction("✅")
                
                await db.execute(
                    "UPDATE entrants SET submission_message_id = ? WHERE entrant_id = ?",
                    (msg.id, entrant_id)
                )
            
            await db.commit()
            
            success_embed = discord.Embed(title="Success", description=f"Battle #{battle_id} has moved to voting phase in {voting_channel.mention}", color=COLOR_SUCCESS)
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
    
    @app_commands.command(name="sync")
    @app_commands.checks.has_permissions(administrator=True)
    async def sync(self, interaction: discord.Interaction):
        """Sync the command tree manually."""
        # defer() is now handled globally in main.py
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(f"Synced {len(synced)} command(s)")
        except Exception as e:
            await interaction.followup.send(f"Failed to sync: {e}")

async def setup(bot):
    await bot.add_cog(Admin(bot))
