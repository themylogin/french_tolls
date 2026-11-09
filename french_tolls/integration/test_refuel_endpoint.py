# -*- coding=utf-8 -*-
"""`route.planned_route` and `POST /api/refuel`.

Here rather than in the unit suite for the reason `test_too_far` gives: `route`
loads the booth artefacts at import, and `api` imports `route`. This suite has
`data/` mounted. It reaches no router.
"""
import asyncio
import json
from types import SimpleNamespace
import urllib.parse

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from .. import api, refuel, route
from ..config import config
from ..osrm import NoRoute, Route, RouterUnavailable, Snap
from ..waypoints import WaypointPlan

FROM = [2.3522, 48.8566]
TO = [5.3698, 43.2965]


def straight_route(node_ids):
    segments = len(node_ids) - 1
    return Route(
        node_ids=tuple(node_ids),
        coordinates=tuple((2.35 + 0.01 * i, 48.86) for i in range(len(node_ids))),
        segment_distance=(1000.0,) * segments,
        segment_duration=(40.0,) * segments,
        distance=1000.0 * segments,
        duration=40.0 * segments,
        weight=40.0 * segments,
    )


class FakeRouters:
    def __init__(self, optimal, *, fast=None, error=None):
        self.optimal_route = optimal
        self.fast_route = fast
        self.error = error
        self.requests = 0

    def _charge(self):
        self.requests += 1
        if self.error is not None:
            raise self.error

    async def snap(self, location, *, reach_m=None):
        self._charge()
        return Snap(location=tuple(location), hint="h", nodes=(1, 2), distance_m=0.0)

    async def optimal(self, start, end):
        self._charge()
        return self.optimal_route

    async def fast(self, start, end):
        self._charge()
        return self.fast_route

    async def route_via(self, base, start, vias, end):
        self._charge()
        return self.optimal_route


@pytest.fixture
def no_waypoint_search(monkeypatch):
    async def refuse(*_args, **_kwargs):
        raise AssertionError("the waypoint search ran")

    monkeypatch.setattr(route, "plan_waypoints", refuse)


def test_the_optimal_route_costs_three_requests(no_waypoint_search):
    optimal = straight_route([1, 2, 3])
    routers = FakeRouters(optimal)

    planned = asyncio.run(route.planned_route(routers, FROM, TO, "optimal"))

    assert planned.route == optimal
    assert planned.stops == ()
    assert routers.requests == 3


def test_the_fast_route_is_planned_on_the_fast_graph(no_waypoint_search):
    fast = straight_route([1, 4, 3])
    routers = FakeRouters(straight_route([1, 2, 3]), fast=fast)

    planned = asyncio.run(route.planned_route(routers, FROM, TO, "fast"))

    assert planned.route == fast
    assert planned.stops == ()
    assert planned.router_url == config.osrm_toll_url


def test_the_optimal_route_is_planned_on_the_optimal_graph(no_waypoint_search):
    planned = asyncio.run(route.planned_route(FakeRouters(straight_route([1, 2, 3])), FROM, TO, "optimal"))

    assert planned.router_url == config.osrm_optimal_url


def test_a_route_without_a_toll_booth_has_no_split_route(no_waypoint_search):
    routers = FakeRouters(straight_route([1, 2, 3]))

    assert asyncio.run(route.planned_route(routers, FROM, TO, "super_optimal")) is None
    assert routers.requests == 3


def test_a_router_failure_names_its_cause():
    routers = FakeRouters(straight_route([1, 2, 3]), error=RouterUnavailable("the router is down"))

    with pytest.raises(route.RouteError) as raised:
        asyncio.run(route.planned_route(routers, FROM, TO, "optimal"))

    assert raised.value.cause == "router_unavailable"


REQUEST = {
    "from": [2.35, 48.86],
    "to": [5.37, 43.30],
    "route": "optimal",
    "car": {"fuel_type": "diesel", "tank_volume": 50, "consume_80": 5.5, "consume_130": 7.2, "reserve_km": 50},
    "fuel": 20,
}
PLANNED = object()
NO_STOP = {"stop_needed": False, "fuel_left": 12.7}


