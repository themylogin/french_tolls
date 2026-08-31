# -*- coding=utf-8 -*-
"""What a driver is sent, for each way a journey can resolve.

Real routers, real booths, real handlers. Google is replayed from what it really
answered and Telegram is a transport that records rather than sends. Nothing
here builds a part, a token or a decision: a test shares two locations and
presses the button the bot put in the message it sent.

Every assertion is on the transcript -- the text, its order, the links, the
buttons -- and on the number of paid requests the flow would have made. That
second one matters as much as the first: it is the operator's bill, and nothing
else in this suite would notice it doubling.
"""
import asyncio
from urllib.parse import parse_qs, urlparse

import pytest

from .. import drive as drive_rules
from ..config import config
from ..refine import ROUTING_PREFERENCE
from .chat import Chat
from .google_replay import Missing, Replay, key_of, load
from .journeys import JOURNEYS, UNPINNED, by_key
from .telegram_transport import DRIVE_LABELS, Telegram

DESTINATION_PROMPT = "Now, send me the destination location"

_driven = {}


def driven(key):
    """Drive a pinned journey to its end, once per suite run.

    Memoised because several tests read one journey and re-driving it would buy
    nothing -- the answers are recorded, so a second run is the same run.
    """
    if key not in _driven:
        journey = by_key(key)

        async def run():
            async with Replay() as replay:
                async with Chat() as chat:
                    await chat.drive(journey.origin, journey.destination)
                return chat, replay

        _driven[key] = (journey, *asyncio.run(run()))
    return _driven[key]


# --- the seam holds -----------------------------------------------------------

def test_the_suite_cannot_reach_google():
    """Structural, not a promise: there is nowhere for a request to go."""
    assert config.google_routes_endpoint.startswith(
        ("http://127.0.0.1", "http://localhost")), \
        f"the endpoint is {config.google_routes_endpoint}, which would spend real money"


def test_no_socket_is_opened_to_telegram():
    journey, chat, _replay = driven("toll-free")

    assert isinstance(chat.application.bot.request, Telegram)
    assert [s.method for s in chat.sent][:1] == ["getMe"], \
        "the library identified the bot through the transport, as it does in production"


def test_the_library_builds_its_own_objects():
    """The flow replies to a message, edits it, and deletes another.

    None of that works unless what came back was parsed into a real `Message`,
    so this passing is the assertion. A journey that presses, because the
    deleted message is the one sent while Google is being checked with.
    """
    _journey, chat, _replay = driven("accepted-first-ask")
    methods = [s.method for s in chat.sent]

    assert "editMessageText" in methods, "the answer edits the message it replied with"
    assert "deleteMessage" in methods, "the working message is removed once it is spent"


def test_an_unrecorded_question_is_not_asked():
    replay = Replay()
    body = {"origin": {"location": {"latLng": {"latitude": 1.0, "longitude": 2.0}}},
            "destination": {"location": {"latLng": {"latitude": 3.0, "longitude": 4.0}}},
            "intermediates": [], "routingPreference": ROUTING_PREFERENCE}

    assert key_of(body) not in replay.answers

    with pytest.raises(Missing) as raised:
        asyncio.run(replay._answer(_Posted(body)))
    assert "no recording" in str(raised.value)


def test_a_recording_knows_what_bought_it(tmp_path):
    (tmp_path / "wrong.json").write_text(
        '{"preference": "TRAFFIC_UNAWARE", "calls": []}')

    with pytest.raises(Missing) as raised:
        load(str(tmp_path))
    assert "TRAFFIC_UNAWARE" in str(raised.value)
    assert ROUTING_PREFERENCE in str(raised.value)


def test_every_recording_was_bought_at_the_preference_in_use():
    assert load(), "no recordings loaded; the suite would assert nothing"


# --- the exchange -------------------------------------------------------------

def test_an_origin_alone_is_answered_with_a_prompt():
    _journey, chat, _replay = driven("toll-free")

    assert chat.texts()[0] == DESTINATION_PROMPT


@pytest.mark.parametrize("key", [j.key for j in JOURNEYS])
def test_every_token_pressed_came_from_the_bot(key):
    """A test that invented a token would pass while the bot offered nothing."""
    journey, chat, _replay = driven(key)
    offered = {b for m in chat.messages for b in m.buttons}

    if journey.asks:
        assert chat.pressed, "no button was pressed, so nothing was driven"
    else:
        assert not chat.pressed, \
            "a journey settled without Google is answered outright, with nothing to press"
    assert set(chat.pressed) <= offered, (
        f"pressed {chat.pressed}, but the bot only ever offered {sorted(offered)}")


def test_a_journey_that_splits_is_driven_by_pressing_for_each_part():
    _journey, chat, _replay = driven("split-all-tolled")

    assert len(chat.pressed) == 2, "the whole journey, then the part it owed"
    assert chat.pressed[0] != chat.pressed[1], "a fresh token for the fresh part"


# --- one test per outcome -----------------------------------------------------

@pytest.mark.parametrize("key", [j.key for j in JOURNEYS])
def test_a_pinned_journey_costs_what_it_is_pinned_to_cost(key):
    journey, _chat, replay = driven(key)

    assert replay.spent == journey.asks, (
        f"{journey.key} made {replay.spent} paid request(s), pinned at "
        f"{journey.asks}. {journey.outcome}")


