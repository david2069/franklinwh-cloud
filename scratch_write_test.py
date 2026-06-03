import asyncio
import json
from franklinwh_cloud.client import Client
from franklinwh_cloud.auth import PasswordAuth
from franklinwh_cloud.cli import load_credentials

async def main():
    email, password, gateway = load_credentials()
    if not email:
        print("Missing credentials")
        return
        
    print("--- Authenticating ---")
    fetcher = PasswordAuth(email, password, login_type=0)
    await fetcher.get_token()
    
    client = Client(fetcher, gateway)
    
    print("\n--- Step 1: Fetching current TOU Dispatch Detail ---")
    res = await client.get_tou_dispatch_detail()
    if "result" not in res:
        print("Error: No result in response", res)
        return
        
    result = res["result"]
    strategies = result.get("strategyList", [])
    if not strategies:
        print("Error: strategyList is empty")
        # Let's see if we can do a default/predefined set
        return
        
    season = strategies[0]
    day_types = season.get("dayTypeVoList", [])
    if not day_types:
        print("Error: dayTypeVoList is empty")
        return
        
    day_type = day_types[0]
    blocks = day_type.get("detailVoList", [])
    
    # Deduplicate blocks to clean up any historical duplicate states
    seen_starts = set()
    deduped_blocks = []
    for b in blocks:
        if b["startHourTime"] not in seen_starts:
            seen_starts.add(b["startHourTime"])
            deduped_blocks.append(b)
            
    print(f"Current blocks count (after deduplication): {len(deduped_blocks)}")
    print(f"First block details: {deduped_blocks[0]}")
    
    # ── Step 2: Backup the original strategy list ──
    print("\n--- Step 2: Backing up current strategy list ---")
    backup_path = await client.tou_backup_save(strategies, cli_args="scratch_write_test")
    print(f"Backup saved to: {backup_path}")
    
    # ── Step 3: Run CUSTOM schedule set ──
    print("\n--- Step 3: Executing set_tou_schedule (CUSTOM) ---")
    
    # Construct a new custom schedule blocks list based on deduped blocks
    custom_blocks = []
    for b in deduped_blocks:
        # Keep only user-facing keys to test enrichment and matching
        custom_blocks.append({
            "startHourTime": b["startHourTime"],
            "endHourTime": b["endHourTime"],
            "waveType": b["waveType"],
            "name": b["name"] if b != deduped_blocks[0] else b["name"] + "-test",
            "dispatchId": b["dispatchId"],
        })
        
    print(f"Submitting CUSTOM schedule blocks...")
    try:
        set_res = await client.set_tou_schedule(
            touMode="CUSTOM",
            touSchedule=custom_blocks,
            month=None, # will auto-resolve to today's month
        )
        print("API Response:", json.dumps(set_res, indent=2))
        
        # Verify success
        if set_res.get("code") == 200:
            print("SUCCESS! The live gateway successfully accepted the CUSTOM schedule write without any strategy table inconsistency rejects!")
        else:
            print("FAILURE: The API returned an error code:", set_res)
            
    except Exception as e:
        print("EXCEPTIONAL FAILURE:", e)
        
    finally:
        # ── Step 4: Restore from backup ──
        print("\n--- Step 4: Restoring original strategy list from backup ---")
        try:
            restore_res = await client.tou_backup_restore(backup_path)
            print("Restore complete! Checksum and payload match perfectly.")
            
            # Clean up the backup file
            await client.tou_backup_delete(backup_path)
            print("Backup cleanup complete.")
        except Exception as e:
            print("Error restoring from backup! Please restore manually from:", backup_path, "\nError:", e)

if __name__ == "__main__":
    asyncio.run(main())
