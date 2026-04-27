import asyncio
from franklinwh_cloud import Client

async def main():
    async with Client() as client:
        res = await client.get_tou_info(1)
        print(res)

asyncio.run(main())
