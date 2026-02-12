import discord
from discord.ext import commands
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

    async def on_ready(self):
        logger.info(f'Logged in as {self.user.name} ({self.user.id})')
        await self.change_presence(activity=discord.Game(name="Music Battles"))

async def main():
    if not os.path.exists('./cogs'):
        os.makedirs('./cogs')
    
    bot = MusicBattlesBot()
    
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
