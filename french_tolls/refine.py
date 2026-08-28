# -*- coding=utf-8 -*-
"""Ask Google what it would drive, and spend the waypoint budget correcting it.

The waypoint search verifies each leg against OSRM's graph, which is the honest
contract it was built to. OSRM's graph is not Google's, so no amount of care on
our side reveals that Google prefers a different road between two of our
waypoints. Google will say so if asked, and the stretches where it left our
route are exactly the places another waypoint helps.

Measured on Bayeux to Apt before this existed: Google covered in 1 009 km what
our route does in 959 km, spending 134 km on a single detour our route skips in
86, for a faithfulness of 74.4%.

Asking costs money. It is asked at most once per journey, and never more often
in a month than the operator allows.
"""
from dataclasses import dataclass, field
import json
import logging
import math
import os
import urllib.parse

import aiohttp

from . import db
from .geometry import DEFAULT_CORRIDOR_M, SegmentIndex, decode_polyline, encode_polyline

logger = logging.getLogger(__name__)

__all__ = ["MAX_WAYPOINTS", "Refinement", "refine"]

ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

API_KEY = os.environ.get("GOOGLE_DIRECTIONS_API_KEY", "").strip()
MONTHLY_CEILING = int(os.environ.get("GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH", "0") or 0)

# What a Google Maps directions URL carries.
MAX_WAYPOINTS = 9

CORRIDOR_M = float(os.environ.get("REFINE_CORRIDOR_M", DEFAULT_CORRIDOR_M))

REQUEST_TIMEOUT_S = float(os.environ.get("GOOGLE_TIMEOUT_S", "30"))

EARTH_RADIUS_M = 6371000.0

# Why a journey was not refined. Reported rather than swallowed: a route Google
# agreed with and a route nobody could afford to ask about look the same from
# outside, and they are not the same thing.
AGREED = "google already followed the route"
NO_WAYPOINT_BUDGET = "the link is already full at nine waypoints"
NO_REQUEST_BUDGET = "this month's Google request budget is spent"
NOT_CONFIGURED = "no Google key or monthly ceiling is configured"
FAILED = "the Google request failed"


@dataclass
class Refinement:
    """What Google said, and what was done about it."""

    refined: bool = False
    reason: str | None = None
    # The waypoints to put in a link: the refined set, or the original ones.
    waypoints: list = field(default_factory=list)
    # The waypoints the stored route was actually driven through. Distinct from
    # `waypoints`, and the distinction matters: one Google request per journey
    # buys the route through the waypoints we *had*, and the refined set is what
    # we worked out from it. Drawing the refined markers on that route puts them
    # where Google demonstrably did not go -- which is where they were put on
    # purpose, and looks like a bug.
    sent_waypoints: list = field(default_factory=list)
    added: list = field(default_factory=list)
    # Google's route through `waypoints` -- the one the link now carries. Always
    # the route that matches the markers a viewer sees, so a correct refinement
    # can never look like a fault. Empty until someone asks to see it.
    nodes: list = field(default_factory=list)
    distance: float | None = None
    duration: float | None = None
    overlap: float | None = None
    # What the first request measured: how faithfully Google drove the *original*
    # waypoints, and how far it strayed. This is why the refinement happened, and
    # it is kept even though the route it describes is not drawn.
    before_overlap: float | None = None
    drift_m: float | None = None
    budget: int = 0

    def as_dict(self):
        return {
            "refined": self.refined,
            "reason": self.reason,
            "waypoints": self.waypoints,
            "sent_waypoints": self.sent_waypoints,
            "added": self.added,
            "nodes": self.nodes,
            "distance": self.distance,
            "duration": self.duration,
            "overlap": self.overlap,
            "before_overlap": self.before_overlap,
            "drift": self.drift_m,
            "budget": self.budget,
        }

    def stored(self):
        """The row form: the geometry encoded, because it is 50 000 points."""
        d = self.as_dict()
        d["nodes"] = encode_polyline([(lat, lon) for lon, lat in self.nodes])
        return d


