import asyncio
import aiohttp
import re
import json

url = "https://open.spotify.com/track/4kV0ugCwyF70Ab3huIdThG?si=20d0d20c70a641c5"

async def test():
    headers = {'User-Agent': 'Mozilla/5.0'}
    track_match = re.search(r'track/([a-zA-Z0-9]+)', url)
    item_id = track_match.group(1) if track_match else None
    print("Item ID:", item_id)
    
    oembed_api = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{item_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(oembed_api, headers=headers) as resp:
            print("oEmbed Status:", resp.status)
            if resp.status == 200:
                data = await resp.json()
                print("oEmbed Data:", data)

asyncio.run(test())
