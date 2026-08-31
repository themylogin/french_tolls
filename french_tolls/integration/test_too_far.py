# -*- coding=utf-8 -*-
"""The guard that refuses a location nowhere near a road.

`handle_location` is the first thing a driver's message reaches, and the only
part of the bot that talks to a router before a journey exists.

Here rather than in the unit suite for the reason `test_parse_location` gives:
`bot` imports `route`, which loads the booth artefacts at import, and no unit
test may import a module that does. This suite has `data/` mounted.

It still reaches no router. The router is a stub answering with a distance,
which is the whole of what the guard reads.
"""
import asyncio

import pytest

from .. import bot
from ..osrm import SNAP_REACH_M, RouterUnavailable

PARIS = (2.3522, 48.8566)

# On the AP-7 in Catalonia, two kilometres south of the border. A better refusal
# than open water: it is on a motorway, and still 2 162.9 m from the nearest road
# the French extract carries -- measured against `osrm-toll`. Le Perthus, the
# village 5 km north on the French side, measures 50.5 m. The guard tracks where
# the extract stops, not where roads stop.
LA_JONQUERA = (2.8747, 42.4197)
LA_JONQUERA_M = 2162.9


class Message:
    """The three things `handle_location` uses a Telegram message for."""

    def __init__(self):
        self.from_user = type("User", (), {"id": 7})()
        self.replies = []

    async def reply_text(self, text):
        self.replies.append(text)


def answering(monkeypatch, *, metres=None, error=None):
    """Stub the router. Returns the list of locations it was asked about."""
    asked = []

    class Stub:
        async def distance_to_road_network(self, location):
            asked.append(location)
            if error is not None:
                raise error
            return metres

    monkeypatch.setattr(bot, "Routers", Stub)
    return asked


def handle(monkeypatch, location, **stub):
    """Run the handler once against a fresh state, and report what happened."""
    asked = answering(monkeypatch, **stub)
    message, state = Message(), bot.ChatState()
    asyncio.run(bot.handle_location(message, state, location))
    return message, state, asked


def test_a_location_on_a_road_is_accepted(monkeypatch):
    message, state, asked = handle(monkeypatch, PARIS, metres=72.0)

    assert asked == [PARIS], "the guard asks the router about the location it was given"
    assert bot.TOO_FAR not in message.replies
    assert state.users_from == {7: PARIS}, "the origin is remembered for the next message"


def test_a_location_off_the_network_is_refused(monkeypatch):
    message, state, _asked = handle(monkeypatch, LA_JONQUERA, metres=LA_JONQUERA_M)

    assert message.replies == [bot.TOO_FAR]
    assert state.users_from == {}, \
        "a refused origin must not be remembered, or the next message pairs with it"


def test_the_reach_itself_is_accepted(monkeypatch):
    """The comparison is `>`, so a location exactly at the reach is on the network."""
    message, state, _asked = handle(monkeypatch, PARIS, metres=SNAP_REACH_M)

    assert bot.TOO_FAR not in message.replies
    assert state.users_from == {7: PARIS}


def test_one_metre_past_the_reach_is_refused(monkeypatch):
    message, state, _asked = handle(monkeypatch, PARIS, metres=SNAP_REACH_M + 1)

    assert message.replies == [bot.TOO_FAR]
    assert state.users_from == {}


def test_a_router_that_fails_refuses_rather_than_raising(monkeypatch):
    """A driver gets the same sentence; the exception does not reach Telegram.

    Refusing is the safe reading. A journey that cannot be started is a message
    the driver can act on, where a traceback is a bot that has stopped replying.
    """
    message, state, _asked = handle(
        monkeypatch, PARIS, error=RouterUnavailable("osrm-toll did not answer"))

    assert message.replies == [bot.TOO_FAR]
    assert state.users_from == {}


def test_the_sentence_names_the_distance_the_guard_enforces():
    """The prose and the constant have to agree, and once did not.

    `TOO_FAR` says a kilometre and the check compares against `SNAP_REACH_M`.
    They were separate literals once, so raising the setting moved the limit and
    left the sentence claiming the old one.
    """
    assert SNAP_REACH_M == 1000.0
    assert "kilometer" in bot.TOO_FAR
