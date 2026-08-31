# -*- coding=utf-8 -*-
from datetime import datetime, timezone
import json
import logging
import os
import urllib.parse

from . import equivalence, osrm
from .config import config
from .booths import load
from .osrm import NoRoute, RouterUnavailable, Routers, TooFarFromNetwork
from .waypoints import MAX_WAYPOINTS, plan_waypoints
from .tolls import account, booths_crossed

logger = logging.getLogger(__name__)

__all__ = ["RouteError", "get_route"]

ERRORS_DIR = "/cache/errors"

BOOTHS = load()


class RouteError(Exception):
    def __init__(self, cause: str, message: str):
        self.cause = cause
        super().__init__(message)


def _record_failure(from_, to, cause, message):
    try:
        os.makedirs(ERRORS_DIR, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S.%f")
        with open(os.path.join(ERRORS_DIR, f"{stamp}.json"), "w") as f:
            json.dump({
                "from": list(from_),
                "to": list(to),
                "cause": cause,
                "message": message,
            }, f)
    except OSError as e:
        logger.warning("could not record failure: %s", e)


def google_maps_link(locations):
    """A Google Maps directions URL through `locations`, origin first."""
    d = {
        "api": "1",
        "origin": locations[0],
        "destination": locations[-1],
    }
    if len(locations) > 2:
        d["waypoints"] = "|".join(locations[1:-1])

    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(d)


def _as_latlon(coordinate) -> str:
    """`lat,lon` at six decimal places, which is what a Maps URL takes."""
    return f"{coordinate[1]:.6f},{coordinate[0]:.6f}"


def _for_delivery(answer, from_, to):
    """The travel-time correction, applied to both routes in place."""
    for route in answer.values():
        raw = route.get("duration_osrm", route["duration"])
        route["duration_osrm"] = raw
        route["duration"] = raw * config.time_multiplier

    return answer


def _describe(route: osrm.Route, plan, journey, booths=()) -> dict:
    """One route, in the shape every consumer already reads."""
    points = [_as_latlon(route.coordinates[0])]
    points += [_as_latlon(c) for c in (plan.locations if plan else ())]
    points.append(_as_latlon(route.coordinates[-1]))

    return {
        "distance": route.distance,
        "duration": route.duration,
        "nodes": [list(c) for c in route.coordinates],
        "peages": [p.as_dict() for p in journey.passages],
        "cost": journey.cost,
        "booths": sorted(booths),
        # The unrefined Google Maps link.
        "google_url": google_maps_link(points),
        # How faithful the link is, and what could not be priced. Read by the
        # evaluation.
        "waypoints": [list(c) for c in (plan.locations if plan else ())],
        "waypoints_needed": plan.needed if plan else 0,
        "complete": plan.complete if plan else True,
        "unpriced": journey.unpriced,
    }


async def get_route(from_, to):
    """Both routes between two `[longitude, latitude]` points, priced.

    Returns `{"fast": ..., "optimal": ...}`, the shape `api.py` serves and
    `bot.py` formats.
    """
    try:
        routers = Routers()

        start = await routers.snap(from_)
        end = await routers.snap(to)

        fast = await routers.fast(start, end)
        optimal = await routers.optimal(start, end)

        plan = await plan_waypoints(
            routers, optimal, start, end, max_waypoints=MAX_WAYPOINTS
        )

        result = {
            "fast": _describe(fast, None, account(BOOTHS, fast.node_ids),
                              booths_crossed(BOOTHS, fast.node_ids)),
            "optimal": _describe(optimal, plan, account(BOOTHS, optimal.node_ids),
                                 booths_crossed(BOOTHS, optimal.node_ids)),
        }
    except TooFarFromNetwork as e:
        _record_failure(from_, to, "out_of_reach", str(e))
        raise RouteError("out_of_reach", str(e)) from None
    except NoRoute as e:
        message = f"no route between {_as_latlon(from_)} and {_as_latlon(to)}: {e}"
        _record_failure(from_, to, "no_route", message)
        raise RouteError("no_route", message) from None
    except RouterUnavailable as e:
        _record_failure(from_, to, "router_unavailable", str(e))
        raise RouteError("router_unavailable", str(e)) from None

    return _for_delivery(result, from_, to)


async def booths_along(geometry):
    """Which booths a foreign route crosses, or None where that is not known."""
    try:
        return await equivalence.booths_of(Routers(), BOOTHS, geometry)
    except Exception as e:                                          # noqa: BLE001
        logger.warning("could not price a foreign geometry: %r", e)
        return None
