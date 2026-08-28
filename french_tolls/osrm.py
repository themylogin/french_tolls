# -*- coding=utf-8 -*-
"""The two routing graphs, and the route as this application reads one.

`osrm-toll` serves the untouched graph: the road network as OSM describes it,
with no tariff in it. A route from it is the fastest by time, and it is this
application's model of what a general-purpose navigation application computes
when it is given two points and nothing else.

`osrm-optimal` serves the toll-weighted graph: the same network with
`data/segment_weights.csv` applied, so a tolled segment costs what its tariff
costs a driver. A route from it is the cheapest in money and time together.

The two are addressed by Compose service name. The published host ports are for
inspection -- on this host they refuse connections while the Compose network
answers -- so nothing here routes through them.
"""
from dataclasses import dataclass
import logging
import os
import urllib.parse

import aiohttp

logger = logging.getLogger(__name__)

__all__ = [
    "BudgetExhausted",
    "NoRoute",
    "Route",
    "RouterUnavailable",
    "Routers",
    "Snap",
    "TooFarFromNetwork",
]

TOLL_URL = os.environ.get("OSRM_TOLL_URL", "http://osrm-toll:5000")
OPTIMAL_URL = os.environ.get("OSRM_OPTIMAL_URL", "http://osrm-optimal:5000")

# How far an origin or a destination may be from the road network. The bot's
# reply text says a kilometre, so the two have to agree.
SNAP_REACH_M = float(os.environ.get("SNAP_REACH_M", "1000"))

# How many routing requests one journey's search may issue. A request against
# these graphs takes 2-11 ms, so the request count is what a search's cost is
# made of; a wall clock would measure the machine's load instead.
#
# 500 rather than the 200 first planned. Measured across France, the dearest
# journey found -- Strasbourg to Nantes, 11 127 nodes and 8 waypoints -- costs
# 325 requests, and 200 truncated it to 4 of its 8. 500 leaves headroom above the
# worst measured case and still bounds a search at about two seconds.
QUERY_BUDGET = int(os.environ.get("QUERY_BUDGET", "500"))

REQUEST_TIMEOUT_S = float(os.environ.get("OSRM_TIMEOUT_S", "30"))

# How many times a dropped connection is retried before the router is called
# unavailable. Two is enough for a keep-alive the server closed under us; a
# router that is actually down fails all three in milliseconds.
CONNECTION_RETRIES = 2


class RouterUnavailable(Exception):
    """A routing service did not answer, or answered something unusable."""

    def __init__(self, message, code=None):
        # The router's own error code, where it gave one. `route` needs it to
        # tell a rejected hint from a query that is wrong for another reason.
        self.code = code
        super().__init__(message)


# What this OSRM answers when it will not take a hint. Measured on 26.8: a hint
# it cannot decode comes back as `InvalidQuery`, not as the `InvalidHints` the
# documentation suggests. Both are listed so a future version that uses the
# documented code is handled too.
HINT_REJECTED_CODES = ("InvalidHints", "InvalidQuery")


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
    """The query budget for one journey ran out.

    Caught by the search, which returns what it has verified so far. It is never
    allowed to reach a caller: a partial list of verified waypoints is worth more
    to a driver than an error.
    """


@dataclass(frozen=True)
class Snap:
    """A query coordinate placed on the road network.

    `hint` is the router's own handle for the exact lane the coordinate landed
    on. Passing it back pins a later request to that lane rather than to
    whichever one happens to be nearest, which is what keeps the two graphs'
    routes starting in the same place.

    The two graphs are the same graph with different edge weights -- the
    toll-weighted one is a file copy of the untouched one followed by
    `osrm-customize` -- so they share node ids, geometry, and the checksum a
    hint carries. One snap therefore serves both, and snapping separately on
    each would let the two routes start on different lanes.
    """

    # [longitude, latitude], as the router returned it.
    location: tuple[float, float]
    hint: str
    # The two nodes of the segment the coordinate landed on.
    nodes: tuple[int, ...]
    distance_m: float


@dataclass(frozen=True)
class Route:
    """One leg of a routing answer.

    `node_ids` and `coordinates` are parallel and both of length n. The
    per-segment measures are of length n - 1, because n nodes have n - 1
    segments between them.

    Keeping them apart is the point. The annotation reports n node ids and n - 1
    distances, and pairing them element by element -- which is what the
    application this replaces did -- silently discards the last node id of every
    route. A Lyon-Paris route returns 8 642 and 8 641, and a barrier standing on
    that last node was never charged.
    """

    node_ids: tuple[int, ...]
    # [longitude, latitude] per node, from the full-overview GeoJSON geometry,
    # which carries exactly one point per annotated node.
    coordinates: tuple[tuple[float, float], ...]
    segment_distance: tuple[float, ...]
    segment_duration: tuple[float, ...]
    # The router's own totals for the route. Not a sum of the annotation: the
    # annotation's first and last segments are partial where the endpoints were
    # snapped into the middle of a segment.
    distance: float
    duration: float
    weight: float
    # True when a router rejected a hint and the request was retried without it.
    # A rejected hint means the two graphs were not built from one extract.
    hint_rejected: bool = False

    def __len__(self):
        return len(self.node_ids)

    def index_of(self, node_id: int) -> int | None:
        try:
            return self.node_ids.index(node_id)
        except ValueError:
            return None


