# -*- coding=utf-8 -*-
"""Answering one route query: both routes, their tolls, and the links.

`api.py` and `bot.py` call `get_route` and are not changed by this work, so its
signature and the shape of what it returns are fixed. Everything a consumer
already reads keeps its name and its meaning; what this adds, it adds as new
keys.
"""
from datetime import datetime, timezone
import json
import logging
import os
import urllib.parse

from . import db, osrm, refine as refine_module
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

PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "").rstrip("/")
if not PUBLIC_SITE_URL:
    # Beside `load_or_exit` and failing the same way, for the same reason. The
    # three link keys address this service, and a service that does not know its
    # own address cannot produce them. Starting anyway would mean answering with
    # links of another shape, which is a silent change to a contract the bot and
    # the page both read.
    raise SystemExit("french_tolls: cannot start: PUBLIC_SITE_URL is not set")

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


def _go_url(form, from_, to):
    """A link to this service, which refines and then redirects to Google.

    A redirect rather than a Google address built now, because the bot writes a
    link long before anyone follows it: refining at send time would pay for every
    link nobody opens. Following one costs milliseconds for a cached journey and
    about two seconds for one that also asks Google.
    """
    query = urllib.parse.urlencode({
        "from": f"{from_[0]:.6f},{from_[1]:.6f}",
        "to": f"{to[0]:.6f},{to[1]:.6f}",
    })
    return f"{PUBLIC_SITE_URL}/go/{form}?{query}"


def _with_links(answer, from_, to):
    """Add the three links to both routes of an answer, in place.

    Not part of what is cached. The three are a function of the two coordinates
    and this service's address, and the two coordinates *are* the cache key --
    so storing them would put the address into what is keyed on the journey, and
    a service whose address changed would serve links to its old one forever.

    Applied to a cache hit and a computed answer alike, so a caller cannot tell
    the two apart and the two paths cannot drift.
    """
    for route in answer.values():
        route["url"] = _go_url("start", from_, to)
        route["url_from_current_location"] = _go_url("here", from_, to)
        route["url_from_current_location_through_start"] = _go_url(
            "here-via-start", from_, to)

    return answer


def _describe(route: osrm.Route, plan, journey) -> dict:
    """One route, in the shape every consumer already reads."""
    points = [_as_latlon(route.coordinates[0])]
    points += [_as_latlon(c) for c in (plan.locations if plan else ())]
    points.append(_as_latlon(route.coordinates[-1]))

    return {
        # Keys every existing consumer reads. Same names, same meanings. The
        # three link keys are not here: `_with_links` adds them after the cache.
        "distance": route.distance,
        "duration": route.duration,
        "nodes": [list(c) for c in route.coordinates],
        "peages": [p.as_dict() for p in journey.passages],
        "cost": journey.cost,

        # The unrefined Google address, for a consumer that would rather not
        # depend on this service being reachable. Unlike the three, it is built
        # from the route's own geometry rather than from the endpoints, so it is
        # not derivable from the key and is stored with the answer.
        "google_url": google_maps_link(points),

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
    cached = db.read_answer(from_, to)
    if cached is not None:
        return _with_links(cached, from_, to)

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

    db.write_answer(from_, to, result)
    return _with_links(result, from_, to)


def maps_link_with(points_latlon):
    """A Google Maps link from a list of `lat,lon` strings, origin first."""
    return google_maps_link(points_latlon)


async def refined_link(from_, to, form="start", *, with_geometry=False):
    """The answer, its refinement, and the Google link the refinement earns.

    This is what both the API endpoint and the redirect are built on, so the two
    can never disagree about what a journey refines to.
    """
    answer = await get_route(from_, to)
    optimal = answer["optimal"]

    # `with_geometry` is what the page's button passes: it wants a route to
    # draw, and that costs a second request. A redirect needs only the
    # waypoints, so it never buys one.
    refinement = await refine_module.refine(
        from_, to, optimal, with_geometry=with_geometry)

    origin = _as_latlon(optimal["nodes"][0])
    destination = _as_latlon(optimal["nodes"][-1])
    waypoints = [_as_latlon(w) for w in refinement.waypoints]

    if form == "here":
        points = ["Current Location"] + waypoints + [destination]
    elif form == "here-via-start":
        # This form spends one of the nine intermediate slots on the route's own
        # origin, so only eight are left for the rest. The refinement is computed
        # once for all three forms and fills all nine, so the surplus is dropped
        # here rather than the whole set being recomputed for one form.
        #
        # The earliest are kept: a driver follows a link from the start, and a
        # waypoint they would reach only after the link has already misled them
        # is worth nothing.
        points = ["Current Location", origin] + waypoints[:refine_module.MAX_WAYPOINTS - 1] + [destination]
    else:
        points = [origin] + waypoints + [destination]

    return answer, refinement, google_maps_link(points)
