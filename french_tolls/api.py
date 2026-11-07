# -*- coding=utf-8 -*-
import logging

from aiohttp import web

from . import refine as refine_module
from . import relay
from .autocomplete import autocomplete
from .config import config
from .route import get_route

logger = logging.getLogger(__name__)

__all__ = ["app"]


async def calculate(request):
    data = await request.json()
    answer = await get_route(data["from"], data["to"])

    if config.debug:
        refinement = await refine_module.refine(
            data["from"], data["to"], answer["optimal"])
        answer["google"] = {
            "nodes": refinement.nodes,
            "waypoints": refinement.waypoints,
            "added": refinement.added,
            "reason": refinement.reason,
        }

    return web.json_response(answer)


app = web.Application()
app.add_routes([web.get("/api/autocomplete", autocomplete)])
app.add_routes([web.post("/api/calculate", calculate)])
relay.install(app)
