import os
from dotenv import load_dotenv

load_dotenv()

GENRES = [
    "Rock", "Trap", "Hip Hop", "Country", "Chill Lo-Fi", 
    "Pop", "R&B", "Reggae", "Metal", "Gospel", "Electronic"
]

POOLS = [5.0, 15.0, 25.0]

PLATFORM_FEE_PERCENT = 0.30
WINNER_PAYOUT_PERCENT = 0.70
VOTING_DURATION_HOURS = 24

# Colors
COLOR_SUCCESS = int(os.getenv('COLOR_SUCCESS', '0x00FF00'), 16)
COLOR_ERROR = int(os.getenv('COLOR_ERROR', '0xFF0000'), 16)
COLOR_INFO = int(os.getenv('COLOR_INFO', '0x5865F2'), 16)

# Roles
CREATOR_ROLE_NAME = os.getenv('CREATOR_ROLE_NAME', 'Creator')
VOTER_ROLE_NAME = os.getenv('VOTER_ROLE_NAME', 'Voter')

# Stripe
STRIPE_API_KEY = os.getenv('STRIPE_API_KEY')

# PayPal
PAYPAL_CLIENT_ID = os.getenv('PAYPAL_CLIENT_ID')
PAYPAL_CLIENT_SECRET = os.getenv('PAYPAL_CLIENT_SECRET')
PAYPAL_MODE = os.getenv('PAYPAL_MODE', 'live').lower()
PAYPAL_API_BASE = "https://api-m.paypal.com" if PAYPAL_MODE == 'live' else "https://api-m.sandbox.paypal.com"
