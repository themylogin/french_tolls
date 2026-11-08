# -*- coding=utf-8 -*-
import logging
import math

from aiohttp import web

from . import refine as refine_module
from . import refuel as refuel_module
from . import relay
from .autocomplete import autocomplete
from .car import parse_car
from .config import config
from .osrm import NoRoute, RouterUnavailable, Routers
from .route import RouteError, get_route, link_through, planned_route, toll_cost

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


async def refuel(request):
    try:
        data = await request.json()
    except ValueError:
        return _refused()
    if not isinstance(data, dict):
        return _refused()

    parameters = parse_car(data.get("car"))
    fuel = data.get("fuel")
    if not _is_point(data.get("from")) or not _is_point(data.get("to")):
        return _refused()
    if data.get("route") not in ("optimal", "super_optimal"):
        return _refused()
    if parameters is None or not _is_number(fuel) or not 0 <= fuel <= parameters.tank_volume:
        return _refused()
    chosen = _chosen(data.get("chosen"))
    if chosen is None:
        return _refused()

    routers = Routers()
    try:
        planned = await planned_route(routers, data["from"], data["to"], data["route"])
        if planned is None:
            return web.json_response({"error": "no_split_route"}, status=404)
        answer = await refuel_module.plan(
            routers, planned, parameters, fuel, toll_cost, chosen=chosen,
            link_through=lambda finished, vias: link_through(routers, planned, finished, vias))
    except RouteError as e:
        return web.json_response({"error": e.cause}, status=502)
    except refuel_module.UnneededStation:
        return _refused()
    except NoRoute as e:
        logger.warning("could not route through the chosen stations: %s", e)
        return web.json_response({"error": "no_route"}, status=502)
    except RouterUnavailable as e:
        logger.warning("could not route a detour: %s", e)
        return web.json_response({"error": "router_unavailable"}, status=502)

    return web.json_response(answer)


def _chosen(value):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 20:
        return None

    chosen = []
    for entry in value:
        if not isinstance(entry, dict):
            return None
        position = (entry.get("latitude"), entry.get("longitude"))
        if not all(_is_number(coordinate) and math.isfinite(coordinate) for coordinate in position):
            return None
        chosen.append(position)
    return chosen


def _refused():
    return web.json_response({"error": "invalid_request"}, status=400)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_point(value):
    return (isinstance(value, list) and len(value) == 2
            and all(_is_number(coordinate) and math.isfinite(coordinate) for coordinate in value))


app = web.Application()
app.add_routes([web.get("/api/autocomplete", autocomplete)])
app.add_routes([web.post("/api/calculate", calculate)])
app.add_routes([web.post("/api/refuel", refuel)])
relay.install(app)
