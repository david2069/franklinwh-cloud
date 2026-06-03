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
        
    fetcher = PasswordAuth(email, password, login_type=0)
    await fetcher.get_token()
    
    client = Client(fetcher, gateway)
    
    print("--- Fetching current gateway TOU Dispatch Detail ---")
    res = await client.get_tou_dispatch_detail()
    
    if "result" not in res:
        print("Error: No result in response", res)
        return
        
    result = res["result"]
    strategies = result.get("strategyList", [])
    
    print("\n--- detailDefaultVo Sample ---")
    default_vo = result.get("detailDefaultVo", {})
    print("touDispatchList keys/values:")
    for item in default_vo.get("touDispatchList", []):
        print(f"  id: {item.get('id')} | dispatchCode: {item.get('dispatchCode')} | name: {item.get('title')} | solarPriority: {item.get('solarPriority')} | loadPriority: {item.get('loadPriority')}")
        
    print(f"Number of seasons in strategyList: {len(strategies)}")
    for i, s in enumerate(strategies):
        print(f"\nSeason {i+1}:")
        print(f"  seasonName: {s.get('seasonName')}")
        print(f"  month:      {s.get('month')}")
        print(f"  id:         {s.get('id')}")
        print(f"  templateId: {s.get('templateId')}")
        
        day_types = s.get("dayTypeVoList", [])
        print(f"  Number of day types in dayTypeVoList: {len(day_types)}")
        for j, dt in enumerate(day_types):
            print(f"    Day Type {j+1}:")
            print(f"      dayName: {dt.get('dayName')}")
            print(f"      dayType: {dt.get('dayType')}")
            # print all keys in day type Vo entry to see if any new keys are present
            dt_keys = list(dt.keys())
            print(f"      All keys in Day Type: {dt_keys}")
            
            blocks = dt.get("detailVoList", [])
            print(f"      Number of time blocks: {len(blocks)}")
            if blocks:
                print(f"      First time block keys: {list(blocks[0].keys())}")
                print(f"      First time block sample: {blocks[0]}")

if __name__ == "__main__":
    asyncio.run(main())
