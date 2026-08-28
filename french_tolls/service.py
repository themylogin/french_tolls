# -*- coding=utf-8 -*-
"""Answering one route query: both routes, their tolls, and the links.

`api.py` and `bot.py` call `get_route` and are not changed by this work, so its
signature and the shape of what it returns are fixed. Everything a consumer
already reads keeps its name and its meaning; what this adds, it adds as new
keys.
"""
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
import urllib.parse

from . import osrm
from .data import load_or_exit
from .osrm import NoRoute, RouterUnavailable, Routers, TooFarFromNetwork
from .search import MAX_WAYPOINTS, plan_waypoints
from .tolls import account

logger = logging.getLogger(__name__)

__all__ = ["RouteError", "get_route"]

# Read once, at import. Every request would otherwise re-read 12 MB of YAML, and
# a bad artefact would surface as a failed journey rather than a service that
# would not start.
BOOTHS = load_or_exit()

CACHE_DIR = os.environ.get("CACHE_DIR", "/cache")
MAX_WAYPOINTS_SETTING = int(os.environ.get("MAX_WAYPOINTS", str(MAX_WAYPOINTS)))


class RouteError(Exception):
    """A query that could not be answered, with the cause named.

    `cause` is one of a small set of strings rather than free text, so a caller
    can tell an unreachable location from a router that is down without matching
    on a message. The old failure records held a Python exception repr, which
    names the line that raised rather than the condition.
    """

    def __init__(self, cause: str, message: str):
        self.cause = cause
        super().__init__(message)


def _cache_path(from_, to) -> str | None:
    if not CACHE_DIR:
        return None

    # The fingerprint is a directory rather than part of the file name so that a
    # superseded generation can be dropped with one `rm -r`.
    key = f"{from_[0]},{from_[1]};{to[0]},{to[1]}"
    # A coordinate pair is short, but not bounded: hashing keeps the file name
    # legal whatever precision a caller sends.
    name = hashlib.sha256(key.encode()).hexdigest()[:32]
    return os.path.join(CACHE_DIR, BOOTHS.fingerprint, f"{name}.json")


def _read_cache(path):
    if path is None:
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        # A missing file is the ordinary case; a truncated one is a crash during
        # a write, and recomputing is the right answer to both.
        return None


def _write_cache(path, result):
    if path is None:
        return

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Written under a unique temporary name and moved into place, so a reader
        # never sees a half-written file. `os.replace` overwrites; the `os.rename`
        # this replaces was wrapped in an `except FileExistsError` that POSIX
        # never raises, so that branch had never once run.
        tmp = f"{path}.{os.getpid()}.tmp"
        with open(tmp, "w") as f:
            json.dump(result, f)
        os.replace(tmp, path)
    except OSError as e:
        # A cache that cannot be written is not a failed journey.
        logger.warning("could not cache %s: %s", path, e)


def _record_failure(from_, to, cause, message):
    if not CACHE_DIR:
        return

    try:
        directory = os.path.join(CACHE_DIR, "errors")
        os.makedirs(directory, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
        with open(os.path.join(directory, f"{stamp}.json"), "w") as f:
            json.dump({
                "from": list(from_),
                "to": list(to),
                "cause": cause,
                "message": message,
                "fingerprint": BOOTHS.fingerprint,
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


def _describe(route: osrm.Route, plan, journey) -> dict:
    """One route, in the shape every consumer already reads."""
    points = [_as_latlon(route.coordinates[0])]
    points += [_as_latlon(c) for c in (plan.locations if plan else ())]
    points.append(_as_latlon(route.coordinates[-1]))

    return {
        # Keys every existing consumer reads. Same names, same meanings.
        "distance": route.distance,
        "duration": route.duration,
        "nodes": [list(c) for c in route.coordinates],
        "peages": [p.as_dict() for p in journey.passages],
        "cost": journey.cost,
        "url": google_maps_link(points),
        "url_from_current_location": google_maps_link(["Current Location"] + points[1:]),
        "url_from_current_location_through_start": google_maps_link(
            ["Current Location"] + points
        ),

        # Added by this work. How faithful the link is, and what could not be
        # priced. A consumer that does not know them is unaffected.
        "waypoints": [list(c) for c in (plan.locations if plan else ())],
        "waypoints_needed": plan.needed if plan else 0,
        "complete": plan.complete if plan else True,
        "divergences": [d.as_dict() for d in (plan.divergences if plan else ())],
        "unpriced": journey.unpriced,
    }


async def get_route(from_, to):
    """Both routes between two `[longitude, latitude]` points, priced.

    Returns `{"fast": ..., "optimal": ...}`, the shape `api.py` serves and
    `bot.py` formats.
    """
    path = _cache_path(from_, to)
    cached = _read_cache(path)
    if cached is not None:
        return cached

    try:
        async with osrm.session() as session:
            routers = Routers(session)

            start = await routers.snap(from_)
            end = await routers.snap(to)

            fast = await routers.fast(start, end)
            optimal = await routers.optimal(start, end)

            plan = await plan_waypoints(
                routers, optimal, start, end, max_waypoints=MAX_WAYPOINTS_SETTING
            )

            result = {
                # The fast route needs no waypoints: it is by definition what a
                # fastest-path router computes from the two endpoints alone.
                "fast": _describe(fast, None, account(BOOTHS, fast.node_ids)),
                "optimal": _describe(optimal, plan, account(BOOTHS, optimal.node_ids)),
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

    logger.info(
        "%s -> %s: fast %.0f km / %.2f EUR, optimal %.0f km / %.2f EUR, "
        "%d waypoints of %d needed, %d requests",
        _as_latlon(from_), _as_latlon(to),
        result["fast"]["distance"] / 1000, result["fast"]["cost"],
        result["optimal"]["distance"] / 1000, result["optimal"]["cost"],
        len(result["optimal"]["waypoints"]), result["optimal"]["waypoints_needed"],
        routers.requests,
    )

    _write_cache(path, result)
    return result
