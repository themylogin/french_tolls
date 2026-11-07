# -*- coding=utf-8 -*-
import asyncio
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys

from aiohttp import web
from aiohttp.test_utils import TestServer

from .. import osrm
from ..config import config
from ..osrm import RouterUnavailable, Routers, Snap

ANSWER = {
    "code": "Ok",
    "waypoints": [{"location": [2.35, 48.86], "hint": "h", "nodes": [1, 2], "distance": 1.0}],
    "matchings": [{"legs": [{"annotation": {"nodes": [1, 2]}}]}],
    "routes": [{
        "legs": [{"annotation": {"nodes": [1, 2], "distance": [1.0], "duration": [1.0]}}],
        "geometry": {"coordinates": [[2.35, 48.86], [2.36, 48.87]]},
        "distance": 1.0,
        "duration": 1.0,
        "weight": 1.0,
    }],
}

PARIS = Snap(location=(2.35, 48.86), hint="h", nodes=(1, 2), distance_m=1.0)


class Recorded(Routers):
    def __init__(self):
        super().__init__()
        self.bases = []

    async def _get(self, base, path, params):
        self.bases.append(base)
        return ANSWER


def configure(monkeypatch, **settings):
    monkeypatch.setattr(osrm, "config", replace(config, **settings))


def snap_against(monkeypatch, answer):
    received = []

    async def router(request):
        received.append(request.headers)
        return await answer(request)

    async def run():
        app = web.Application()
        app.add_routes([web.get("/{rest:.*}", router)])
        async with TestServer(app) as server:
            configure(monkeypatch, osrm_toll_url=str(server.make_url("")).rstrip("/"),
                      osrm_access_token=osrm.config.osrm_access_token)
            try:
                await Routers().snap((2.35, 48.86))
            except RouterUnavailable as e:
                return received, e
        return received, None

    return asyncio.run(run())


async def ok(request):
    return web.json_response(ANSWER)


def test_the_router_addresses_default_to_the_service_names():
    assert config.osrm_toll_url == "http://osrm-toll:5000"
    assert config.osrm_optimal_url == "http://osrm-optimal:5000"
    assert config.osrm_access_token == ""


def test_a_trailing_slash_is_dropped():
    env = {**os.environ, "OSRM_TOLL_URL": "https://example.org/api/osrm/toll/"}
    result = subprocess.run(
        [sys.executable, "-c", "from french_tolls.config import config; print(config.osrm_toll_url)"],
        env=env, cwd=Path(__file__).parents[2], capture_output=True, text=True, check=True,
    )

    assert result.stdout.strip() == "https://example.org/api/osrm/toll"


def test_each_graph_is_asked_at_its_configured_address(monkeypatch):
    configure(monkeypatch, osrm_toll_url="https://example.org/api/osrm/toll")
    routers = Recorded()

    async def ask():
        await routers.snap((2.35, 48.86))
        await routers.distance_to_road_network((2.35, 48.86))
        await routers.match([(2.35, 48.86), (2.36, 48.87)])
        await routers.fast(PARIS, PARIS)
        await routers.optimal(PARIS, PARIS)

    asyncio.run(ask())

    assert routers.bases == [
        "https://example.org/api/osrm/toll",
        "https://example.org/api/osrm/toll",
        "https://example.org/api/osrm/toll",
        "https://example.org/api/osrm/toll",
        "http://osrm-optimal:5000",
    ]


def test_the_token_is_sent_as_x_auth(monkeypatch):
    configure(monkeypatch, osrm_access_token="s3cret")

    received, error = snap_against(monkeypatch, ok)

    assert error is None
    assert received[0]["X-Auth"] == "s3cret"


def test_no_token_sends_no_x_auth(monkeypatch):
    configure(monkeypatch, osrm_access_token="")

    received, error = snap_against(monkeypatch, ok)

    assert error is None
    assert "X-Auth" not in received[0]


def test_an_html_error_page_is_an_unavailable_router(monkeypatch):
    configure(monkeypatch)

    async def bad_gateway(request):
        return web.Response(status=502, text="<html>502 Bad Gateway</html>", content_type="text/html")

    _received, error = snap_against(monkeypatch, bad_gateway)

    assert isinstance(error, RouterUnavailable)
    assert "502" in str(error)
    assert "http://127.0.0.1:" in str(error)


def test_a_refused_token_is_an_unavailable_router_that_hides_the_token(monkeypatch):
    configure(monkeypatch, osrm_access_token="s3cret")

    async def unauthorized(request):
        return web.json_response(
            {"code": "Unauthorized", "message": "X-Auth does not match"}, status=401)

    _received, error = snap_against(monkeypatch, unauthorized)

    assert isinstance(error, RouterUnavailable)
    assert "Unauthorized" in str(error)
    assert "s3cret" not in str(error)
