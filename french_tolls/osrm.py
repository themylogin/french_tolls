# -*- coding=utf-8 -*-
from dataclasses import dataclass
import json
import logging
import os
import urllib.parse

import aiohttp

from .config import config

logger = logging.getLogger(__name__)

__all__ = [
    "BudgetExhausted",
    "Match",
    "NoRoute",
    "Route",
    "RouterUnavailable",
    "Routers",
    "Snap",
    "TooFarFromNetwork",
]

# How far an origin or a destination may be from the road network.
SNAP_REACH_M = 1000.0

# How many routing requests one journey's search may issue.
#
# Hundreds, not two. Answering a journey costs four requests -- snap both ends,
# then the fast route and the optimal one. Everything after that is
# `waypoints.plan_waypoints` solving a different problem: the smallest set of
# waypoints that makes a plain fastest-path router reproduce the toll-optimal
# route. Only the router can say whether a given span reproduces it, so every
# probe is a request.
#
# 1000 is a guard against an infinite loop. The real highest request count in
# our tests across France was 327.
QUERY_BUDGET = 1000

REQUEST_TIMEOUT_S = 30.0


class RouterUnavailable(Exception):
    pass



class NoRoute(Exception):
    """The graph holds no route between the two points."""


class TooFarFromNetwork(Exception):
    """A location is further from the road network than the reach allows."""

    def __init__(self, location, distance_m):
        self.location = location
        self.distance_m = distance_m
        super().__init__(
            f"{location[1]:.6f},{location[0]:.6f} is {distance_m:.0f} m from the "
            f"nearest road, beyond the {SNAP_REACH_M:.0f} m this accepts"
        )


class BudgetExhausted(Exception):
    """The query budget for one journey ran out."""


@dataclass(frozen=True)
class Snap:
    """A query coordinate placed on the road network.
    """

    # [longitude, latitude], as the router returned it.
    location: tuple[float, float]
    # The router's own handle for the exact lane the coordinate landed on.
    # Passing it back pins a later request to that lane rather than to whichever
    # one happens to be nearest, which is what keeps the two graphs' routes
    # starting in the same place. It works because the graphs are the same; only
    # the weights differ.
    hint: str
    # The two nodes of the segment the coordinate landed on.
    nodes: tuple[int, ...]
    distance_m: float


@dataclass(frozen=True)
class Route:
    """One leg of a routing answer.
    """

    node_ids: tuple[int, ...]
    # [longitude, latitude] per node, exactly one point per annotated node.
    coordinates: tuple[tuple[float, float], ...]
    segment_distance: tuple[float, ...]
    segment_duration: tuple[float, ...]
    # The router's own totals for the route. Not a sum of the annotation: the
    # annotation's first and last segments are partial where the endpoints were
    # snapped into the middle of a segment.
    distance: float
    duration: float
    weight: float
    # The router's distance of each leg, in metres: one leg more than the points
    # the route was forced through.
    leg_distance: tuple[float, ...] = ()
    # The node index where each leg begins. Leg `k + 1` begins at the node of
    # via `k`.
    leg_start: tuple[int, ...] = ()

    def __len__(self):
        return len(self.node_ids)

    def index_of(self, node_id: int) -> int | None:
        try:
            return self.node_ids.index(node_id)
        except ValueError:
            return None


@dataclass(frozen=True)
class Match:
    """A foreign geometry placed on the graph, as the nodes it runs over.
    """

    node_ids: tuple[int, ...]
    # How many separate matchings the router needed.
    # More than one means it lost confidence somewhere and started again.
    pieces: int

    @property
    def whole(self) -> bool:
        """True where the router matched the trace in one piece."""
        return self.pieces == 1


