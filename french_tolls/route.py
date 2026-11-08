# -*- coding=utf-8 -*-
import contextlib
from dataclasses import dataclass
from datetime import datetime, timezone
import itertools
import json
import logging
import os
import urllib.parse

from . import equivalence, osrm, splits
from .config import config
from .booths import load
from .osrm import NoRoute, RouterUnavailable, Routers, Snap, TooFarFromNetwork
from .waypoints import MAX_WAYPOINTS, plan_waypoints
from .tolls import Journey, account, booths_crossed, closed_sections, fare

logger = logging.getLogger(__name__)

__all__ = ["PlannedRoute", "RouteError", "SplitStop", "get_route", "link_through", "planned_route",
           "stretch_through", "toll_cost"]

ERRORS_DIR = "/cache/errors"

BOOTHS = load()
ADVICE = splits.load()


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


def _ticket_price(entrance_node: int, exit_node: int):
    """What the operator charges for one sold ticket, or None if it sells none."""
    entrance = BOOTHS.at(entrance_node)
    exit_booth = BOOTHS.at(exit_node)
    if entrance is None or exit_booth is None or exit_booth.gare is None:
        return None
    price = fare(BOOTHS, entrance, exit_booth)
    return None if price is None else float(price)


def _split_fare(entrance, exit_booth, candidate):
    """What a candidate's tickets cost in total, or None if one is not sold."""
    legs, previous = [], entrance.node_id
    for stop in candidate.stops:
        legs.append((previous, stop.exit_node))
        previous = stop.enter_node
    legs.append((previous, exit_booth.node_id))

    total = 0.0
    for a, b in legs:
        price = _ticket_price(a, b)
        if price is None:
            return None
        total += price
    return round(total, 2)


def _plan_split(optimal):
    """The stops worth making on this route, and what they save."""
    limit = splits.threshold()
    stops, saved, extra = [], 0.0, 0
    for entrance, exit_booth in closed_sections(BOOTHS, optimal.node_ids):
        if entrance.gare is None or exit_booth.gare is None:
            continue
        direct = fare(BOOTHS, entrance, exit_booth)
        if direct is None:
            continue
        chosen = ADVICE.best(
            entrance.gare, exit_booth.gare, float(direct),
            lambda c, e=entrance, x=exit_booth: _split_fare(e, x, c),
            limit,
        )
        if chosen is None:
            continue
        candidate, saving = chosen
        stops.append((entrance, exit_booth, candidate))
        saved += saving
        extra += candidate.extra_time
    return stops, round(saved, 2), extra


def _split_google_url(route, optimal, plan, stops):
    """A Maps link that drives the split journey, or None if it will not fit."""
    placed = []

    for index, location in zip(plan.indices if plan else (),
                               plan.locations if plan else ()):
        # The waypoint is a position on the *optimal* route; the split route is
        # a different sequence, so it is found again by the node it stands on.
        node_id = optimal.node_ids[index]
        at = route.index_of(node_id)
        if at is not None:
            placed.append((at, location))

    for _entrance, _exit, candidate in stops:
        for stop in candidate.stops:
            booth = BOOTHS.at(stop.exit_node)
            at = route.index_of(booth.node_id)
            if at is None:
                return None
            placed.append((at, (booth.latlon[1], booth.latlon[0])))

    if len(placed) > MAX_WAYPOINTS:
        return None

    placed.sort(key=lambda p: p[0])
    points = [_as_latlon(route.coordinates[0])]
    points += [_as_latlon(location) for _at, location in placed]
    points.append(_as_latlon(route.coordinates[-1]))
    return google_maps_link(points)


@dataclass(frozen=True)
class _Split:
    route: osrm.Route
    stops: list
    journey: Journey
    saving: float
    extra_time: int


async def _split_journey(routers, start, end, optimal):
    stops, expected_saving, extra = _plan_split(optimal)
    if not stops:
        return None

    vias = []
    wanted = []
    for _entrance, _exit, candidate in stops:
        for stop in candidate.stops:
            for node_id in (stop.exit_node, stop.enter_node):
                booth = BOOTHS.at(node_id)
                if booth is None:
                    return None
                wanted.append(booth.node_id)

            booth = BOOTHS.at(stop.exit_node)
            vias.append((booth.latlon[1], booth.latlon[0]))

    route = await routers.route_via(config.osrm_optimal_url, start, vias, end)

    crossed = booths_crossed(BOOTHS, route.node_ids)
    missed = [n for n in wanted if n not in crossed]
    if missed:
        # The re-route did not go through the junctions the saving was computed
        # for, so it is not that journey and must not be offered as it.
        logger.info("the split route missed %d of its stops; not offering it",
                    len(missed))
        return None

    journey = account(BOOTHS, route.node_ids)
    saving = round(optimal_cost(optimal) - journey.cost, 2)
    if saving <= 0:
        logger.info("the split route priced no cheaper than the optimal one"
                    " (expected %.2f); not offering it", expected_saving)
        return None

    return _Split(route=route, stops=stops, journey=journey, saving=saving, extra_time=extra)


