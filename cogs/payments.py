import discord
from discord.ext import commands, tasks
from discord import app_commands
from utils.database import get_db
from utils.constants import COLOR_SUCCESS, COLOR_ERROR, COLOR_INFO, STRIPE_API_KEY, PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET, PAYPAL_API_BASE, GENRES, POOLS, WINNER_PAYOUT_PERCENT
import stripe
import asyncio
import logging
import aiohttp
import base64

logger = logging.getLogger('music_battles.payments')
stripe.api_key = STRIPE_API_KEY

COIN_PRICE = 1.00

class VerifyCoinPaymentView(discord.ui.View):
    def __init__(self, session_id, user_id, coins_to_add, method, cog):
        super().__init__(timeout=600)
        self.session_id = session_id
        self.user_id = user_id
        self.coins_to_add = coins_to_add
        self.method = method
        self.cog = cog

    @discord.ui.button(label="Verify Purchase", style=discord.ButtonStyle.green)
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(title="Access Denied", description="This button is not for you.", color=COLOR_ERROR)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            is_paid = False
            if self.method == 'stripe':
                # session = stripe.checkout.Session.retrieve(self.session_id)
                session = await asyncio.to_thread(stripe.checkout.Session.retrieve, self.session_id)
                is_paid = (session.payment_status == 'paid')
            else:
                status = await self.cog._verify_paypal_order(self.session_id)
                if status == 'APPROVED':
                    capture_status = await self.cog._capture_paypal_order(self.session_id)
                    is_paid = (capture_status == 'COMPLETED')
                else:
                    is_paid = (status == 'COMPLETED')

            if is_paid:
                async with get_db() as db:
                    await db.execute(
                        "UPDATE users SET coins = coins + ? WHERE user_id = ?",
                        (self.coins_to_add, self.user_id)
                    )
                    await db.commit()

                button.disabled = True
                button.label = "Verified"
                await interaction.edit_original_response(view=self)
                
                embed = discord.Embed(
                    title="Payment Confirmed", 
                    description=f"Successfully added **{self.coins_to_add}** coins to your account.", 
                    color=COLOR_SUCCESS
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(title="Payment Pending", description="We could not verify your payment yet. Please ensure checkout is complete.", color=COLOR_ERROR)
                await interaction.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"Error verifying coin purchase: {e}")
            embed = discord.Embed(title="Error", description="An error occurred during verification.", color=COLOR_ERROR)
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