@pytest.mark.parametrize("key", [j.key for j in JOURNEYS])
def test_a_pinned_journey_resolves_into_the_parts_it_is_pinned_to(key):
    journey, chat, _replay = driven(key)

    assert len(chat.parts) == journey.parts, (
        f"{journey.key} produced {len(chat.parts)} link(s), pinned at "
        f"{journey.parts}")


def test_a_toll_free_journey_buys_nothing():
    journey, chat, replay = driven("toll-free")

    assert replay.spent == 0, "a route that pays nothing has nothing to ask about"
    assert len(chat.parts) == 1
    assert drive_rules.AVOID_TOLLS in chat.parts[0].text


def test_a_journey_whose_two_routes_agree_buys_nothing():
    """It pays a toll, so it is not the toll-free case; it is answered anyway
    because our own fastest route crosses the booths our optimal one does."""
    _journey, chat, replay = driven("routes-agree")

    assert replay.spent == 0, "our own two routes agreeing settles it for free"
    assert len(chat.parts) == 1
    assert drive_rules.AVOID_TOLLS not in chat.parts[0].text, \
        "this journey pays a toll; it is not the toll-free rule that answered it"
    assert drive_rules.UNVERIFIED not in chat.parts[0].text

    link = chat.parts[0].links[-1]
    assert "waypoints" not in parse_qs(urlparse(link).query), \
        f"a link straight through carries no waypoints, got {link}"


def test_a_route_google_already_pays_our_tolls_for_is_sent_as_it_is():
    journey, chat, replay = driven("accepted-first-ask")

    assert replay.spent == 1, "one ask, no correction, no split"
    assert len(chat.parts) == 1
    assert drive_rules.COMPLEX not in chat.parts[0].text
    assert drive_rules.UNVERIFIED not in chat.parts[0].text


def test_a_route_google_leaves_is_corrected_and_then_sent():
    journey, chat, replay = driven("corrected-then-accepted")

    assert replay.spent == 2, "the first ask strayed, the second was accepted"
    assert len(chat.parts) == 1
    sent = [len(body.get("intermediates") or []) for body in replay.asked]
    assert sent[1] > sent[0], "the correcting ask carries more waypoints than the first"


def test_a_split_journey_arrives_one_part_at_a_time():
    journey, chat, _replay = driven("split-all-tolled")

    assert len(chat.parts) == 2
    assert drive_rules.COMPLEX in chat.parts[0].text, "the first part says the route is complex"
    assert chat.parts[0].buttons, "and offers the next"
    assert not chat.parts[-1].buttons, "the last part offers nothing further"


def test_a_toll_free_part_says_so_and_the_others_do_not():
    journey, chat, _replay = driven("split-with-a-free-part")

    free = [p for p in chat.parts if drive_rules.AVOID_TOLLS in p.text]
    assert len(free) == 1, "exactly one part of this journey pays nothing"
    assert free[0] is chat.parts[0], "and it is the one driven first"


def test_no_part_of_any_journey_claims_to_be_the_first_half():
    """The wording defect: three stretches all announced as the beginning."""
    for journey in JOURNEYS:
        _j, chat, _replay = driven(journey.key)
        for part in chat.parts:
            assert "first half" not in part.text.lower(), part.text


# --- the properties every journey rests on ------------------------------------

@pytest.mark.parametrize("key", [j.key for j in JOURNEYS])
def test_every_link_starts_where_the_driver_is(key):
    _journey, chat, _replay = driven(key)

    for part in chat.parts:
        assert part.links, "a part with no link is not a part"
        # The last link: a settled journey carries its drive link in the answer
        # message, after the comparison map.
        assert "origin=Current+Location" in part.links[-1], part.links[-1]


@pytest.mark.parametrize("key", [j.key for j in JOURNEYS])
def test_only_the_last_part_offers_an_action(key):
    _journey, chat, _replay = driven(key)

    offering = [i for i, p in enumerate(chat.parts) if p.buttons]
    assert offering == list(range(len(chat.parts) - 1)), (
        "every part but the last offers the next, and the last offers nothing")


@pytest.mark.parametrize("key", [j.key for j in JOURNEYS])
def test_every_part_carries_a_link_to_drive(key):
    _journey, chat, _replay = driven(key)

    for part in chat.parts:
        assert any(label in part.text for label in DRIVE_LABELS)


def test_the_answer_is_computed_from_real_routes():
    """Not a fixture: the distance, the cost and the map link are the routers'."""
    _journey, chat, _replay = driven("corrected-then-accepted")
    answer = chat.messages[1].text

    assert "Optimal route:" in answer and "Fastest route:" in answer
    assert "km" in answer and "€" in answer
    assert "Open comparison map" in answer


# --- what is not covered ------------------------------------------------------

def test_the_outcomes_with_no_journey_are_named():
    """Recorded rather than invented. See `journeys.UNPINNED` for why."""
    assert set(UNPINNED) == {
        "split into three parts",
        "accepted on the first ask above the fit share",
    }
    for reason in UNPINNED.values():
        assert len(reason) > 40, "a gap needs a reason, not a label"


class _Posted:
    """The one thing `Replay._answer` reads from a request."""

    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body
