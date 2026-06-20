import asyncio
import logging
import sys
from franklinwh_cloud import FranklinWHCloud, ForceVPPLockError

# Set debug logging to see the API responses if needed
# logging.basicConfig(level=logging.DEBUG)

async def main():
    print("Initializing FranklinWH Cloud Client...")
    fwh = FranklinWHCloud.from_config("franklinwh.ini")
    
    try:
        await fwh.login()
        await fwh.select_gateway()
    except Exception as e:
        print(f"Login failed: {e}")
        return
        
    print(f"Connected to gateway: {fwh.gateway}")
    
    print("Clearing any stuck sessions...")
    await fwh.force_emergency_clear()
    
    print("\nChecking current run status...")
    comp = await fwh.get_device_composite_info()
    runtime = comp.get("result", {}).get("runtimeData", {})
    run_status = runtime.get("run_status")
    mode = runtime.get("mode")
    print(f"Current run_status: {run_status}")
    print(f"Current mode: {mode}")
    if run_status == 9 or mode == 9:
        print("Modbus/VPP mode is currently ACTIVE on the hardware.")
    else:
        print("Modbus/VPP mode is NOT active. run_status is normal.")
    
    print("\nAttempting to start a 5-minute force_charge to 100%...")
    try:
        session = await fwh.force_charge(max_soc=100, duration_minutes=5)
        print(f"SUCCESS: Force charge started! Session ID: {session.session_id}")
        
        print("Waiting 10 seconds before releasing...")
        await asyncio.sleep(10)
        
        print("Releasing force mode...")
        await fwh.force_release()
        print("Session released. System returning to prior state.")
        
    except ForceVPPLockError as e:
        print(f"\nEXPECTED FAILURE: Preflight successfully caught the VPP Lockout!")
        print(f"Error Details: {e}")
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(main())