def post(monkeypatch, body, *, planned=PLANNED, route_error=None, plan_error=None, cars=None):
    """POST `body`, with the planner replaced. `cars` collects the car that reaches `plan`."""
    calls = []

    async def fake_planned_route(routers, from_, to, name):
        calls.append(("planned_route", name))
        if route_error is not None:
            raise route_error
        return planned

    async def fake_plan(routers, planned_, parameters, toll_cost, *, fuel=None, range_km=None, chosen=(),
                        link_through=None):
        start = fuel
        if range_km is not None:
            start = f"{range_km} km"
        calls.append(("plan", start, tuple(chosen)))
        if cars is not None:
            cars.append(parameters)
        if plan_error is not None:
            raise plan_error
        return NO_STOP

    monkeypatch.setattr(api, "planned_route", fake_planned_route)
    monkeypatch.setattr(refuel, "plan", fake_plan)

    if isinstance(body, dict):
        body = json.dumps(body)

    async def run():
        app = web.Application()
        app.add_routes([web.post("/api/refuel", api.refuel)])
        async with TestServer(app) as server:
            async with aiohttp.ClientSession() as session:
                async with session.post(server.make_url("/api/refuel"), data=body,
                                        headers={"Content-Type": "application/json"}) as reply:
                    return reply.status, await reply.json()

    status, answer = asyncio.run(run())
    return status, answer, calls


def with_changes(**changes):
    request = json.loads(json.dumps(REQUEST))
    for key, value in changes.items():
        if key in request["car"]:
            request["car"][key] = value
        else:
            request[key] = value
    return request


def test_a_complete_request_is_answered(monkeypatch):
    status, answer, calls = post(monkeypatch, REQUEST)

    assert status == 200
    assert answer == NO_STOP
    assert calls == [("planned_route", "optimal"), ("plan", 20, ())]


@pytest.mark.parametrize("body", [
    with_changes(tank_volume=29),
    with_changes(tank_volume=50, fuel=51),
    with_changes(consume_80=7.2, consume_130=5.5),
    with_changes(route="fast"),
    with_changes(reserve_km=501),
    {**REQUEST, "car": {key: value for key, value in REQUEST["car"].items() if key != "reserve_km"}},
    {**{key: value for key, value in REQUEST.items() if key != "fuel"}, "range": 3001},
    {**{key: value for key, value in REQUEST.items() if key != "fuel"}, "range": True},
    with_changes(range=300),
    {key: value for key, value in REQUEST.items() if key != "fuel"},
    {**REQUEST, "car": {**{key: value for key, value in REQUEST["car"].items() if key != "reserve_km"},
                        "reserve": 5}},
    "this is not JSON",
])
def test_an_invalid_request_gets_400_and_no_router_request(monkeypatch, body):
    status, _answer, calls = post(monkeypatch, body)

    assert status == 400
    assert calls == []


def test_an_empty_tank_is_accepted(monkeypatch):
    status, _answer, calls = post(monkeypatch, with_changes(fuel=0))

    assert status == 200
    assert calls[-1] == ("plan", 0, ())


def test_a_reserve_of_0_is_accepted(monkeypatch):
    status, _answer, calls = post(monkeypatch, with_changes(reserve_km=0))

    assert status == 200
    assert calls[-1] == ("plan", 20, ())


def test_a_range_without_fuel_is_accepted(monkeypatch):
    body = {**{key: value for key, value in REQUEST.items() if key != "fuel"}, "range": 300}

    status, _answer, calls = post(monkeypatch, body)

    assert status == 200
    assert calls[-1] == ("plan", "300 km", ())


def test_a_reserve_in_liters_from_an_old_page_is_ignored(monkeypatch):
    with_liters, without = [], []

    status, _answer, _calls = post(monkeypatch, {**REQUEST, "car": {**REQUEST["car"], "reserve": 5}}, cars=with_liters)
    post(monkeypatch, REQUEST, cars=without)

    assert status == 200
    assert with_liters == without


def test_a_journey_without_a_split_route_gets_404(monkeypatch):
    status, _answer, calls = post(monkeypatch, with_changes(route="super_optimal"), planned=None)

    assert status == 404
    assert calls == [("planned_route", "super_optimal")]


def test_a_route_failure_gets_502_with_its_cause(monkeypatch):
    status, answer, _calls = post(monkeypatch, REQUEST,
                                  route_error=route.RouteError("router_unavailable", "the router is down"))

    assert status == 502
    assert answer == {"error": "router_unavailable"}


def test_a_detour_failure_gets_502(monkeypatch):
    status, answer, _calls = post(monkeypatch, REQUEST, plan_error=RouterUnavailable("the router is down"))

    assert status == 502
    assert answer == {"error": "router_unavailable"}


