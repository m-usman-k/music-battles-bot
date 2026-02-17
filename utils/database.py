import aiosqlite
import os

DB_PATH = 'music_battles.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                coins INTEGER DEFAULT 0
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS battles (
                battle_id INTEGER PRIMARY KEY AUTOINCREMENT,
                genre TEXT,
                pool_amount REAL,
                status TEXT, -- 'pending', 'active', 'voting', 'completed'
                battle_channel_id INTEGER,
                voting_channel_id INTEGER,
                voting_ends_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS entrants (
                entrant_id INTEGER PRIMARY KEY AUTOINCREMENT,
                battle_id INTEGER,
                user_id INTEGER,
                track_link TEXT,
                payment_status TEXT, -- 'pending', 'paid'
                stripe_session_id TEXT,
                paypal_order_id TEXT,
                submission_message_id INTEGER,
                announcement_message_id INTEGER,
                disqualified INTEGER DEFAULT 0,
                FOREIGN KEY (battle_id) REFERENCES battles (battle_id),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Migration: Add announcement_message_id if it doesn't exist
        try:
            await db.execute("ALTER TABLE entrants ADD COLUMN announcement_message_id INTEGER")
            await db.commit()
        except aiosqlite.OperationalError:
            # Column already exists
            pass
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS votes (
                vote_id INTEGER PRIMARY KEY AUTOINCREMENT,
                battle_id INTEGER,
                voter_id INTEGER,
                entrant_id INTEGER,
                FOREIGN KEY (battle_id) REFERENCES battles (battle_id),
                FOREIGN KEY (voter_id) REFERENCES users (user_id),
                FOREIGN KEY (entrant_id) REFERENCES entrants (entrant_id),
                UNIQUE(battle_id, voter_id)
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS pool_totals (
                genre TEXT,
                pool_type REAL,
                total_amount REAL DEFAULT 0,
                entrant_count INTEGER DEFAULT 0,
                PRIMARY KEY (genre, pool_type)
            )
        ''')
        
        await db.commit()

def get_db():
    return aiosqlite.connect(DB_PATH)
