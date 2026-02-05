#!/usr/bin/env python3
"""Simple test script for franklinwh library.

Uses franklinwh.ini for credentials to avoid exposing them in logs/screenshots.
"""

import asyncio
import configparser
import sys
from franklinwh import Client, TokenFetcher


async def main():
    """Test the franklinwh library."""
    
    # Read config file
    config = configparser.ConfigParser()
    config_file = "franklinwh.ini"
    
    if not config.read(config_file):
        print(f"❌ Error: {config_file} not found!")
        print(f"Create {config_file} with the following format:")
        print("""
[energy.franklinwh.com]
email = your.email@example.com
password = your_password

[gateways.enabled]
serialno = YOUR_GATEWAY_SERIAL
""")
        sys.exit(1)
    
    # Get credentials
    email = config.get('energy.franklinwh.com', 'email')
    password = config.get('energy.franklinwh.com', 'password')
    gateway = config.get('gateways.enabled', 'serialno')
    
    print(f"🔧 Testing franklinwh library...")
    print(f"📍 Gateway: {gateway}")
    
    # Create client
    fetcher = TokenFetcher(email, password)
    client = Client(fetcher, gateway)
    
    # Test 1: Token refresh
    print("\n✅ Test 1: Token refresh...")
    await client.refresh_token()
    print(f"   Token obtained successfully!")
    
    # Test 2: Get device info
    print("\n✅ Test 2: Get device info...")
    device_info = await client.get_device_info()
    print(f"   Gateway ID: {device_info['result']['gatewayId']}")
    print(f"   Time Zone: {device_info['result']['zoneInfo']}")
    
    # Test 3: Get stats
    print("\n✅ Test 3: Get stats...")
    stats = await client.get_stats()
    print(f"   Battery SoC: {stats.current.battery_soc}%")
    print(f"   Solar Production: {stats.current.solar_production} kW")
    print(f"   Grid Use: {stats.current.grid_use} kW")
    print(f"   Home Load: {stats.current.home_load} kW")
    print(f"   Work Mode: {stats.current.work_mode_desc}")
    
    # Test 4: Get mode
    print("\n✅ Test 4: Get current mode...")
    mode_info = await client.get_mode()
    print(f"   Mode info retrieved successfully (keys: {list(mode_info.keys())[:5]}...)")
    
    print("\n🎉 All tests passed! Library is working correctly.")
    

if __name__ == "__main__":
    asyncio.run(main())
