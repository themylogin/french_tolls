# -*- coding=utf-8 -*-
"""Google, answered from what it really said.

A real HTTP server on localhost, and the application's own client posts to it.
Nothing is patched: `_ask_google` builds the body, sets the field mask, encodes
the JSON, reads the status and decodes the answer, exactly as in production. The
only difference is the host in `GOOGLE_ROUTES_ENDPOINT`.

Patching that function instead would skip all of it, which is the part most
likely to break without anyone noticing.

A recording holds the request that was sent and the answer that came back, keyed
by the request. A question with no recording is an error, never a forward: the
suite is specified to spend nothing, and a test that quietly asked Google would
spend and then assert against an answer nobody recorded.
"""
import hashlib
import json
import os
import urllib.parse

from aiohttp import web

from ..refine import ROUTING_PREFERENCE

__all__ = ["Missing", "Replay", "key_of", "load"]

CASSETTES = os.environ.get(
    "GOOGLE_CASSETTES",
    os.path.join(os.path.dirname(__file__), "cassettes"))


class Missing(Exception):
    """The flow asked something no recording answers."""


def key_of(body: dict) -> str:
    """A recording's key: the request, canonically.

    The whole body, so a recording answers the question it was asked and no
    other. The body carries the waypoints and the waypoints come from the graph,
    so a rebuilt graph misses every recording at once -- loudly, as a wall of
    `Missing`, and the fix is to record again. A looser key would survive the
    rebuild by answering with the route for waypoints that have moved, which is
    a test that passes while asserting nothing.
    """
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]


def load(directory=None) -> dict:
    """Every recording, by key."""
    directory = directory or CASSETTES
    answers = {}
    if not os.path.isdir(directory):
        return answers

    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(directory, name)) as f:
            cassette = json.load(f)

        preference = cassette.get("preference")
        if preference != ROUTING_PREFERENCE:
            # A recording bought under another routing quality answers a
            # different question. The same journeys resolve differently beneath
            # it -- one of these is accepted outright at one quality and splits
            # into three parts at another -- so replaying it would assert
            # against a route the application would not receive.
            raise Missing(
                f"{name} was recorded at {preference!r} and this application "
                f"asks at {ROUTING_PREFERENCE!r}. Record it again.")

        for call in cassette["calls"]:
            answers[call["key"]] = call["response"]

    return answers


class Replay:
    """The replay server, and what it was asked."""

    def __init__(self, endpoint=None, directory=None):
        self.answers = load(directory)
        self.asked = []
        self.endpoint = endpoint or os.environ.get("GOOGLE_ROUTES_ENDPOINT", "")
        if not self.endpoint:
            raise RuntimeError(
                "GOOGLE_ROUTES_ENDPOINT is unset, so the application would ask "
                "Google itself. Refusing to run.")

        parsed = urllib.parse.urlparse(self.endpoint)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 80
        self.path = parsed.path
        self._runner = None

    @property
    def spent(self) -> int:
        """How many paid requests this journey would have cost."""
        return len(self.asked)

    async def __aenter__(self):
        app = web.Application()
        app.add_routes([web.post(self.path, self._answer)])
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        await web.TCPSite(self._runner, self.host, self.port).start()
        return self

    async def __aexit__(self, *_exc):
        await self._runner.cleanup()
        return False

    async def _answer(self, request):
        body = await request.json()
        key = key_of(body)
        self.asked.append(body)

        answer = self.answers.get(key)
        if answer is None:
            raise Missing(
                f"no recording for {key}: "
                f"{_describe(body)}. "
                f"{len(self.answers)} recordings loaded. Record this journey again.")

        return web.json_response(answer)


def _describe(body):
    def ll(point):
        v = point["location"]["latLng"]
        return f"{v['latitude']:.6f},{v['longitude']:.6f}"

    return (f"{ll(body['origin'])} -> {ll(body['destination'])} through "
            f"{len(body.get('intermediates') or [])} waypoint(s) at "
            f"{body.get('routingPreference')}")
