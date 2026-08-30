# -*- coding=utf-8 -*-
"""Ask Google what it would drive, and spend the waypoint budget correcting it.

The waypoint search verifies each leg against OSRM's graph, which is the contract
it was built to meet. OSRM's graph is not Google's, so no amount of care on our
side reveals that Google prefers a different road between two of our waypoints.
Google will say so if asked, and the stretches where it left our route are
exactly the places another waypoint helps.
"""
from dataclasses import dataclass, field
import json
import logging

import aiohttp
import numpy as np

from . import spending
from .config import config
from .overlap import (
    DEFAULT_CORRIDOR_M, Corridor, decode_polyline, lengths_m, total_length_m,
)

logger = logging.getLogger(__name__)

__all__ = ["GoogleRoute", "MAX_WAYPOINTS", "Refinement", "refine", "request_route_once"]

# What a Google Maps directions URL carries.
MAX_WAYPOINTS = 9

# The routing quality every request asks for.
#
# At `TRAFFIC_UNAWARE` Google returns bizarre routes that leave a motorway at a
# junction and rejoin it shortly after.
ROUTING_PREFERENCE = "TRAFFIC_AWARE_OPTIMAL"

REQUEST_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class GoogleRoute:
    # How much of Google's route ran inside the corridor of ours.
    share: float | None
    # The original waypoints, plus the ones that need to be added.
    waypoints: list = field(default_factory=list)
    # The route geometry Google returned.
    geometry: list = field(default_factory=list)


@dataclass
class Refinement:
    refined: bool = False
    reason: str | None = None
    # The waypoints to put in a link: the refined set, or the original ones.
    waypoints: list = field(default_factory=list)
    # The original waypoints.
    sent_waypoints: list = field(default_factory=list)
    # Added waypoints.
    added: list = field(default_factory=list)
    # Google's route through `waypoints` -- the one the link now carries.
    nodes: list = field(default_factory=list)
    distance: float | None = None
    duration: float | None = None
    overlap: float | None = None
    # What the first request measured: how faithfully Google drove through the
    # *original* waypoints, and how far it strayed.
    before_overlap: float | None = None
    drift_m: float | None = None
    budget: int = 0


def _cumulative(points):
    """Distance along `points`, in metres, one entry per point starting at zero."""
    if len(points) < 2:
        return [0.0]
    return [0.0] + list(np.cumsum(lengths_m(points)))


def _positions(ours, points):
    """Where along `ours`, in metres, each of `points` lies.
    """
    along = _cumulative(ours)
    route = Corridor(ours)
    return [along[route.nearest_index(p)] for p in points]


def drift_sections(theirs, ours, corridor_m=DEFAULT_CORRIDOR_M):
    """The stretches of Google's route lying outside the corridor of ours."""
    if len(theirs) < 2 or len(ours) < 2:
        return []

    points = np.asarray(theirs, dtype=float)
    lengths = lengths_m(points)
    real = np.flatnonzero(lengths > 0.0)
    if len(real) == 0:
        return []

    midpoints = ((points[:-1] + points[1:]) / 2.0)[real]
    inside = Corridor(ours, corridor_m).within(midpoints)

    sections = []
    current = None
    for i, is_inside in zip(real, inside):
        if not is_inside:
            a, b = theirs[i], theirs[i + 1]
            if current is None:
                current = {"from": a, "to": b, "length": 0.0}
            current["length"] += float(lengths[i])
            current["to"] = b
        elif current is not None:
            sections.append(current)
            current = None

    if current is not None:
        sections.append(current)

    return sections


def _rank(length, start, total):
    """A stretch's length, discounted by how far into the route it begins.

    We care more about correcting the beginning of the route than the end.
    The plans might change, the end might never be reached, or the route
    might be re-routed midway to get some gas or have dinner.
    """
    return length * (1.0 - (start / total) / 2 if total else 1.0)


