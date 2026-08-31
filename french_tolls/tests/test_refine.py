# -*- coding=utf-8 -*-
"""Which drift stretches the waypoint budget is spent on.

Every test builds a straight route along the equator and hand-writes the
stretches Google is supposed to have strayed over. Nothing here reaches Google
or the spend accounting: the one test that needs a whole first pass stubs both.

A metre of longitude at the equator is a metre of route, and a segment at
latitude zero measures exactly its share of the equator, so a route written this
way has cumulative distances that are the round numbers the tests name.
"""
import asyncio
from dataclasses import replace

import pytest
from pyproj import Geod

from .. import refine
from ..refine import _rank, waypoints_for

# Metres per degree of longitude at the equator, exactly as the module measures
# it: the WGS84 geodesic, not a sphere. 111 319.5 m against the 111 194.9 m the
# old constant gave, which is the 0.11% the sphere was running short by.
M_PER_DEGREE = Geod(ellps="WGS84").inv(0.0, 0.0, 1.0, 0.0)[2]

TOTAL_M = 1_000_000.0
STEP_M = 1_000.0


def route(total_m=TOTAL_M, step_m=STEP_M):
    """A due-east route from (0, 0), one point every `step_m`."""
    count = int(total_m / step_m) + 1
    return [(0.0, i * step_m / M_PER_DEGREE) for i in range(count)]


def at(ours, metres):
    """The point of `ours` that distance along it."""
    return ours[int(round(metres / STEP_M))]


def stretch(ours, from_m, to_m, length_m):
    """A stretch of Google's route bypassing `from_m`..`to_m` of ours.

    `length_m` is what Google drove instead, and it is what the ranking weighs.
    It is given rather than derived, because a detour is not the length of what
    it skips -- that is the whole reason a stretch is worth correcting.
    """
    return {"from": at(ours, from_m), "to": at(ours, to_m), "length": length_m}


def chosen(added):
    """The stretches a selection picked, named by the detour length each had."""
    return [w["google_detour_m"] for w in added]


# --------------------------------------------------------------------------
# The weight itself
# --------------------------------------------------------------------------

def test_a_stretch_at_the_origin_keeps_its_length():
    assert _rank(40_000.0, 0.0, TOTAL_M) == 40_000.0


def test_a_stretch_at_the_destination_counts_for_half():
    assert _rank(40_000.0, TOTAL_M, TOTAL_M) == 20_000.0


def test_the_weight_falls_linearly():
    assert _rank(40_000.0, TOTAL_M / 2, TOTAL_M) == 30_000.0


def test_a_route_of_no_length_weighs_nothing_down():
    assert _rank(40_000.0, 0.0, 0.0) == 40_000.0


# --------------------------------------------------------------------------
# Which stretches are chosen
# --------------------------------------------------------------------------

def test_an_earlier_stretch_outranks_a_longer_later_one():
    # 40 km at 50 km ranks 39 000; 60 km at 950 km ranks 31 500.
    ours = route()
    sections = [
        stretch(ours, 50_000, 90_000, 40_000.0),
        stretch(ours, 950_000, 990_000, 60_000.0),
    ]
    assert chosen(waypoints_for(sections, ours, budget=1)) == [40_000.0]


def test_a_later_stretch_wins_when_it_is_long_enough():
    # The weight halves a stretch at most, so it cannot overturn a threefold
    # difference in length: 20 000 against 31 500.
    ours = route()
    sections = [
        stretch(ours, 0, 20_000, 20_000.0),
        stretch(ours, 950_000, 990_000, 60_000.0),
    ]
    assert chosen(waypoints_for(sections, ours, budget=1)) == [60_000.0]


def test_stretches_at_the_same_place_are_ranked_by_length():
    ours = route()
    sections = [
        stretch(ours, 100_000, 130_000, 30_000.0),
        stretch(ours, 100_000, 150_000, 50_000.0),
    ]
    assert chosen(waypoints_for(sections, ours, budget=1)) == [50_000.0]


def test_raw_length_would_have_chosen_differently():
    # The point of the change, stated as a test: under the old ranking the
    # 60 km stretch was the longest and won outright.
    ours = route()
    sections = [
        stretch(ours, 50_000, 90_000, 40_000.0),
        stretch(ours, 950_000, 990_000, 60_000.0),
    ]
    longest = max(sections, key=lambda s: s["length"])
    assert longest["length"] == 60_000.0
    assert chosen(waypoints_for(sections, ours, budget=1)) == [40_000.0]


def test_two_of_seventeen():
    # Seventeen stretches of equal length spread evenly: the weight alone
    # decides, so the two earliest win.
    ours = route()
    sections = [stretch(ours, i * 55_000, i * 55_000 + 10_000, 10_000.0 + i)
                for i in range(17)]
    assert chosen(waypoints_for(sections, ours, budget=2)) == [10_000.0, 10_001.0]


def test_every_stretch_is_taken_when_the_budget_covers_them():
    ours = route()
    sections = [
        stretch(ours, 50_000, 90_000, 40_000.0),
        stretch(ours, 950_000, 990_000, 60_000.0),
    ]
    assert sorted(chosen(waypoints_for(sections, ours, budget=9))) == [40_000.0, 60_000.0]