def a_plan(optimal, indices):
    async def fake_plan_waypoints(routers, route_, origin, destination, *, max_waypoints):
        return WaypointPlan(indices=list(indices), locations=[optimal.coordinates[i] for i in indices])

    return fake_plan_waypoints


def link_waypoints(url):
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    return query["waypoints"][0].split("|")


def latlon(route_, index):
    longitude, latitude = route_.coordinates[index]
    return f"{latitude:.6f},{longitude:.6f}"


def kept_at(route_, *indices):
    return [refuel.Via(location=route_.coordinates[i], index=i, chosen=True) for i in indices]


def test_the_link_of_a_plan_fits_the_route_waypoints_and_the_stations(monkeypatch):
    optimal = straight_route(range(1, 22))
    monkeypatch.setattr(route, "plan_waypoints", a_plan(optimal, [2, 6, 10, 14, 18]))
    planned = SimpleNamespace(start="start", end="end", optimal=optimal)

    url = asyncio.run(route.link_through(None, planned, optimal, kept_at(optimal, 4, 12)))

    assert link_waypoints(url) == [latlon(optimal, i) for i in (2, 4, 6, 10, 12, 14, 18)]


def test_the_link_drops_the_route_waypoint_nearest_to_another(monkeypatch):
    optimal = straight_route(range(1, 31))
    monkeypatch.setattr(route, "plan_waypoints", a_plan(optimal, [2, 5, 8, 11, 14, 17, 22, 26]))
    planned = SimpleNamespace(start="start", end="end", optimal=optimal)

    url = asyncio.run(route.link_through(None, planned, optimal, kept_at(optimal, 12, 20)))

    assert link_waypoints(url) == [latlon(optimal, i) for i in (2, 5, 8, 12, 14, 17, 20, 22, 26)]


def test_a_route_waypoint_that_the_plan_leaves_is_not_in_the_link(monkeypatch):
    optimal = straight_route(range(1, 22))
    finished = straight_route([*range(1, 11), *range(100, 106), *range(15, 22)])
    monkeypatch.setattr(route, "plan_waypoints", a_plan(optimal, [5, 11, 17]))
    planned = SimpleNamespace(start="start", end="end", optimal=optimal)

    url = asyncio.run(route.link_through(None, planned, finished, kept_at(finished, 12)))

    assert link_waypoints(url) == [latlon(optimal, 5), latlon(finished, 12), latlon(optimal, 17)]


def test_more_than_9_stations_give_no_link(monkeypatch):
    optimal = straight_route(range(1, 31))
    searched = []

    async def refuse(*_args, **_kwargs):
        searched.append(True)

    monkeypatch.setattr(route, "plan_waypoints", refuse)
    planned = SimpleNamespace(start="start", end="end", optimal=optimal)

    assert asyncio.run(route.link_through(None, planned, optimal, kept_at(optimal, *range(2, 22, 2)))) is None
    assert searched == []


def test_a_request_without_chosen_stations_plans_the_first_stop(monkeypatch):
    status, _answer, calls = post(monkeypatch, REQUEST)

    assert status == 200
    assert calls[-1] == ("plan", 20, ())


def test_the_chosen_stations_reach_the_plan_in_order(monkeypatch):
    body = with_changes(chosen=[{"latitude": 47.0, "longitude": 2.0}, {"latitude": 45.34, "longitude": 4.805}])

    status, _answer, calls = post(monkeypatch, body)

    assert status == 200
    assert calls[-1] == ("plan", 20, ((47.0, 2.0), (45.34, 4.805)))


@pytest.mark.parametrize("chosen", [
    [{"latitude": 47.0, "longitude": 2.0}] * 21,
    [{"latitude": 45.34}],
    "A",
])
def test_invalid_chosen_stations_get_400_and_no_router_request(monkeypatch, chosen):
    status, _answer, calls = post(monkeypatch, with_changes(chosen=chosen))

    assert status == 400
    assert calls == []


def test_a_station_that_the_plan_does_not_need_gets_400(monkeypatch):
    status, _answer, _calls = post(monkeypatch, REQUEST, plan_error=refuel.UnneededStation("not needed"))

    assert status == 400


def test_no_route_through_the_chosen_stations_gets_502(monkeypatch):
    status, answer, _calls = post(monkeypatch, REQUEST, plan_error=NoRoute("no road"))

    assert status == 502
    assert answer == {"error": "no_route"}
