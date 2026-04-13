import asyncio
from franklinwh_cloud import FranklinWHCloud

async def run():
    c = FranklinWHCloud.from_config("../franklinwh-cloud-test/franklinwh.ini")
    await c.login()
    await c.select_gateway()
    print(await c.get_power_details(1, "2026-04-12"))

asyncio.run(run())
