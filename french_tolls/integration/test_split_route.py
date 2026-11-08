# -*- coding=utf-8 -*-
"""The split route, as the route answer carries it for the bot to drive.

Here rather than in the unit suite: `route` loads the booth artefacts at import,
and the stops are real booths. It reaches no router. The routes are built, and
the split search that would find them is replaced by its result.
"""
import asyncio
import urllib.parse

from .. import route, splits
from ..osrm import Route, Snap
from ..tolls import account
from ..waypoints import WaypointPlan

BOOTH_IDS = sorted(route.BOOTHS.booths)[:20]


def position(node_id):
    """`(longitude, latitude)` of a booth, or of a plain node on a line."""
    booth = route.BOOTHS.at(node_id)
    if booth is not None:
        return booth.latlon[1], booth.latlon[0]
    return 2.35 + 0.01 * node_id, 48.86


def built_route(node_ids):
    segments = len(node_ids) - 1
    return Route(
        node_ids=tuple(node_ids),
        coordinates=tuple(position(n) for n in node_ids),
        segment_distance=(1000.0,) * segments,
        segment_duration=(40.0,) * segments,
        distance=1000.0 * segments,
        duration=40.0 * segments,
        weight=40.0 * segments,
    )


def plan_of(optimal, indices):
    return WaypointPlan(indices=list(indices), locations=[optimal.coordinates[i] for i in indices])


def split_route(optimal, stops_after):
    """`optimal` with a stop after each node of `stops_after`, as `{node: (exit, entrance)}`."""
    node_ids = []
    for node_id in optimal.node_ids:
        node_ids.append(node_id)
        if node_id in stops_after:
            exit_id, enter_id = stops_after[node_id]
            node_ids += list(dict.fromkeys([exit_id, enter_id]))
    return built_route(node_ids)


def super_optimal(monkeypatch, optimal, plan, stops_after):
    """What `_super_optimal` answers when the split search finds this split."""
    split = split_route(optimal, stops_after)
    candidate = splits.Candidate(
        stops=tuple(splits.Stop(exit_node=e, enter_node=n) for e, n in stops_after.values()),
        extra_time=120)

    async def found(routers, start, end, optimal_):
        return route._Split(route=split, stops=[(None, None, candidate)],
                            journey=account(route.BOOTHS, split.node_ids), saving=1.0, extra_time=120)

    monkeypatch.setattr(route, "_split_journey", found)
    return split, asyncio.run(route._super_optimal(None, None, None, optimal, plan))


def latlon(lonlat):
    return f"{lonlat[1]:.6f},{lonlat[0]:.6f}"


def link_waypoints(url):
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return query["waypoints"][0].split("|")


def test_the_plain_nodes_are_not_booths():
    assert all(route.BOOTHS.at(n) is None for n in range(1, 41))


def test_the_drive_waypoints_keep_both_stops_where_the_link_is_withheld(monkeypatch):
    optimal = built_route(range(1, 31))
    plan = plan_of(optimal, [2, 5, 8, 11, 14, 17, 22, 26])
    a, b = (BOOTH_IDS[0], BOOTH_IDS[1]), (BOOTH_IDS[2], BOOTH_IDS[3])

    _split, answer = super_optimal(monkeypatch, optimal, plan, {12: a, 20: b})

    assert len(answer["drive_waypoints"]) == 9
    assert list(position(a[0])) in answer["drive_waypoints"]
    assert list(position(b[0])) in answer["drive_waypoints"]
    assert answer["google_url"] is None


def test_the_drive_waypoints_are_the_link_where_everything_fits(monkeypatch):
    optimal = built_route(range(1, 31))
    plan = plan_of(optimal, [4, 9, 16, 24])

    _split, answer = super_optimal(monkeypatch, optimal, plan, {12: (BOOTH_IDS[0], BOOTH_IDS[1])})

    assert len(answer["drive_waypoints"]) == 5
    assert [latlon(w) for w in answer["drive_waypoints"]] == link_waypoints(answer["google_url"])


def test_stops_that_do_not_fit_give_no_drive_waypoints(monkeypatch):
    optimal = built_route(range(1, 31))
    stops_after = {2 * i + 2: (BOOTH_IDS[i], BOOTH_IDS[i]) for i in range(10)}

    _split, answer = super_optimal(monkeypatch, optimal, plan_of(optimal, [5]), stops_after)

    assert answer["drive_waypoints"] is None


def test_a_stop_names_its_booths_and_where_the_route_reaches_it(monkeypatch):
    optimal = built_route(range(1, 31))
    exit_id, enter_id = BOOTH_IDS[0], BOOTH_IDS[1]

    split, answer = super_optimal(monkeypatch, optimal, plan_of(optimal, [5]), {12: (exit_id, enter_id)})

    [stop] = answer["stops"]
    assert stop["booths"] == [exit_id, enter_id]
    assert set(stop["booths"]) <= set(answer["booths"])
    assert split.node_ids[stop["index"]] == exit_id
    assert answer["nodes"][stop["index"]] == list(position(exit_id))


class FakeRouters:
    """Routes along `optimal`, and through a stop when asked for its exit booth."""

    def __init__(self, optimal, detours):
        self.optimal_route = optimal
        # The exit booth's position -> the `(exit, entrance)` the route crosses there.
        self.detours = detours
        self.vias = []

    async def snap(self, location, *, reach_m=None):
        return Snap(location=tuple(location), hint="h", nodes=(1, 2), distance_m=0.0)

    async def fast(self, start, end):
        return self.optimal_route

    async def optimal(self, start, end):
        return self.optimal_route

    async def route_via(self, base, start, vias, end):
        self.vias.append(list(vias))
        return split_route(self.optimal_route, {12: self.detours[vias[0]]})


def stretch(monkeypatch, routers, stops):
    async def plan(routers_, optimal, start, end, *, max_waypoints):
        return plan_of(optimal, [5, 20])

    monkeypatch.setattr(route, "Routers", lambda: routers)
    monkeypatch.setattr(route, "plan_waypoints", plan)
    return asyncio.run(route.stretch_through([2.36, 48.86], [2.65, 48.86], stops))


def test_a_stretch_is_routed_through_its_stop(monkeypatch):
    optimal = built_route(range(1, 31))
    exit_id, enter_id = BOOTH_IDS[0], BOOTH_IDS[1]
    routers = FakeRouters(optimal, {position(exit_id): (exit_id, enter_id)})

    answer = stretch(monkeypatch, routers, [(position(exit_id), frozenset({exit_id, enter_id}))])

    assert routers.vias == [[position(exit_id)]]
    assert list(position(exit_id)) in answer["super_optimal"]["drive_waypoints"]
    assert answer["super_optimal"]["stops"][0]["booths"] == [exit_id, enter_id]


def test_a_stretch_that_misses_the_entrance_booth_is_not_offered(monkeypatch):
    optimal = built_route(range(1, 31))
    exit_id, enter_id = BOOTH_IDS[0], BOOTH_IDS[1]
    routers = FakeRouters(optimal, {position(exit_id): (exit_id, exit_id)})

    answer = stretch(monkeypatch, routers, [(position(exit_id), frozenset({exit_id, enter_id}))])

    assert answer is None