class BuyCoinsView(discord.ui.View):
    def __init__(self, user_id, amount_usd, cog):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.amount_usd = amount_usd
        self.cog = cog

    @discord.ui.button(label="Pay with Card", style=discord.ButtonStyle.blurple)
    async def stripe_pay(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(title="Access Denied", description="This menu is not for you.", color=COLOR_ERROR)
            return await interaction.response.send_message(embed=embed, ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        try:
            session = await asyncio.to_thread(
                stripe.checkout.Session.create,
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {'name': f'{int(self.amount_usd)} Battle Coins'},
                        'unit_amount': int(self.amount_usd * 100),
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url='https://discord.com',
                cancel_url='https://discord.com',
            )
            embed = discord.Embed(
                title="Stripe Checkout", 
                description=f"Quantity: **{int(self.amount_usd)} coins**\nTotal: **${self.amount_usd:.2f}**\n\nPlease complete the payment using the link below.", 
                color=COLOR_INFO
            )
            embed.add_field(name="Link", value=f"[Open Payment Page]({session.url})", inline=False)
            view = VerifyCoinPaymentView(session.id, self.user_id, int(self.amount_usd), 'stripe', self.cog)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(title="Error", description="Failed to create payment link.", color=COLOR_ERROR)
            await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="Pay with PayPal", style=discord.ButtonStyle.gray)
    async def paypal_pay(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            embed = discord.Embed(title="Access Denied", description="This menu is not for you.", color=COLOR_ERROR)
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        try:
            order = await self.cog._create_paypal_order(self.amount_usd, f"{int(self.amount_usd)} Battle Coins")
            approve_url = next(link['href'] for link in order['links'] if link['rel'] == 'approve')
            embed = discord.Embed(
                title="PayPal Checkout", 
                description=f"Quantity: **{int(self.amount_usd)} coins**\nTotal: **${self.amount_usd:.2f}**\n\nPlease complete the payment using the link below.", 
                color=COLOR_INFO
            )
            embed.add_field(name="Link", value=f"[Open Payment Page]({approve_url})", inline=False)
            view = VerifyCoinPaymentView(order['id'], self.user_id, int(self.amount_usd), 'paypal', self.cog)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(title="Error", description="Failed to create payment link.", color=COLOR_ERROR)
            await interaction.followup.send(embed=embed, ephemeral=True)

class Payments(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_live_stats.start()

    def cog_unload(self):
        self.update_live_stats.cancel()

    async def _get_paypal_token(self):
        auth = base64.b64encode(f"{PAYPAL_CLIENT_ID}:{PAYPAL_CLIENT_SECRET}".encode()).decode()
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{PAYPAL_API_BASE}/v1/oauth2/token",
                headers={"Authorization": f"Basic {auth}"},
                data={"grant_type": "client_credentials"}
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    logger.error(f"PayPal Token Error: {resp.status} - {data}")
                    return None
                return data.get('access_token')

    async def _create_paypal_order(self, amount, desc):
        token = await self._get_paypal_token()
        if not token:
            raise Exception("Failed to get PayPal access token.")
            
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{PAYPAL_API_BASE}/v2/checkout/orders",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"intent": "CAPTURE", "purchase_units": [{"amount": {"currency_code": "USD", "value": str(amount)}, "description": desc}]}
            ) as resp:
                data = await resp.json()
                if resp.status not in [200, 201]:
                    logger.error(f"PayPal Order Error: {resp.status} - {data}")
                    raise Exception(f"PayPal API error: {data.get('message', 'Unknown error')}")
                return data

    async def _verify_paypal_order(self, order_id):
        token = await self._get_paypal_token()
        if not token: return None
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}", headers={"Authorization": f"Bearer {token}"}) as resp:
                data = await resp.json()
                return data.get('status')

    async def _capture_paypal_order(self, order_id):
        token = await self._get_paypal_token()
        if not token: return None
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{PAYPAL_API_BASE}/v2/checkout/orders/{order_id}/capture", headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}) as resp:
                data = await resp.json()
                return data.get('status')

    @tasks.loop(minutes=5)
    async def update_live_stats(self):
        for guild in self.bot.guilds:
            channel = discord.utils.get(guild.text_channels, name="live-stats")
            if channel:
                stats_embed = await self.get_stats_embed()
                async for message in channel.history(limit=5):
                    if message.author == self.bot.user:
                        await message.edit(embed=stats_embed)
                        break
                else:
                    await channel.send(embed=stats_embed)

    async def get_stats_embed(self, genre_filter=None):
        async with get_db() as db:
            cursor = await db.execute("SELECT genre, pool_type, total_amount, entrant_count FROM pool_totals")
            rows = await cursor.fetchall()
            
            # Map existing stats for quick lookup
            stats_map = {(r[0], r[1]): (r[2], r[3]) for r in rows}
            
            title = f"Live Prize Pools: {genre_filter}" if genre_filter else "Live Prize Pools"
            embed = discord.Embed(title=title, color=COLOR_INFO)
            embed.set_footer(text="Join a pool by entering its channel and typing /enter")
            
            genres_to_show = [genre_filter] if genre_filter else GENRES
            for g in genres_to_show:
                category_stats = []
                for p in POOLS:
                    total, count = stats_map.get((g, p), (0.0, 0))
                    winner_prize = total * WINNER_PAYOUT_PERCENT
                    
                    status = f"**${p} Pool**: `${total:.2f}` (Winner: `${winner_prize:.2f}`)"
                    if count == 0:
                        status += "\n*No entrants*"
                    else:
                        # Query for the top 3 leaders in this genre/pool
                        leader_cursor = await db.execute(
                            """
                            SELECT u.username, COUNT(v.vote_id) as vote_count 
                            FROM entrants e 
                            JOIN users u ON e.user_id = u.user_id 
                            LEFT JOIN votes v ON e.entrant_id = v.entrant_id 
                            WHERE e.battle_id = (
                                SELECT battle_id FROM battles 
                                WHERE genre = ? AND pool_amount = ? AND status IN ('pending', 'active', 'voting') 
                                ORDER BY created_at DESC LIMIT 1
                            ) 
                            AND e.payment_status = 'paid'
                            AND e.disqualified = 0
                            GROUP BY e.entrant_id 
                            ORDER BY vote_count DESC, e.entrant_id ASC
                            LIMIT 3
                            """,
                            (g, float(p))
                        )
                        leaders = await leader_cursor.fetchall()
                        if leaders:
                            leaderboard = []
                            for i, (name, votes) in enumerate(leaders, 1):
                                emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
                                leaderboard.append(f"{emoji} {name} (`{votes}v`)")
                            status += "\n" + "\n".join(leaderboard)
                    
                    category_stats.append(status + "\n")
                
                embed.add_field(
                    name=f"--- {g} ---",
                    value="\n".join(category_stats),
                    inline=True
                )
            return embed

    @app_commands.command(name="pools")
    @app_commands.choices(genre=[
        app_commands.Choice(name=g, value=g) for g in GENRES
    ])
    async def pools(self, interaction: discord.Interaction, genre: str = None):
        """Check the current prize money in each pool."""
        # defer() is now handled globally in main.py
        embed = await self.get_stats_embed(genre)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="buy_coins")
    @app_commands.choices(amount=[
        app_commands.Choice(name="5 Coins ($5.00)", value=5),
        app_commands.Choice(name="10 Coins ($10.00)", value=10),
        app_commands.Choice(name="20 Coins ($20.00)", value=20),
        app_commands.Choice(name="50 Coins ($50.00)", value=50),
        app_commands.Choice(name="100 Coins ($100.00)", value=100)
    ])
    async def buy_coins(self, interaction: discord.Interaction, amount: int):
        """Purchase battle coins (1 Coin = $1.00)."""
        # defer() is now handled globally in main.py
        if amount <= 0:
            embed = discord.Embed(title="Invalid Amount", description="Please specify a positive number of coins.", color=COLOR_ERROR)
            return await interaction.followup.send(embed=embed)
        
        async with get_db() as db:
            await db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (interaction.user.id, interaction.user.name))
            await db.commit()

        embed = discord.Embed(
            title="Purchase Coins", 
            description=(
                f"You are about to purchase **{amount} Battle Coins**.\n\n"
                f"Total Price: **${amount:.2f}**\n"
                "Rate: **1 Coin = $1.00**\n\n"
                "Please select your preferred payment method below."
            ), 
            color=COLOR_INFO
        )
        embed.set_footer(text="Payments are processed securely via Stripe or PayPal.")
        view = BuyCoinsView(interaction.user.id, float(amount), self)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="balance")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        """Check your coin balance or another user's balance (Admins only)."""
        # defer() is now handled globally in main.py
        target = member or interaction.user
        
        # Check permissions if checking someone else
        if member and member != interaction.user and not interaction.user.guild_permissions.administrator:
            embed = discord.Embed(title="Access Denied", description="You do not have permission to check other users' balances.", color=COLOR_ERROR)
            return await interaction.followup.send(embed=embed)

        async with get_db() as db:
            cursor = await db.execute("SELECT coins FROM users WHERE user_id = ?", (target.id,))
            row = await cursor.fetchone()
            coins = row[0] if row else 0
        
        title = "Account Balance" if target == interaction.user else f"Balance for {target.display_name}"
        desc = f"You currently have **{coins}** Battle Coins." if target == interaction.user else f"{target.mention} currently has **{coins}** Battle Coins."
        
        embed = discord.Embed(title=title, description=desc, color=COLOR_INFO)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="add_coins")
    @app_commands.checks.has_permissions(administrator=True)
    async def add_coins(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        """Admin: Manually add coins to a user."""
        # defer() is now handled globally in main.py
        async with get_db() as db:
            await db.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user.id, user.name))
            await db.execute("UPDATE users SET coins = coins + ? WHERE user_id = ?", (amount, user.id))
            await db.commit()
        
        embed = discord.Embed(title="Coins Added", description=f"Successfully added **{amount}** coins to {user.mention}.", color=COLOR_SUCCESS)
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="payouts")
    @app_commands.checks.has_permissions(administrator=True)
    async def payouts(self, interaction: discord.Interaction):
        """Admin: View winners and amounts owed."""
        # defer() is now handled globally in main.py
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT u.username, b.genre, b.pool_amount, b.battle_id FROM battles b JOIN entrants e ON b.battle_id = e.battle_id JOIN users u ON e.user_id = u.user_id "
                "WHERE b.status = 'completed' AND e.payment_status = 'paid' AND e.entrant_id = (SELECT v.entrant_id FROM votes v WHERE v.battle_id = b.battle_id GROUP BY v.entrant_id ORDER BY COUNT(*) DESC LIMIT 1)"
            )
            rows = await cursor.fetchall()
            
            if not rows:
                embed = discord.Embed(title="Owed Payouts", description="No pending payouts found.", color=COLOR_INFO)
                return await interaction.followup.send(embed=embed)
                
            embed = discord.Embed(title="Owed Payouts", color=COLOR_SUCCESS)
            for username, genre, pool, bid in rows:
                count_cursor = await db.execute("SELECT COUNT(*) FROM entrants WHERE battle_id = ? AND payment_status = 'paid'", (bid,))
                n = (await count_cursor.fetchone())[0]
                embed.add_field(name=f"Battle #{bid}: {username}", value=f"**Genre:** {genre}\n**Pool:** ${pool}\n**Owed:** `${(n*pool)*0.7:.2f}`", inline=False)
            await interaction.followup.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Payments(bot))
