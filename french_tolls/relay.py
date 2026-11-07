# -*- coding=utf-8 -*-
import hmac
import logging

import aiohttp
from aiohttp import web
import yarl

from .config import config
from .osrm import REQUEST_TIMEOUT_S

logger = logging.getLogger(__name__)

__all__ = ["install"]


def install(app: web.Application):
    if config.osrm_access_token:
        app.add_routes([
            web.get("/api/osrm/{graph:toll|optimal}/{rest:.*}", forward, allow_head=False),
        ])


async def forward(request: web.Request) -> web.Response:
    if not hmac.compare_digest(request.headers.get("X-Auth", ""), config.osrm_access_token):
        return web.json_response(
            {"code": "Unauthorized", "message": "X-Auth does not match OSRM_ACCESS_TOKEN"},
            status=401,
        )

    graph = request.match_info["graph"]
    bases = {"toll": config.osrm_toll_url, "optimal": config.osrm_optimal_url}
    # The raw target, not the match info: decoding turns a hint's %2B into a
    # `+`, which the router then reads as a space.
    rest = request.raw_path[len(f"/api/osrm/{graph}"):]
    url = yarl.URL(bases[graph] + rest, encoded=True)

    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers={"X-Auth": config.osrm_access_token}) as resp:
                body = await resp.read()
                headers = {}
                if "Content-Type" in resp.headers:
                    headers["Content-Type"] = resp.headers["Content-Type"]
                return web.Response(status=resp.status, body=body, headers=headers)
    except (aiohttp.ClientError, TimeoutError) as e:
        logger.warning("the %s router did not answer: %s", graph, e)
        return web.json_response(
            {"code": "RouterUnavailable", "message": f"the {graph} router did not answer"},
            status=502,
        )
