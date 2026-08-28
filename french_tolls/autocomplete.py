import json
import os
import sqlite3

import aiohttp
from aiohttp import web

API_KEY = os.environ["LOCATIONIQ_API_KEY"]
CACHE = os.environ.get("AUTOCOMPLETE_CACHE", "/data/autocomplete.sqlite")


async def autocomplete(request):
    query = " ".join(request.query.get("q", "").split()).lower()[:200]
    if len(query) < 3:
        return web.json_response([])

    db = sqlite3.connect(CACHE)
    db.execute("CREATE TABLE IF NOT EXISTS cache (q TEXT PRIMARY KEY, response TEXT)")

    row = db.execute("SELECT response FROM cache WHERE q = ?", (query,)).fetchone()
    if row:
        db.close()
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
                db.close()
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
    db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?)", (query, text))
    db.commit()
    db.close()

    return web.Response(text=text, content_type="application/json")