class Routers:
    """The two graphs, an aiohttp session, and one journey's query budget.

    One instance per journey. The budget is per journey rather than global
    because it bounds a single search, and a counter shared between concurrent
    requests would make one journey's cost depend on another's.
    """

    def __init__(self, session: aiohttp.ClientSession, budget: int = QUERY_BUDGET):
        self._session = session
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

        # A search issues hundreds of requests over one session, and the server
        # closes a pooled connection from time to time. That arrives as a
        # ServerDisconnectedError on the next request over that connection --
        # nothing to do with the query, and answered normally on a fresh one.
        # Retried rather than reported, and not counted again against the budget:
        # the budget bounds the questions asked, not the sockets used to ask them.
        for attempt in range(CONNECTION_RETRIES + 1):
            try:
                async with self._session.get(url) as resp:
                    body = await resp.json(content_type=None)
                break
            except aiohttp.ClientConnectionError as e:
                if attempt == CONNECTION_RETRIES:
                    raise RouterUnavailable(f"{base} did not answer: {e}") from e
                logger.debug("%s dropped the connection; retrying (%d)", base, attempt + 1)
            except aiohttp.ClientError as e:
                raise RouterUnavailable(f"{base} did not answer: {e}") from e
            except TimeoutError as e:
                raise RouterUnavailable(
                    f"{base} did not answer within {REQUEST_TIMEOUT_S:.0f} s"
                ) from e

        code = body.get("code")
        if code == "Ok":
            return body
        if code in ("NoRoute", "NoSegment"):
            raise NoRoute(f"{base} reports {code}: {body.get('message', '')}")

        # A rejected hint is the one error worth a retry rather than a failure,
        # and the caller decides that. Everything else is a bad request or a
        # broken service, and neither improves by being asked again.
        raise RouterUnavailable(f"{base} answered {code}: {body.get('message', '')}", code)

    async def snap(self, location, *, reach_m: float = None) -> Snap:
        """Place a coordinate on the road network, on the untouched graph.

        Snapping on one graph and using the result on both is deliberate; see
        `Snap`. Routing the coordinate to a fixed third point to snap it -- which
        is what the application this replaces did -- fails for a location that
        cannot reach that point, and for the point itself.
        """
        reach_m = SNAP_REACH_M if reach_m is None else reach_m

        body = await self._get(
            TOLL_URL, f"/nearest/v1/driving/{location[0]},{location[1]}", {"number": 1}
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

    async def distance_to_network(self, location) -> float:
        """How far a coordinate is from the nearest road, in metres."""
        body = await self._get(
            TOLL_URL, f"/nearest/v1/driving/{location[0]},{location[1]}", {"number": 1}
        )
        waypoints = body.get("waypoints") or []
        return waypoints[0]["distance"] if waypoints else float("inf")

    async def route(self, base: str, start: Snap, end: Snap) -> Route:
        """One route between two snapped points.

        `geometries=geojson` with `overview=full` returns exactly one coordinate
        per annotated node, so nodes and coordinates pair directly. The
        alternative -- concatenating the per-step polylines -- decodes at
        precision 5, which rounds every coordinate by about a metre, and has to
        drop the last point of each step to splice them.
        """
        params = {
            "annotations": "nodes,distance,duration",
            "geometries": "geojson",
            "overview": "full",
            "steps": "false",
            "hints": [start.hint, end.hint],
        }
        coords = f"{start.location[0]},{start.location[1]};{end.location[0]},{end.location[1]}"

        hint_rejected = False
        try:
            body = await self._get(base, f"/route/v1/driving/{coords}", params)
        except RouterUnavailable as e:
            if e.code not in HINT_REJECTED_CODES:
                raise

            # The router will not take one of the hints -- which is what happens
            # when the two graphs were not built from one extract. Retrying
            # unpinned still gives an answer; it is simply no longer tied to a
            # chosen lane, and the answer says so.
            #
            # The same code also covers a query malformed for a reason of our
            # own, so the original error is re-raised when the unpinned request
            # fails too. Otherwise a bug of ours would read as a hint problem.
            logger.warning("%s refused a hint (%s); retrying unpinned", base, e.code)
            params.pop("hints")
            try:
                body = await self._get(base, f"/route/v1/driving/{coords}", params)
            except RouterUnavailable:
                raise e from None
            hint_rejected = True

        return _read_route(body, hint_rejected)

    async def fast(self, start: Snap, end: Snap) -> Route:
        """The fastest route: the untouched graph, which carries no tariff."""
        return await self.route(TOLL_URL, start, end)

    async def optimal(self, start: Snap, end: Snap) -> Route:
        """The cheapest route in money and time: the toll-weighted graph."""
        return await self.route(OPTIMAL_URL, start, end)


def _read_route(body: dict, hint_rejected: bool) -> Route:
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
        # The full overview carries one point per annotated node. If it ever does
        # not, every position the search computes is off by the difference, and
        # failing here is the only way that does not become a wrong waypoint.
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
        hint_rejected=hint_rejected,
    )


def session() -> aiohttp.ClientSession:
    """The session the routers share for one journey."""
    return aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S))
