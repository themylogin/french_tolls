import aiohttp
from aiohttp import web
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from . import db
from .config import config
from .models import Autocomplete


async def autocomplete(request):
    query = " ".join(request.query.get("q", "").split()).lower()[:200]
    if len(query) < 3:
        return web.json_response([])

    async with db.Session() as session:
        response = await session.scalar(
            select(Autocomplete.response).where(Autocomplete.q == query))

    if response is None:
        if not config.locationiq_api_key:
            return web.json_response(
                {"error": "LOCATIONIQ_API_KEY is not set, so place lookup is unavailable"},
                status=503)

        async with aiohttp.ClientSession() as http:
            async with http.get("https://api.locationiq.com/v1/autocomplete", params={
                "key": config.locationiq_api_key,
                "q": query,
                "limit": "5",
                "countrycodes": "fr",
                "accept-language": "fr",
                "normalizecity": "1",
                "dedupe": "1",
            }) as reply:
                if reply.status not in (200, 404):
                    return web.json_response(
                        {"error": "locationiq http %d" % reply.status}, status=502)

                response = await reply.json() if reply.status == 200 else []

        async with db.Session() as session:
            await session.execute(
                insert(Autocomplete)
                .values(q=query, response=response)
                .on_conflict_do_update(
                    index_elements=[Autocomplete.q], set_={"response": response}))
            await session.commit()

    return web.json_response([
        {
            "name": place["display_name"],
            "main_text": place.get("display_place") or place["display_name"].split(",")[0],
            "secondary_text": place.get("display_address", ""),
            "lonlat": [float(place["lon"]), float(place["lat"])],
        }
        for place in response
    ])
