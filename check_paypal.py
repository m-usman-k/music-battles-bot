import asyncio
import aiohttp
import base64
import os
from dotenv import load_dotenv

async def check_credentials():
    # Reload .env to catch changes
    load_dotenv(override=True)
    
    client_id = os.getenv('PAYPAL_CLIENT_ID', '').strip()
    client_secret = os.getenv('PAYPAL_CLIENT_SECRET', '').strip()
    
    if not client_id or not client_secret:
        print("Error: PAYPAL_CLIENT_ID or PAYPAL_CLIENT_SECRET not found in .env")
        return

    print(f"--- Checking Credentials ---")
    print(f"Client ID: {client_id[:10]}...")
    
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    
    endpoints = [
        ("Live", "https://api-m.paypal.com/v1/oauth2/token"),
        ("Sandbox", "https://api-m.sandbox.paypal.com/v1/oauth2/token")
    ]
    
    async with aiohttp.ClientSession() as session:
        for name, url in endpoints:
            print(f"Testing {name} API...")
            try:
                async with session.post(
                    url,
                    headers={"Authorization": f"Basic {auth}"},
                    data={"grant_type": "client_credentials"},
                    timeout=10
                ) as resp:
                    data = await resp.json()
                    if resp.status == 200:
                        print(f"✅ {name}: SUCCESS! Token received.")
                    else:
                        print(f"❌ {name}: FAILED ({resp.status}) - {data.get('error_description', data.get('error', 'Unknown error'))}")
            except Exception as e:
                print(f"❌ {name}: Connection error - {e}")

if __name__ == '__main__':
    asyncio.run(check_credentials())