def test_a_degenerate_route_selects_by_raw_length():
    ours = [(0.0, 0.0)] * 5
    sections = [
        {"from": (0.0, 0.0), "to": (0.0, 0.0), "length": 10_000.0},
        {"from": (0.0, 0.0), "to": (0.0, 0.0), "length": 30_000.0},
    ]
    assert chosen(waypoints_for(sections, ours, budget=1)) == [30_000.0]


# --------------------------------------------------------------------------
# What the ranking must not change
# --------------------------------------------------------------------------

def test_the_waypoint_is_the_midpoint_of_the_bypassed_portion():
    ours = route()
    sections = [stretch(ours, 200_000, 300_000, 140_000.0)]
    added = waypoints_for(sections, ours, budget=1)
    assert added[0]["at_m"] == pytest.approx(250_000.0)
    assert added[0]["latlon"] == list(at(ours, 250_000))


def test_the_waypoint_lies_on_our_route():
    ours = route()
    sections = [stretch(ours, 200_000, 300_000, 140_000.0)]
    added = waypoints_for(sections, ours, budget=1)
    assert tuple(added[0]["latlon"]) in set(ours)


def test_an_entry_carries_four_keys_and_no_score():
    ours = route()
    sections = [stretch(ours, 200_000, 300_000, 140_000.0)]
    added = waypoints_for(sections, ours, budget=1)
    assert set(added[0]) == {"latlon", "at_m", "skipped_m", "google_detour_m"}
    assert added[0]["skipped_m"] == pytest.approx(100_000.0)
    assert added[0]["google_detour_m"] == 140_000.0


def test_ends_the_wrong_way_round_are_swapped():
    ours = route()
    section = stretch(ours, 300_000, 200_000, 140_000.0)
    added = waypoints_for([section], ours, budget=1)
    assert added[0]["at_m"] == pytest.approx(250_000.0)
    assert added[0]["skipped_m"] == pytest.approx(100_000.0)


def test_nothing_to_spend_and_nothing_to_spend_it_on():
    ours = route()
    assert waypoints_for([stretch(ours, 0, 10_000, 5_000.0)], ours, budget=0) == []
    assert waypoints_for([], ours, budget=2) == []


# --------------------------------------------------------------------------
# The merge, through a whole first pass with Google and the store stubbed
# --------------------------------------------------------------------------

class FakeSpending:
    """The one call `_first_pass` makes, and what it was asked for.

    A coroutine, as `spending`'s own is. Nothing is written any more: a refinement
    is not stored, so the fake has nothing to record but the claims made against
    the month's ceiling.
    """

    def __init__(self):
        self.claims = []

    async def reserve_google_request(self, ceiling):
        self.claims.append(ceiling)
        return True


def google_leaving_between(ours, from_m, to_m, offset_deg=0.05):
    """Our route, but detouring well outside the corridor over one stretch."""
    lo, hi = int(from_m / STEP_M), int(to_m / STEP_M)
    return [(offset_deg if lo < i < hi else lat, lon)
            for i, (lat, lon) in enumerate(ours)]


def first_pass(monkeypatch, ours, theirs, original):
    fake = FakeSpending()
    monkeypatch.setattr(refine, "config", replace(
        refine.config, google_api_key="test-key", google_max_requests_per_month=100))
    monkeypatch.setattr(refine, "spending", fake)
    monkeypatch.setattr(refine, "_geometry", lambda route: theirs)

    async def request_route(from_, to, waypoints):
        return {"distanceMeters": 1, "duration": "1s"}

    monkeypatch.setattr(refine, "_request_route", request_route)

    result = asyncio.run(refine._first_pass(ours[0], ours[-1], ours, original))
    return result, fake


def test_a_new_waypoint_is_merged_in_route_order(monkeypatch):
    ours = route()
    theirs = google_leaving_between(ours, 500_000, 520_000)
    original = [[lon, lat] for lat, lon in (at(ours, 200_000), at(ours, 800_000))]

    result, fake = first_pass(monkeypatch, ours, theirs, original)

    assert result.refined
    assert len(result.waypoints) == 3
    assert result.waypoints[0] == original[0]
    assert result.waypoints[2] == original[1]
    # The new one falls between them, in the middle of what Google bypassed.
    lon = result.waypoints[1][0]
    assert 490_000 < lon * M_PER_DEGREE < 530_000
    assert result.added == [result.waypoints[1]]
    # One claim against the month's ceiling, and nothing stored: the refinement is
    # the return value now, not a row.
    assert fake.claims == [100]


def test_the_waypoints_asked_about_are_kept_apart_from_the_refined_set(monkeypatch):
    ours = route()
    theirs = google_leaving_between(ours, 500_000, 520_000)
    original = [[lon, lat] for lat, lon in (at(ours, 200_000), at(ours, 800_000))]

    result, _fake = first_pass(monkeypatch, ours, theirs, original)

    assert result.sent_waypoints == original
    assert result.nodes == []


def test_google_agreeing_adds_nothing(monkeypatch):
    ours = route()
    original = [[lon, lat] for lat, lon in (at(ours, 200_000),)]

    result, _fake = first_pass(monkeypatch, ours, list(ours), original)

    assert not result.refined
    assert result.reason == "Google already followed the route"
    assert result.waypoints == original
