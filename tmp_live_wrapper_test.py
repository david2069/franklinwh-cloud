import asyncio
import os
import sys

# Ensure library is in path
sys.path.insert(0, os.path.abspath('.'))

from franklinwh_cloud import FranklinWHCloud

async def prove_live_auth():
    print("=========================================================")
    print(" 📡 EXECUTING LIVE AUTHENTICATION VIA LEGACY FACADE       ")
    print("=========================================================")
    
    # Use the test cluster init file holding credentials
    try:
        # We point it to the franklinwh.ini located in the testing directory
        config_path = "franklinwh.ini" 
        if not os.path.exists(config_path):
            config_path = "tests/franklinwh.ini"
            
        client = FranklinWHCloud.from_config(config_path)
        print(f"✅ Init     : FranklinWHCloud instance created for {client.email}")
        
        await client.login()
        print(f"✅ Login    : Successfully generated and parsed Token Payload")
        
        await client.select_gateway()
        print(f"✅ Bind     : Auto-discovered and bound to aGate [{client.gateway}]")
        
        stats = await client.get_stats()
        print(f"✅ Proxy    : Client proxy fetched Live Data!")
        print(f"")
        print(f"🔋 Battery : {stats.current.battery_soc}%")
        print(f"☀️ Solar   : {stats.current.solar_production} kW")
        print(f"⚡️ Grid    : {stats.current.work_mode_desc}")
        print("=========================================================")
        
    except Exception as e:
        print(f"❌ FAILURE: {str(e)}")

if __name__ == "__main__":
    asyncio.run(prove_live_auth())
