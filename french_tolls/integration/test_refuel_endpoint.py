# -*- coding=utf-8 -*-
"""`route.planned_route` and `POST /api/refuel`.

Here rather than in the unit suite for the reason `test_too_far` gives: `route`
loads the booth artefacts at import, and `api` imports `route`. This suite has
`data/` mounted. It reaches no router.
"""
import asyncio
import json

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import pytest

from .. import api, refuel, route
from ..osrm import Route, RouterUnavailable, Snap

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
    def __init__(self, optimal, *, error=None):
        self.optimal_route = optimal
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
    "car": {"fuel_type": "diesel", "tank_volume": 50, "consume_80": 5.5, "consume_130": 7.2},
    "fuel": 20,
}
PLANNED = object()
NO_STOP = {"stop_needed": False, "fuel_left": 12.7}


def post(monkeypatch, body, *, planned=PLANNED, route_error=None, plan_error=None):
    calls = []

    async def fake_planned_route(routers, from_, to, name):
        calls.append(("planned_route", name))
        if route_error is not None:
            raise route_error
        return planned

    async def fake_plan(routers, planned_, parameters, fuel, toll_cost):
        calls.append(("plan", fuel))
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
    assert calls == [("planned_route", "optimal"), ("plan", 20)]


@pytest.mark.parametrize("body", [
    with_changes(tank_volume=29),
    with_changes(tank_volume=50, fuel=51),
    with_changes(consume_80=7.2, consume_130=5.5),
    with_changes(route="fast"),
    {key: value for key, value in REQUEST.items() if key != "fuel"},
    "this is not JSON",
])
def test_an_invalid_request_gets_400_and_no_router_request(monkeypatch, body):
    status, _answer, calls = post(monkeypatch, body)

    assert status == 400
    assert calls == []


def test_an_empty_tank_is_accepted(monkeypatch):
    status, _answer, calls = post(monkeypatch, with_changes(fuel=0))

    assert status == 200
    assert calls[-1] == ("plan", 0)


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
