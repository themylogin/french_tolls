# -*- coding=utf-8 -*-
import logging

from aiohttp import web

from .autocomplete import autocomplete
from .service import get_route

logger = logging.getLogger(__name__)

__all__ = ["app"]


async def calculate(request):
    data = await request.json()

    return web.json_response(await get_route(data["from"], data["to"]))

app = web.Application()
app.add_routes([web.get("/api/autocomplete", autocomplete)])
app.add_routes([web.post("/api/calculate", calculate)])
