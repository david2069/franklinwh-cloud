import asyncio
import os

from franklinwh_cloud.auth import PasswordAuth, TokenAuth
from franklinwh_cloud.client import Client

async def test_liveAuthFlow():
    email = "[REDACTED]@gmail.com"
    pwd = "cYvwi6-sibpox-byhcot"
    gateway = "10060006AXXXXXXXXX"

    print("1. Testing PasswordAuth flow...")
    fetcher = PasswordAuth(email, pwd)
    token = await fetcher.get_token()
    print(f" -> Successfully acquired token len={len(token)}")

    print("\n2. Testing TokenAuth flow (Bypassing credentials)...")
    # Wrap purely with TokenAuth to ensure the client natively supports static bypass
    # Never sending credentials natively
    static_fetcher = TokenAuth(token)
    client = Client(static_fetcher, gateway)
    
    # We execute a read-only hit to ensure the token actually validates upstream
    stats = await client.get_stats()
    print(f" -> Success! TokenAuth pulled stats: Battery SOC = {stats.current.battery_soc}%")

if __name__ == "__main__":
    asyncio.run(test_liveAuthFlow())
