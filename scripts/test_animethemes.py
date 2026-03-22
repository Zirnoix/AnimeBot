import asyncio
import aiohttp
from fetch_openings import iter_animethemes  # ou adapte l'import

async def main():
    async with aiohttp.ClientSession() as sess:
        count = 0
        async for a in iter_animethemes(sess):
            count += 1
            if count <= 3:
                print("exemple:", a.get("name") or a.get("slug") or a.get("id"))
        print("TOTAL récupérés:", count)

asyncio.run(main())