class Routers:
    """One instance per journey.
    """

    def __init__(self, budget: int = QUERY_BUDGET):
        self.budget = budget
        self.requests = 0

    @property
    def exhausted(self) -> bool:
        return self.requests >= self.budget

    async def _get(self, base: str, path: str, params: dict) -> dict:
        if self.exhausted:
            raise BudgetExhausted(f"{self.requests} requests issued, budget is {self.budget}")

        self.requests += 1
        url = f"{base}{path}?{urllib.parse.urlencode(params, doseq=True, quote_via=urllib.parse.quote)}"

        headers = {}
        if config.osrm_access_token:
            headers["X-Auth"] = config.osrm_access_token

        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as resp:
                    status = resp.status
                    raw = await resp.read()
        except aiohttp.ClientError as e:
            raise RouterUnavailable(f"{base} did not answer: {e}") from e
        except TimeoutError as e:
            raise RouterUnavailable(
                f"{base} did not answer within {REQUEST_TIMEOUT_S:.0f} s"
            ) from e

        # A proxy on the way to a remote router answers its own errors as HTML.
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if not isinstance(body, dict):
            raise RouterUnavailable(f"{base} answered HTTP {status} without a JSON object")

        code = body.get("code")
        if code == "Ok":
            return body
        if code in ("NoRoute", "NoSegment"):
            raise NoRoute(f"{base} reports {code}: {body.get('message', '')}")

        raise RouterUnavailable(f"{base} answered {code}: {body.get('message', '')}")

    async def snap(self, location, *, reach_m: float = None) -> Snap:
        """Place a coordinate on the road network, on the untouched graph.

        Snapping on one graph and using the result on both is deliberate; see
        `Snap`.
        """
        reach_m = SNAP_REACH_M if reach_m is None else reach_m

        body = await self._get(
            config.osrm_toll_url, f"/nearest/v1/driving/{location[0]},{location[1]}", {"number": 1}
        )
        waypoints = body.get("waypoints") or []
        if not waypoints:
            raise TooFarFromNetwork(location, float("inf"))

        w = waypoints[0]
        if w["distance"] > reach_m:
            raise TooFarFromNetwork(location, w["distance"])

        return Snap(
            location=tuple(w["location"]),
            hint=w["hint"],
            nodes=tuple(w.get("nodes") or ()),
            distance_m=w["distance"],
        )

    async def distance_to_road_network(self, location) -> float:
        """How far a coordinate is from the nearest road, in metres."""
        body = await self._get(
            config.osrm_toll_url, f"/nearest/v1/driving/{location[0]},{location[1]}", {"number": 1}
        )
        waypoints = body.get("waypoints") or []
        return waypoints[0]["distance"] if waypoints else float("inf")

    async def route(self, base: str, start: Snap, end: Snap) -> Route:
        """One route between two snapped points.
        """
        params = {
            "annotations": "nodes,distance,duration",
            "geometries": "geojson",
            "overview": "full",
            "steps": "false",
            "hints": [start.hint, end.hint],
        }
        coords = f"{start.location[0]},{start.location[1]};{end.location[0]},{end.location[1]}"

        body = await self._get(base, f"/route/v1/driving/{coords}", params)

        return _read_route(body)

    async def route_via(self, base: str, start: Snap, vias, end: Snap) -> Route:
        """One route forced through intermediate points, returned as one leg.
        """
        if not vias:
            return await self.route(base, start, end)

        points = [start.location, *vias, end.location]
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in points)
        params = {
            "annotations": "nodes,distance,duration",
            "geometries": "geojson",
            "overview": "full",
            "steps": "false",
        }

        body = await self._get(base, f"/route/v1/driving/{coords}", params)

        return _read_route_legs(body)

    async def match(self, coordinates) -> Match:
        """Place a foreign geometry on the graph, as node ids.
        """
        coords = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in coordinates)
        params = {
            "annotations": "nodes",
            "overview": "false",
            "steps": "false",
            # Because a trace has no timestamps. Left at `split`, the router
            # is free to decide that two consecutive points are too far apart in
            # a time nobody gave it.
            "gaps": "ignore",
            "tidy": "false",
            # Nothing pins a later request to these points, and a hint per
            # tracepoint is most of the response body.
            "generate_hints": "false",
        }
        body = await self._get(config.osrm_toll_url, f"/match/v1/driving/{coords}", params)
        return _read_match(body)

    async def fast(self, start: Snap, end: Snap) -> Route:
        """The fastest route: the untouched graph, which carries no tariff."""
        return await self.route(config.osrm_toll_url, start, end)

    async def optimal(self, start: Snap, end: Snap) -> Route:
        """The cheapest route in money and time: the toll-weighted graph."""
        return await self.route(config.osrm_optimal_url, start, end)