async def _super_optimal(routers, start, end, optimal, plan):
    """The optimal route, re-driven through the stops that make it cheaper."""
    try:
        split = await _split_journey(routers, start, end, optimal)
    except (NoRoute, RouterUnavailable) as e:
        logger.info("could not route the split journey: %r", e)
        return None
    if split is None:
        return None

    route = split.route
    stops = [
        _stop_entry(route, [BOOTHS.at(stop.exit_node).node_id, BOOTHS.at(stop.enter_node).node_id])
        for _e, _x, candidate in split.stops for stop in candidate.stops
    ]
    described = _describe_split(route, optimal, plan, split.journey, stops)
    # `_describe` builds a link from the plan it was handed, which is the
    # optimal route's and says nothing about the stops. Replace it with one that
    # drives this journey, or with None where the waypoints do not fit.
    described["google_url"] = _split_google_url(route, optimal, plan, split.stops)
    described["extra_duration"] = split.extra_time
    described["saving"] = split.saving
    return described


def _stop_entry(route, booths):
    """A stop as the answer carries it, or None where `route` crosses none of `booths`.

    `booths` are the ids of the stop's exit booth and entrance booth. The route
    reaches the exit booth first. It may cross an alias lane of a booth rather
    than the booth's own node, so the booth is found by what each node belongs to.
    """
    for index, node_id in enumerate(route.node_ids):
        booth = BOOTHS.at(node_id)
        if booth is not None and booth.node_id in booths:
            return {
                "name": booth.label,
                "latlon": list(booth.latlon),
                "booths": [booth.node_id, *sorted(set(booths) - {booth.node_id})],
                "index": index,
            }
    return None


def _describe_split(route, optimal, plan, journey, stops):
    """A route through `stops`, with the waypoints that drive it when every stop is kept."""
    described = _describe(route, plan, journey, booths_crossed(BOOTHS, route.node_ids))
    described["stops"] = stops

    fixed = [(stop["index"], (stop["latlon"][1], stop["latlon"][0])) for stop in stops]
    placed = _fit_waypoints(route, optimal, plan, fixed)
    described["drive_waypoints"] = None
    if placed is not None:
        described["drive_waypoints"] = [list(location) for _at, location in placed]
    return described


def optimal_cost(optimal) -> float:
    return account(BOOTHS, optimal.node_ids).cost


def toll_cost(route: osrm.Route) -> float:
    return account(BOOTHS, route.node_ids).cost


@contextlib.contextmanager
def _named_failures(from_, to):
    try:
        yield
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


async def get_route(from_, to):
    """Both routes between two `[longitude, latitude]` points, priced.

    Returns `{"fast": ..., "optimal": ...}`, the shape `api.py` serves and
    `bot.py` formats.
    """
    with _named_failures(from_, to):
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

        split = await _super_optimal(routers, start, end, optimal, plan)
        if split is not None:
            result["super_optimal"] = split

    return _for_delivery(result, from_, to)


async def stretch_through(from_, to, stops):
    """The fast route, and the route through `stops`, between two `[longitude, latitude]` points.

    Each stop is a `(location, booths)` pair: the `(longitude, latitude)` of its
    exit booth, and the ids of its exit booth and entrance booth. The route is
    built on the toll-weighted graph through each exit booth, as the split route
    is, so the road between two stops is chosen as it is for `optimal`.

    Returns `{"fast": ..., "super_optimal": ...}` in the shape of `get_route`, or
    None where the route does not cross the booths of every stop.
    """
    with _named_failures(from_, to):
        routers = Routers()

        start = await routers.snap(from_)
        end = await routers.snap(to)

        fast = await routers.fast(start, end)
        optimal = await routers.optimal(start, end)
        plan = await plan_waypoints(routers, optimal, start, end, max_waypoints=MAX_WAYPOINTS)

        vias = [tuple(location) for location, _booths in stops]
        through = await routers.route_via(config.osrm_optimal_url, start, vias, end)

    crossed = booths_crossed(BOOTHS, through.node_ids)
    if any(not set(booths) <= crossed for _location, booths in stops):
        logger.info("the route through %d stop(s) missed one; not offering it", len(stops))
        return None

    result = {
        "fast": _describe(fast, None, account(BOOTHS, fast.node_ids), booths_crossed(BOOTHS, fast.node_ids)),
        "super_optimal": _describe_split(
            through, optimal, plan, account(BOOTHS, through.node_ids),
            [_stop_entry(through, set(booths)) for _location, booths in stops]),
    }
    return _for_delivery(result, from_, to)


