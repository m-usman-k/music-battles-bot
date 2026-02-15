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

class GlobalDeferTree(app_commands.CommandTree):
    """Custom CommandTree to handle global interaction deferral immediately."""
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # We only want to defer Slash Commands (not context menus unless needed)
        if interaction.type == discord.InteractionType.application_command:
            # Determine if this command should be ephemeral or not
            # Based on user request: /help and /balance are non-ephemeral
            command_name = interaction.command.name if interaction.command else None
            is_non_ephemeral = command_name in ['help', 'balance']
            
            # Diagnostic Latency Logging
            now = discord.utils.utcnow()
            latency = (now - interaction.created_at).total_seconds()
            
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer(ephemeral=not is_non_ephemeral)
                    logger.info(f"Globally deferred /{command_name} in {latency:.2f}s (Ephemeral: {not is_non_ephemeral})")
                else:
                    logger.info(f"Interaction for /{command_name} was already done (Received after {latency:.2f}s)")
            except Exception as e:
                logger.error(f"FAILED to globally defer /{command_name} after {latency:.2f}s: {e}")
                # If we get a 404 here, it's 100% because latency was > 3s
        
        return True

class MusicBattlesBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(
            command_prefix='!', 
            intents=intents, 
            help_command=None,
            tree_cls=GlobalDeferTree # Use our custom tree
        )

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
        
        # Manual sync via /sync is preferred to avoid startup delays
        # but we do one first sync if the tree is empty
        # try:
        #     synced = await self.tree.sync()
        #     logger.info(f"Synced {len(synced)} command(s)")
        # except Exception as e:
        #     logger.error(f"Failed to sync command tree: {e}")

    async def on_ready(self):
        logger.info(f'Logged in as {self.user.name} ({self.user.id})')
        logger.info(f'Process ID (PID): {os.getpid()}') # Added PID logging
        await self.change_presence(activity=discord.Game(name="Music Battles"))

    async def on_command_error(self, ctx, error):
        from utils.constants import COLOR_ERROR
        if isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="Missing Argument", 
                description=f"You are missing a required argument: `{error.param.name}`\n\nUse !help to see correct usage.", 
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
        
        # Unpack CommandInvokeError to see the real cause
        original_error = getattr(error, 'original', error)
        
        if isinstance(original_error, discord.NotFound):
            logger.warning(f'Resource not found during command {interaction.command}: {original_error}')
            return # Don't bother the user with "Not Found" errors during setup/cleanup

        logger.error(f'App Command Error: {error}')
        
        # Gracefully handle errors even if interaction was deferred
        embed = discord.Embed(title="Error", description=f"An error occurred: {error}", color=COLOR_ERROR)
        
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)
        except:
            pass

async def main():
    if not os.path.exists('./cogs'):
        os.makedirs('./cogs')
    
    bot = MusicBattlesBot()
    
    async with bot:
        await bot.start(TOKEN)

if __name__ == '__main__':
    asyncio.run(main())