def _metres(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def _cumulative(points):
    out = [0.0]
    for a, b in zip(points, points[1:]):
        out.append(out[-1] + _metres(a, b))
    return out


def _nearest_index(points, target):
    best_i, best_d = 0, None
    for i, p in enumerate(points):
        d = _metres(p, target)
        if best_d is None or d < best_d:
            best_i, best_d = i, d
    return best_i


def drift_sections(theirs, ours, corridor_m=CORRIDOR_M):
    """The stretches of Google's route lying outside the corridor of ours."""
    index = SegmentIndex(ours)

    sections = []
    current = None
    for a, b in zip(theirs, theirs[1:]):
        length = _metres(a, b)
        if length == 0.0:
            continue
        midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if not index.within(midpoint, corridor_m):
            if current is None:
                current = {"from": a, "to": b, "length": 0.0}
            current["length"] += length
            current["to"] = b
        elif current is not None:
            sections.append(current)
            current = None

    if current is not None:
        sections.append(current)

    return sections


def waypoints_for(sections, ours, budget):
    """A waypoint on our route for each of the worst stretches.

    The stretch is located on our route by its two ends -- where Google left and
    where it rejoined -- and the waypoint is our route's own midpoint between
    them.

    On **our** route, never on Google's. Google drifting means it found a road it
    liked better between two of our waypoints; naming a point on that road would
    confirm the detour rather than correct it.
    """
    if budget <= 0 or not sections:
        return []

    along = _cumulative(ours)

    out = []
    for section in sorted(sections, key=lambda s: -s["length"])[:budget]:
        start = along[_nearest_index(ours, section["from"])]
        end = along[_nearest_index(ours, section["to"])]
        if end < start:
            start, end = end, start

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

    `TRAFFIC_UNAWARE` is what makes Google's answer comparable to the route it is
    being compared against: it is Google's own name for routing as though the
    road were empty, which is what OSRM computes from its profile's speeds.

    No departureTime -- supplying one enables traffic, which would make
    TRAFFIC_UNAWARE a contradiction. Tolls are emphatically not avoided: a route
    that uses toll roads is the entire subject. Waypoint order is not optimised,
    because reordering would answer a question about a journey nobody asked for.
    """
    def point(lon, lat):
        return {"location": {"latLng": {"latitude": lat, "longitude": lon}}}

    return {
        "origin": point(from_[0], from_[1]),
        "destination": point(to[0], to[1]),
        "intermediates": [point(lon, lat) for lon, lat in waypoints],
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",
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


# Only what is used. The evaluation asks for every field because it buys an
# answer once against questions not yet asked; this asks a question it already
# knows.
FIELD_MASK = "routes.polyline.encodedPolyline,routes.distanceMeters,routes.duration"


async def _ask_google(session, body):
    async with session.post(
        ROUTES_ENDPOINT,
        data=json.dumps(body),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
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


def _from_stored(stored, original):
    """A refinement read back from the store."""
    encoded = stored.get("nodes") or ""
    return Refinement(
        refined=stored.get("refined", False),
        reason=stored.get("reason"),
        waypoints=stored.get("waypoints") or original,
        sent_waypoints=stored.get("sent_waypoints") or original,
        added=stored.get("added") or [],
        nodes=[[lon, lat] for lat, lon in decode_polyline(encoded)] if encoded else [],
        distance=stored.get("distance"),
        duration=stored.get("duration"),
        overlap=stored.get("overlap"),
        before_overlap=stored.get("before_overlap"),
        drift_m=stored.get("drift"),
        budget=stored.get("budget", 0),
    )


async def _ask(from_, to, waypoints):
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
    length = sum(_metres(a, b) for a, b in zip(theirs, theirs[1:]))
    return sections, drift, (1.0 - drift / length if length else None)


async def refine(fingerprint, from_, to, optimal, *, with_geometry=False):
    """Refine a journey's waypoints, or say why it was not refined.

    Two phases, because the two things a caller can want cost differently.

    Following a link needs only the refined waypoints, and those come from one
    request: Google's route through the waypoints we already had, read for the
    stretches where it went its own way.

    Seeing the result needs a second, because the route through the refined
    waypoints does not exist until it is asked for. The first request cannot
    answer it — its whole purpose is to find the places that route will differ.

    So `with_geometry` is what the page's button passes and a redirect does not.
    Both phases are stored, so a journey costs at most two requests ever, and a
    link followed after the button costs nothing.
    """
    original = [list(w) for w in optimal["waypoints"]]
    ours = [(lat, lon) for lon, lat in optimal["nodes"]]

    stored = db.read_refinement(fingerprint, from_, to)
    result = _from_stored(stored, original) if stored else None

    if result is None:
        result = await _first_pass(fingerprint, from_, to, ours, original)

    # The drawable route, bought only when someone asks to look at it.
    if with_geometry and result.refined and not result.nodes:
        result = await _second_pass(fingerprint, from_, to, ours, result)

    return result


async def _first_pass(fingerprint, from_, to, ours, original):
    """Ask what Google drives through the waypoints we have, and correct them."""
    budget = MAX_WAYPOINTS - len(original)

    if not API_KEY or MONTHLY_CEILING <= 0:
        return Refinement(reason=NOT_CONFIGURED, waypoints=original,
                          sent_waypoints=original, budget=budget)

    if budget <= 0:
        return Refinement(reason=NO_WAYPOINT_BUDGET, waypoints=original,
                          sent_waypoints=original, budget=0)

    if not db.reserve_google_request(MONTHLY_CEILING):
        return Refinement(reason=NO_REQUEST_BUDGET, waypoints=original,
                          sent_waypoints=original, budget=budget)

    route = await _ask(from_, to, original)
    if route is None:
        return Refinement(reason=FAILED, waypoints=original,
                          sent_waypoints=original, budget=budget)

    theirs = _geometry(route)
    sections, drift, share = _measure(theirs, ours)
    added = waypoints_for(sections, ours, budget)

    if not added:
        # Google already drove our route, so the route it drove *is* the route
        # the link produces. Nothing more to buy: the geometry is already here.
        return _store(fingerprint, from_, to, Refinement(
            refined=False, reason=AGREED,
            waypoints=original, sent_waypoints=original, added=[],
            nodes=[[lon, lat] for lat, lon in theirs],
            distance=route.get("distanceMeters"), duration=_duration_s(route),
            overlap=share, before_overlap=share, drift_m=drift, budget=budget))

    # Merged in the order our route reaches them: Google is asked to visit them
    # in order, and a list in another order describes a different journey.
    along = _cumulative(ours)
    positions = [(along[_nearest_index(ours, (lat, lon))], [lon, lat])
                 for lon, lat in original]
    positions += [(w["at_m"], [w["latlon"][1], w["latlon"][0]]) for w in added]
    positions.sort(key=lambda p: p[0])

    # `nodes` is left empty on purpose. The route through these new waypoints is
    # not the route just measured, and drawing that one would put the added
    # points visibly off the line they were computed to correct.
    return _store(fingerprint, from_, to, Refinement(
        refined=True, reason=None,
        waypoints=[p[1] for p in positions], sent_waypoints=original,
        added=[[w["latlon"][1], w["latlon"][0]] for w in added],
        nodes=[], distance=None, duration=None, overlap=None,
        before_overlap=share, drift_m=drift, budget=budget))


async def _second_pass(fingerprint, from_, to, ours, result):
    """Buy the route through the refined waypoints, so it can be drawn."""
    if not API_KEY or not db.reserve_google_request(MONTHLY_CEILING):
        # The waypoints stand; only the picture is unavailable.
        result.reason = result.reason or NO_REQUEST_BUDGET
        return result

    route = await _ask(from_, to, result.waypoints)
    if route is None:
        result.reason = result.reason or FAILED
        return result

    theirs = _geometry(route)
    _sections, drift, share = _measure(theirs, ours)

    result.nodes = [[lon, lat] for lat, lon in theirs]
    result.distance = route.get("distanceMeters")
    result.duration = _duration_s(route)
    result.overlap = share
    return _store(fingerprint, from_, to, result)


def _store(fingerprint, from_, to, result):
    db.write_refinement(fingerprint, from_, to, result.stored())
    return result