def waypoints_for(sections, ours, budget):
    """A waypoint on our route for each of the worst stretches.
    """
    if budget <= 0 or not sections:
        return []

    along = _cumulative(ours)
    total = along[-1]

    ends = _positions(ours, [s[end] for s in sections for end in ("from", "to")])

    ranked = []
    for section, start, end in zip(sections, ends[0::2], ends[1::2]):
        if end < start:
            start, end = end, start
        ranked.append((_rank(section["length"], start, total), start, end, section))

    out = []
    for _r, start, end, section in sorted(ranked, key=lambda r: -r[0])[:budget]:
        middle = (start + end) / 2
        i = min(range(len(along)), key=lambda k: abs(along[k] - middle))
        out.append({
            "latlon": list(ours[i]),
            "at_m": along[i],
            "skipped_m": end - start,
            "google_detour_m": section["length"],
        })

    return out


def _request_body(from_, to, waypoints):
    """The Routes API request, with every choice stated rather than defaulted.
    """
    def point(lon, lat):
        return {"location": {"latLng": {"latitude": lat, "longitude": lon}}}

    return {
        "origin": point(from_[0], from_[1]),
        "destination": point(to[0], to[1]),
        # Stopovers, which is what a point with no `via` is. A Google Maps
        # directions URL cannot express a pass-through waypoint, so a request
        # that used one would measure a route the link cannot produce.
        "intermediates": [point(lon, lat) for lon, lat in waypoints],
        "travelMode": "DRIVE",
        "routingPreference": ROUTING_PREFERENCE,
        "polylineQuality": "HIGH_QUALITY",
        "polylineEncoding": "ENCODED_POLYLINE",
        "computeAlternativeRoutes": False,
        "optimizeWaypointOrder": False,
        "routeModifiers": {
            "avoidTolls": False,
            "avoidHighways": False,
            "avoidFerries": False,
        },
        "units": "METRIC",
        "languageCode": "en",
        "regionCode": "FR",
    }


FIELD_MASK = "routes.polyline.encodedPolyline,routes.distanceMeters,routes.duration"


async def _ask_google(session, body):
    async with session.post(
        config.google_routes_endpoint,
        data=json.dumps(body),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": config.google_api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S),
    ) as response:
        text = await response.text()
        if response.status != 200:
            raise RuntimeError(f"Google answered HTTP {response.status}: {text[:300]}")
        return json.loads(text)


def _duration_s(route):
    raw = route.get("duration")
    if isinstance(raw, str) and raw.endswith("s"):
        return float(raw[:-1])
    return float(raw) if isinstance(raw, (int, float)) else None


async def _request_route(from_, to, waypoints):
    """One paid Google request. Returns the route, or None."""
    body = _request_body(from_, to, waypoints)
    try:
        async with aiohttp.ClientSession() as session:
            answer = await _ask_google(session, body)
    except Exception as e:                                          # noqa: BLE001
        logger.warning("google request failed for %s -> %s: %s", from_, to, e)
        return None

    routes = answer.get("routes") or []
    return routes[0] if routes else None


def _geometry(route):
    encoded = (route.get("polyline") or {}).get("encodedPolyline")
    return decode_polyline(encoded) if encoded else []


def _measure(theirs, ours):
    """How faithfully `theirs` followed `ours`, and how far it strayed."""
    sections = drift_sections(theirs, ours)
    drift = sum(s["length"] for s in sections)
    length = total_length_m(theirs)
    return sections, drift, (1.0 - drift / length if length else None)


async def request_route_once(from_, to, ours, waypoints):
    """One Google request through `waypoints`. Returns a `GoogleRoute`, or None.
    """
    if not config.google_api_key or config.google_max_requests_per_month <= 0:
        return None
    if not await spending.reserve_google_request(config.google_max_requests_per_month):
        return None

    route = await _request_route(from_, to, waypoints)
    if route is None:
        return None

    theirs = _geometry(route)
    sections, _drift, share = _measure(theirs, ours)
    geometry = [[lon, lat] for lat, lon in theirs]

    budget = MAX_WAYPOINTS - len(waypoints)
    added = waypoints_for(sections, ours, budget) if budget > 0 else []
    if not added:
        return GoogleRoute(share=share, waypoints=list(waypoints), geometry=geometry)

    # In the order our route reaches them: Google is asked to visit them in
    # order, and a list in another order describes a different journey.
    positions = list(zip(_positions(ours, [(lat, lon) for lon, lat in waypoints]),
                         ([lon, lat] for lon, lat in waypoints)))
    positions += [(w["at_m"], [w["latlon"][1], w["latlon"][0]]) for w in added]
    positions.sort(key=lambda p: p[0])
    return GoogleRoute(share=share, waypoints=[p[1] for p in positions], geometry=geometry)


