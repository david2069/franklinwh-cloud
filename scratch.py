import asyncio
from franklinwh_cloud import FranklinWHCloud

async def main():
    client = FranklinWHCloud.from_config("franklinwh.ini")
    await client.login()
    await client.select_gateway()
    
    print("--- Fetching current gateway TOU list ---")
    tou_raw = await client.get_gateway_tou_list()
    current_list = tou_raw["result"]["list"]
    
    # Mode 2 = Self Consumption
    mode_entry = next((item for item in current_list if item["workMode"] == 2), None)
    print("Before maxSoc:", mode_entry.get("maxSoc"))

    url = client.url_base + "hes-gateway/terminal/tou/updateTouModeV2"
    url += f"?gatewayId={client.gateway}"
    url += f"&currendId={mode_entry['id']}"
    url += f"&oldIndex={mode_entry['oldIndex']}"
    url += f"&workMode=2"
    url += f"&soc={mode_entry.get('soc', 5)}"
    url += f"&stromEn=1&electricityType=1"
    
    # NOW ADD maxSoc!
    url += f"&maxSoc=91.0"
    url += f"&complianceSoc=3.0"
    
    print("Sending updateTouModeV2...", url)
    res = await client._post(url, None)
    print("Save result:", res.get("message") or res)
    
    print("--- Verifying ---")
    await asyncio.sleep(2)
    tou_raw_new = await client.get_gateway_tou_list()
    mode_entry_new = next((item for item in tou_raw_new["result"]["list"] if item["workMode"] == 2), None)
    print("Verified maxSoc now:", mode_entry_new.get("maxSoc"))
            
if __name__ == "__main__":
    asyncio.run(main())
