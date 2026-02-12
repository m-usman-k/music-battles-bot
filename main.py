import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('music_battles')

load_dotenv()
TOKEN = os.getenv('BOT_TOKEN')

class MusicBattlesBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix='!', intents=intents, help_command=None)

    async def setup_hook(self):
        from utils.database import init_db
        await init_db()
        
        # Load cogs
        if not os.path.exists('./cogs'):
            os.makedirs('./cogs')
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    logger.info(f'Loaded extension: {filename}')
                except Exception as e:
                    logger.error(f'Failed to load extension {filename}: {e}')
        
        # Sync command tree
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} command(s)")
        except Exception as e:
            logger.error(f"Failed to sync command tree: {e}")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user.name} ({self.user.id})')
        await self.change_presence(activity=discord.Game(name="Music Battles"))

    async def on_command_error(self, ctx, error):
        from utils.constants import COLOR_ERROR
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="Missing Argument", 
                description=f"You are missing a required argument: `{error.param.name}`\n\nUse `!help` to see correct usage.", 
                color=COLOR_ERROR
            )
            await ctx.send(embed=embed)
        elif isinstance(error, commands.CommandNotFound):
            pass 
        else:
            logger.error(f'Error in command {ctx.command}: {error}')
            embed = discord.Embed(title="Error", description="An unexpected error occurred while running the command.", color=COLOR_ERROR)
            await ctx.send(embed=embed)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        from utils.constants import COLOR_ERROR
        if isinstance(error, app_commands.MissingPermissions):
            embed = discord.Embed(title="Access Denied", description="You do not have permission to use this command.", color=COLOR_ERROR)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            logger.error(f'App Command Error: {error}')
            embed = discord.Embed(title="Error", description="An error occurred while processing this command.", color=COLOR_ERROR)
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

async def main():
    if not os.path.exists('./cogs'):
        os.makedirs('./cogs')
    
    bot = MusicBattlesBot()
    
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
