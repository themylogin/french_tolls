"""A route the pricing step would refuse must never reach the route set.

The three holes these cover are the three ways such a route used to get in: the
search wanted the booth, a candidate crossed it on its way elsewhere, and a
route already on disk was carried forward untested.
"""

import textwrap

import pytest

import build_route_set
import build_vinci_prices
import overrides


# --------------------------------------------------------------------------
# One definition, read by two steps
# --------------------------------------------------------------------------

def write_overrides(tmp_path, body):
    path = tmp_path / "overrides.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(path)


def test_blocking_is_the_two_halves_of_a_pair(tmp_path):
    ov = overrides.load(write_overrides(tmp_path, """
        toll_booths:
          11:
            type: absent_enter
          22:
            type: absent_exit
          33:
            type: absent_passthrough
          44:
            type: ignore
          55:
            type: passthrough
          66:
            type: enter
    """))
    assert ov.blocking() == {11, 22}


def test_no_absent_override_blocks_nothing(tmp_path):
    ov = overrides.load(write_overrides(tmp_path, """
        toll_booths:
          33:
            type: absent_passthrough
    """))
    assert ov.blocking() == set()


def test_the_pricing_step_reads_the_same_definition():
    # A copy of the tuple in either step is a second source of truth, and the two
    # disagreeing is the failure the shared definition exists to prevent.
    assert build_vinci_prices.BLOCKING_ABSENT is overrides.BLOCKING


# --------------------------------------------------------------------------
# The search does not go looking for such a booth
# --------------------------------------------------------------------------

def test_a_blocking_booth_is_not_a_coverage_target():
    targets = build_route_set.coverage_targets(
        booths={1, 2, 3}, bidirectional=set(), plaza_pbf=None, blocking={2})
    assert targets == {(1, None), (3, None)}


def test_a_booth_the_operator_does_carry_stays_a_target():
    targets = build_route_set.coverage_targets(
        booths={1, 2, 3}, bidirectional=set(), plaza_pbf=None, blocking=set())
    assert targets == {(1, None), (2, None), (3, None)}


# --------------------------------------------------------------------------
# The search does not accept a route that crosses one
# --------------------------------------------------------------------------

class StubOsrm(build_route_set.Osrm):
    """`route_nodes` is the only thing `cover_many` asks the router for."""

    def __init__(self, drives):
        super().__init__("http://stub", workers=1)
        self.drives = drives

    def route_nodes(self, a, b):
        return self.drives.get((a["node_id"], b["node_id"]))


PLACES = {
    10: {"node_id": 10, "lat": 0.0, "lon": 0.0},
    20: {"node_id": 20, "lat": 1.0, "lon": 1.0},
    30: {"node_id": 30, "lat": 2.0, "lon": 2.0},
}

CLEAN = (10, 20)
BLOCKED = (10, 30)
BARRIER = (20, 30)

# 7 is the booth the operator does not carry as half a pair; 8 is a barrier it
# does not carry either, which forms no pair and so blocks nothing. 5 and 6 are
# ordinary priceable booths, and each unaskable route carries one of them --
# which is the whole reason a dropped route costs anything.
DRIVES = {
    CLEAN: [1, 5, 2, 6, 3],
    BLOCKED: [1, 5, 7, 2],
    BARRIER: [1, 8, 6, 2],
}


def cover(blocking, pairs=(CLEAN, BLOCKED, BARRIER)):
    return StubOsrm(DRIVES).cover_many(
        list(pairs), PLACES, traversable={5, 6, 7, 8}, resolve={},
        bidirectional=set(), blocking=blocking)


def test_a_candidate_crossing_an_absent_half_pair_is_withheld():
    results, blocked = cover(blocking={7})
    assert BLOCKED not in results
    assert blocked == [BLOCKED]


def test_it_is_withheld_however_much_else_it_covers():
    # The old bug in one line: gain alone decided, so a route covering five
    # wanted booths won and took all five down with it.
    results, _ = cover(blocking={7}, pairs=(BLOCKED,))
    assert results == {}


def test_an_absent_barrier_does_not_withhold_its_route():
    results, blocked = cover(blocking={7})
    assert BARRIER in results
    assert BARRIER not in blocked


def test_a_selected_route_still_reports_the_booth_it_drove():
    # The rule decides which routes are selected. It does not edit the record of
    # what a selected route drove.
    results, _ = cover(blocking={7})
    assert results[BARRIER] == ((8, None), (6, None))


def test_nothing_is_withheld_when_no_booth_blocks():
    results, blocked = cover(blocking=set())
    assert blocked == []
    assert set(results) == {CLEAN, BLOCKED, BARRIER}


def test_an_alias_is_tested_as_its_representative():
    # `cover_many` resolves a lane onto its plaza before recording it, and the
    # pricing step tests the representative. Testing the traversed id instead
    # would let the two steps disagree.
    osrm = StubOsrm({CLEAN: [1, 9, 2]})
    results, blocked = osrm.cover_many(
        [CLEAN], PLACES, traversable={9}, resolve={9: 7},
        bidirectional=set(), blocking={7})
    assert results == {}
    assert blocked == [CLEAN]


@pytest.mark.parametrize("pair", [CLEAN, BARRIER])
def test_an_askable_route_survives(pair):
    results, _ = cover(blocking={7}, pairs=(pair,))
    assert pair in results