@dataclass(frozen=True)
class SplitStop:
    # [longitude, latitude] of the exit booth, as the split route was sent it.
    location: tuple[float, float]
    index: int


@dataclass(frozen=True)
class PlannedRoute:
    start: Snap
    end: Snap
    route: osrm.Route
    stops: tuple[SplitStop, ...]
    optimal: osrm.Route


async def planned_route(routers, from_, to, name) -> PlannedRoute | None:
    """The `optimal` or `super_optimal` route of `get_route`, without the waypoint search.

    None where the journey offers no split route.
    """
    with _named_failures(from_, to):
        start = await routers.snap(from_)
        end = await routers.snap(to)
        optimal = await routers.optimal(start, end)

        if name == "optimal":
            return PlannedRoute(start=start, end=end, route=optimal, stops=(), optimal=optimal)

        try:
            split = await _split_journey(routers, start, end, optimal)
        except NoRoute:
            return None
        if split is None:
            return None

        stops = []
        for _entrance, _exit, candidate in split.stops:
            for stop in candidate.stops:
                booth = BOOTHS.at(stop.exit_node)
                stops.append(SplitStop(location=(booth.latlon[1], booth.latlon[0]),
                                       index=split.route.index_of(booth.node_id)))

        return PlannedRoute(start=start, end=end, route=split.route, stops=tuple(stops), optimal=optimal)


async def booths_along(geometry):
    """Which booths a foreign route crosses, or None where that is not known."""
    try:
        return await equivalence.booths_of(Routers(), BOOTHS, geometry)
    except Exception as e:                                          # noqa: BLE001
        logger.warning("could not price a foreign geometry: %r", e)
        return None


async def link_through(routers, planned, route, kept) -> str | None:
    """A Maps link that drives `route` through each of `kept`, or None where they alone do not fit.

    `kept` are the vias of the route, each with a `location` and the node `index`
    where the route meets it. The waypoints of the optimal route's own link fill
    the free places, as `_fit_waypoints` chooses them.
    """
    if len(kept) > MAX_WAYPOINTS:
        return None

    plan = await plan_waypoints(routers, planned.optimal, planned.start, planned.end, max_waypoints=MAX_WAYPOINTS)
    placed = _fit_waypoints(route, planned.optimal, plan, [(via.index, via.location) for via in kept])
    points = [_as_latlon(route.coordinates[0])]
    points += [_as_latlon(location) for _at, location in placed]
    points.append(_as_latlon(route.coordinates[-1]))
    return google_maps_link(points)


def _fit_waypoints(route, optimal, plan, fixed):
    """`fixed`, and the waypoints of `optimal`'s plan that fit beside them, in `route` order.

    `fixed` are `(index, location)` pairs on `route`. A waypoint of the plan is
    kept where `route` crosses its node. Where they do not all fit, the one
    nearest along the route to another waypoint goes first: a waypoint next to
    another one pins the least. None where `fixed` alone does not fit.
    """
    if len(fixed) > MAX_WAYPOINTS:
        return None

    optional = []
    for index, location in zip(plan.indices, plan.locations):
        at = route.index_of(optimal.node_ids[index])
        if at is not None:
            optional.append((at, location))
    fixed = list(fixed)

    along = [0.0, *itertools.accumulate(route.segment_distance)]
    while len(fixed) + len(optional) > MAX_WAYPOINTS:
        def gap(position):
            at = optional[position][0]
            others = fixed + optional[:position] + optional[position + 1:]
            return min(abs(along[at] - along[other]) for other, _location in others)

        del optional[min(range(len(optional)), key=gap)]

    return sorted(fixed + optional, key=lambda point: point[0])
