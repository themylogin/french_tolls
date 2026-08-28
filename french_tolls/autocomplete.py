import json
import os

import aiohttp
from aiohttp import web

from . import db

API_KEY = os.environ["LOCATIONIQ_API_KEY"]


async def autocomplete(request):
    query = " ".join(request.query.get("q", "").split()).lower()[:200]
    if len(query) < 3:
        return web.json_response([])

    with db.connect() as connection:
        row = connection.execute(
            "SELECT response FROM autocomplete WHERE q = ?", (query,)).fetchone()
    if row:
        return web.Response(text=row[0], content_type="application/json")

    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.locationiq.com/v1/autocomplete", params={
            "key": API_KEY,
            "q": query,
            "limit": "5",
            "countrycodes": "fr",
            "accept-language": "fr",
            "normalizecity": "1",
            "dedupe": "1",
        }) as response:
            # 404 = nothing found, worth caching as an empty result.
            if response.status not in (200, 404):
                return web.json_response({"error": "locationiq http %d" % response.status}, status=502)

            places = await response.json() if response.status == 200 else []

    results = [
        {
            "name": place["display_name"],
            "main_text": place.get("display_place") or place["display_name"].split(",")[0],
            "secondary_text": place.get("display_address", ""),
            "lonlat": [float(place["lon"]), float(place["lat"])],
        }
        for place in places
    ]

    text = json.dumps(results, ensure_ascii=False)
    with db.connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO autocomplete VALUES (?, ?)", (query, text))
        connection.commit()

    return web.Response(text=text, content_type="application/json")
