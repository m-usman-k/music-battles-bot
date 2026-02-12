# Music Battles Bot

A Professional Discord bot for organizing automated music battles with cash prizes using a coin-based economy.

## Features
- **Genre-based Battles**: Organized by Rock, Trap, Hip Hop, etc.
- **Entry Pools**: $5, $15, and $25 pools.
- **Coin System**: Users buy Battle Coins to participate in competitions.
- **Voting System**: 24-hour voting window with auto-tallying.
- **Automated Announcements**: Winners and results posted automatically.
- **Roles**:
  - `Creator`: Automatically assigned to battle participants.
  - `Admin`: Full control over the bot and server.
- **Global Economy**: Battle Coins can be purchased via Stripe or PayPal.

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure `.env`:
   - `BOT_TOKEN`: Your Discord bot token.
   - `STRIPE_API_KEY`: Your Stripe secret key.
   - `PAYPAL_CLIENT_ID`: Your PayPal Client ID.
   - `PAYPAL_CLIENT_SECRET`: Your PayPal Secret Key.
   - `COLOR_SUCCESS`, `COLOR_ERROR`, `COLOR_INFO`: Hex colors for embeds.
3. Run the bot:
   ```bash
   python main.py
   ```
4. Initial Discord Setup:
   - Use `!setup_server` as an administrator to create the necessary channels, categories, and roles.

## Commands
Type `!help` in Discord to see a comprehensive list of all available commands and their descriptions.

## How it Works
1. Users purchase coins using `!buy_coins`.
2. They select a genre pool channel (e.g., `#rock #5-pool`).
3. They upload their music file and use `!enter`.
4. If they have sufficient coins, the entry is activated immediately.
5. Admin uses `!start_battle` to begin the voting phase.
6. A voting channel is created automatically.
7. Users have 24 hours to vote using `!vote`.
8. The bot automatically tallies votes, announces the winner, and locks the channel.
9. Admin uses `!payouts` to see who to pay out.
