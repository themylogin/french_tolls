# -*- coding=utf-8 -*-
import asyncio
from dataclasses import dataclass, field, replace
import json

import aiohttp
from aiohttp import web
from aiohttp.test_utils import TestServer
import yarl

from .. import relay
from ..config import config

NEAREST = "/api/osrm/toll/nearest/v1/driving/2.35,48.86"


@dataclass
class Exchange:
    status: int
    content_type: str
    body: bytes
    router_received: list = field(default_factory=list)

    def json(self):
        return json.loads(self.body)


async def router_ok(request):
    return web.Response(
        body=b'{"code":"Ok","waypoints":[]}',
        headers={"Content-Type": "application/json; charset=UTF-8"},
    )


def exchange(monkeypatch, path, *, token="s3cret", x_auth="s3cret", method="GET",
             answer=router_ok, router_up=True):
    received = []

    async def router(request):
        received.append((request.raw_path, dict(request.headers)))
        return await answer(request)

    async def run():
        router_app = web.Application()
        router_app.add_routes([web.get("/{rest:.*}", router)])
        router_server = TestServer(router_app)
        await router_server.start_server()
        base = str(router_server.make_url("")).rstrip("/")
        if not router_up:
            await router_server.close()

        monkeypatch.setattr(relay, "config", replace(
            config, osrm_access_token=token, osrm_toll_url=base, osrm_optimal_url=base))
        app = web.Application()
        relay.install(app)

        headers = {}
        if x_auth is not None:
            headers["X-Auth"] = x_auth

        async with TestServer(app) as server:
            url = yarl.URL(str(server.make_url("")).rstrip("/") + path, encoded=True)
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=headers) as resp:
                    result = Exchange(
                        status=resp.status,
                        content_type=resp.headers.get("Content-Type", ""),
                        body=await resp.read(),
                        router_received=received,
                    )

        if router_up:
            await router_server.close()
        return result

    return asyncio.run(run())


def test_no_token_no_relay(monkeypatch):
    result = exchange(monkeypatch, NEAREST, token="", x_auth="")

    assert result.status == 404
    assert result.router_received == []


def test_an_unknown_graph_is_not_served(monkeypatch):
    result = exchange(monkeypatch, "/api/osrm/fast/nearest/v1/driving/2.35,48.86")

    assert result.status == 404
    assert result.router_received == []


def test_only_get_is_served(monkeypatch):
    result = exchange(monkeypatch, NEAREST, method="POST")

    assert result.status == 405
    assert result.router_received == []


def test_a_missing_header_is_refused(monkeypatch):
    result = exchange(monkeypatch, NEAREST, x_auth=None)

    assert result.status == 401
    assert result.json()["code"] == "Unauthorized"
    assert result.router_received == []


def test_a_wrong_header_is_refused(monkeypatch):
    result = exchange(monkeypatch, NEAREST, x_auth="s3cre")

    assert result.status == 401
    assert result.json()["code"] == "Unauthorized"
    assert result.router_received == []


def test_a_holder_of_the_token_gets_the_routers_answer(monkeypatch):
    result = exchange(
        monkeypatch, "/api/osrm/optimal/route/v1/driving/2.35,48.86;4.83,45.76?overview=false")

    assert result.status == 200
    assert result.content_type == "application/json; charset=UTF-8"
    assert result.body == b'{"code":"Ok","waypoints":[]}'
    assert result.router_received[0][0] == "/route/v1/driving/2.35,48.86;4.83,45.76?overview=false"


def test_escapes_reach_the_router_unchanged(monkeypatch):
    result = exchange(
        monkeypatch, "/api/osrm/toll/route/v1/driving/2.35,48.86;4.83,45.76?hints=ab%2Bc%2Fd%3D;ef")

    assert result.router_received[0][0] == "/route/v1/driving/2.35,48.86;4.83,45.76?hints=ab%2Bc%2Fd%3D;ef"


def test_a_router_error_passes_through(monkeypatch):
    async def no_segment(request):
        return web.json_response(
            {"code": "NoSegment", "message": "Could not find a matching segment"}, status=400)

    result = exchange(monkeypatch, NEAREST, answer=no_segment)

    assert result.status == 400
    assert result.json() == {"code": "NoSegment", "message": "Could not find a matching segment"}


def test_a_stopped_router_is_reported(monkeypatch):
    result = exchange(monkeypatch, NEAREST, router_up=False)

    assert result.status == 502
    assert result.json()["code"] == "RouterUnavailable"
    assert "toll" in result.json()["message"]
    assert b"s3cret" not in result.body


def test_the_router_receives_the_token(monkeypatch):
    result = exchange(monkeypatch, NEAREST)

    assert result.router_received[0][1]["X-Auth"] == "s3cret"