async def refine(from_, to, optimal):
    """Refine a journey's waypoints, or say why it was not refined.

    This is for debug purposes only.
    """
    original = [list(w) for w in optimal["waypoints"]]
    ours = [(lat, lon) for lon, lat in optimal["nodes"]]

    result = await _first_pass(from_, to, ours, original)

    if not result.nodes and (
            result.refined or result.reason == "the link is already full at nine waypoints"):
        result = await _second_pass(from_, to, ours, result)

    return result


async def _first_pass(from_, to, ours, original):
    """Ask Google to route through our waypoints, and add more where they help.
    """
    budget = MAX_WAYPOINTS - len(original)

    if not config.google_api_key or config.google_max_requests_per_month <= 0:
        return Refinement(reason="no Google key or monthly ceiling is configured",
                          waypoints=original, sent_waypoints=original, budget=budget)

    if budget <= 0:
        return Refinement(reason="the link is already full at nine waypoints", waypoints=original,
                          sent_waypoints=original, budget=0)

    if not await spending.reserve_google_request(config.google_max_requests_per_month):
        return Refinement(reason="this month's Google request budget is spent", waypoints=original,
                          sent_waypoints=original, budget=budget)

    route = await _request_route(from_, to, original)
    if route is None:
        return Refinement(reason="the Google request failed", waypoints=original,
                          sent_waypoints=original, budget=budget)

    theirs = _geometry(route)
    sections, drift, share = _measure(theirs, ours)
    added = waypoints_for(sections, ours, budget)

    if not added:
        # No refinement needed: Google already follows our route.
        return Refinement(
            refined=False, reason="Google already followed the route",
            waypoints=original, sent_waypoints=original, added=[],
            nodes=[[lon, lat] for lat, lon in theirs],
            distance=route.get("distanceMeters"), duration=_duration_s(route),
            overlap=share, before_overlap=share, drift_m=drift, budget=budget)

    # Merge our waypoints with the added ones.
    positions = list(zip(_positions(ours, [(lat, lon) for lon, lat in original]),
                         ([lon, lat] for lon, lat in original)))
    positions += [(w["at_m"], [w["latlon"][1], w["latlon"][0]]) for w in added]
    positions.sort(key=lambda p: p[0])

    # `nodes` is left empty on purpose, so that `_second_pass` re-requests the
    # route through the new waypoint set.
    return Refinement(
        refined=True, reason=None,
        waypoints=[p[1] for p in positions], sent_waypoints=original,
        added=[[w["latlon"][1], w["latlon"][0]] for w in added],
        nodes=[], distance=None, duration=None, overlap=None,
        before_overlap=share, drift_m=drift, budget=budget)


async def _second_pass(from_, to, ours, result):
    """Re-request the refined route through the new waypoint set.
    """
    if not config.google_api_key or not await spending.reserve_google_request(
            config.google_max_requests_per_month):
        # The waypoints stand; only the picture is unavailable.
        result.reason = result.reason or "this month's Google request budget is spent"
        return result

    route = await _request_route(from_, to, result.waypoints)
    if route is None:
        result.reason = result.reason or "the Google request failed"
        return result

    theirs = _geometry(route)
    _sections, drift, share = _measure(theirs, ours)

    result.nodes = [[lon, lat] for lat, lon in theirs]
    result.distance = route.get("distanceMeters")
    result.duration = _duration_s(route)
    result.overlap = share

    if result.before_overlap is None:
        result.before_overlap = share
    if result.drift_m is None:
        result.drift_m = drift

    return result

