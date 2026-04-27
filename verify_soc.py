import asyncio
from franklinwh_cloud import FranklinWHCloud

async def main():
    client = FranklinWHCloud.from_config("franklinwh.ini")
    await client.login()
    await client.select_gateway()
    
    print("--- Fetching current gateway TOU list ---")
    tou_raw_response = await client.get_tou_dispatch_detail()
    payload = tou_raw_response.get("result")
    
    if not payload:
        print("Failed to get TOU details")
        return
        
    print("-- Current values --")
    
    # We will modify the default load configs
    # But wait, maxSoc actually exists inside `getGatewayTouListV2` as well.
    # Where does it live in `getTouDispatchDetail`?
    # Let's inspect the `strategyList` structure to find maxSoc:
    found = False
    for strategy in payload.get("strategyList", []):
        for dayType in strategy.get("dayTypeVoList", []):
            for block in dayType.get("detailVoList", []):
                if "maxSoc" in block:
                    print(f"Found maxSoc {block['maxSoc']} in TOU block {block['name']}")
                    block["maxSoc"] = 93.0
                    found = True
                    break
    
    if not found:
        print("Could not find maxSoc in the TOU schedule blocks!")

    # Let's save it back using `saveTouDispatch`
    url = client.url_base + "hes-gateway/terminal/tou/saveTouDispatch"
    print("Sending saveTouDispatch with modifications...")
    
    res = await client._post(url, payload)
    print("Save result:", res.get("message") or res)
    
    print("--- Verifying ---")
    # Actually wait 2 seconds because the gateway takes a second to apply
    await asyncio.sleep(2)
    tou_ver_1 = await client.get_tou_dispatch_detail()
    
    for strategy in tou_ver_1.get("result", {}).get("strategyList", []):
        for dayType in strategy.get("dayTypeVoList", []):
            for block in dayType.get("detailVoList", []):
                if "maxSoc" in block:
                    print(f"Verified maxSoc now: {block['maxSoc']}")
                    break
            
if __name__ == "__main__":
    asyncio.run(main())