def _read_route(body: dict) -> Route:
    routes = body.get("routes") or []
    if not routes:
        raise NoRoute("the router returned no route")

    route = routes[0]
    legs = route.get("legs") or []
    if len(legs) != 1:
        raise RouterUnavailable(f"expected one leg, got {len(legs)}")

    annotation = legs[0]["annotation"]
    node_ids = tuple(annotation["nodes"])
    coordinates = tuple(tuple(c) for c in route["geometry"]["coordinates"])

    if len(coordinates) != len(node_ids):
        raise RouterUnavailable(
            f"{len(node_ids)} annotated nodes but {len(coordinates)} geometry points"
        )

    distance = tuple(annotation["distance"])
    duration = tuple(annotation["duration"])
    if len(distance) != len(node_ids) - 1:
        raise RouterUnavailable(
            f"{len(node_ids)} nodes but {len(distance)} segments; expected {len(node_ids) - 1}"
        )

    return Route(
        node_ids=node_ids,
        coordinates=coordinates,
        segment_distance=distance,
        segment_duration=duration,
        distance=route["distance"],
        duration=route["duration"],
        weight=route["weight"],
        leg_distance=(legs[0]["distance"],),
        leg_start=(0,),
    )


def _read_route_legs(body: dict) -> Route:
    """A multi-leg route flattened into one, with the seam repetition removed.

    Each leg's node annotation begins with the node the leg starts at, which is
    the node the previous leg ended on. Left in place that node would be crossed
    twice, and the pricing counts a booth once per appearance -- a waypoint put
    on a booth would be charged twice for one passage. The geometry repeats the
    same point, and the two per-segment arrays have one fewer entry than nodes
    *per leg*, so they concatenate without a seam of their own.
    """
    routes = body.get("routes") or []
    if not routes:
        raise NoRoute("the router returned no route")

    route = routes[0]
    legs = route.get("legs") or []
    if not legs:
        raise RouterUnavailable("the router returned a route with no legs")

    node_ids, distance, duration, leg_start = [], [], [], []
    for n, leg in enumerate(legs):
        leg_start.append(len(node_ids))
        annotation = leg["annotation"]
        nodes = list(annotation["nodes"])
        # A waypoint snaps onto a segment, so the leg that ends there and the
        # leg that starts there each name a node for it and the geometry carries
        # the point once. Dropping the *earlier* leg's last node is what keeps
        # the counts equal, and it is the safe end to drop: the node the waypoint
        # snapped to is the next leg's first, and here that node is the booth
        # the journey was routed through. Dropping that would lose the passage
        # the whole split exists to buy.
        if n < len(legs) - 1:
            nodes = nodes[:-1]
        node_ids += nodes
        distance += list(annotation["distance"])
        duration += list(annotation["duration"])

    coordinates = [tuple(c) for c in route["geometry"]["coordinates"]]

    if len(coordinates) != len(node_ids):
        raise RouterUnavailable(
            f"{len(node_ids)} annotated nodes but {len(coordinates)} geometry"
            f" points across {len(legs)} legs"
        )
    if len(distance) != len(node_ids) - 1:
        raise RouterUnavailable(
            f"{len(node_ids)} nodes but {len(distance)} segments across"
            f" {len(legs)} legs; expected {len(node_ids) - 1}"
        )

    return Route(
        node_ids=tuple(node_ids),
        coordinates=tuple(coordinates),
        segment_distance=tuple(distance),
        segment_duration=tuple(duration),
        distance=route["distance"],
        duration=route["duration"],
        weight=route["weight"],
        leg_distance=tuple(leg["distance"] for leg in legs),
        leg_start=tuple(leg_start),
    )


def _read_match(body: dict) -> Match:
    """The node sequence of a matching, with each leg's repeated head dropped.

    A leg's node annotation begins with the node *preceding* the leg's start,
    because a tracepoint snaps partway along a segment and the leg has to name
    the segment it starts in the middle of. 

    Dropping the head leaves one node repeated *in place* at each boundary, so
    we cut that repetition off too.
    """
    matchings = body.get("matchings") or []
    if not matchings:
        raise NoRoute("the router matched no part of the trace")

    node_ids = []
    for matching in matchings:
        for k, leg in enumerate(matching.get("legs") or []):
            nodes = leg["annotation"]["nodes"]
            for node_id in (nodes[1:] if k > 0 else nodes):
                if not node_ids or node_ids[-1] != node_id:
                    node_ids.append(node_id)

    return Match(node_ids=tuple(node_ids), pieces=len(matchings))

