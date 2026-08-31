# -*- coding=utf-8 -*-
"""Turning a foreign geometry into the booths it crosses.

The router is answered from a written-down response rather than reached. What is
worth testing here is not that OSRM matches -- it does -- but what this project
does with what it returns: that the trace goes in one request, that a leg's
repeated head does not become a second charge, and that a trace the matcher gave
up on is admitted to be unpriced rather than priced wrongly.
"""
import asyncio

from ..equivalence import booths_of, matched_nodes, optimize
from ..overlap import lengths_m
from ..osrm import Routers
from ..tolls import account, booths_crossed
from .booths import build_booths, entrance, exit_, lane, passthrough


class Recorded(Routers):
    """A router that answers from a written response and remembers the request."""

    def __init__(self, body):
        super().__init__()
        self.body = body
        self.asked = []

    async def _get(self, base, path, params):
        self.asked.append((base, path, params))
        return self.body


def matching(*legs):
    """A response body: one matching made of the given node sequences."""
    return {"code": "Ok", "matchings": [
        {"legs": [{"annotation": {"nodes": list(nodes)}} for nodes in legs]}]}


def in_pieces(*matchings):
    return {"code": "Ok", "matchings": [
        {"legs": [{"annotation": {"nodes": list(nodes)}}]} for nodes in matchings]}


def line(n, spacing_deg=0.01, lat=45.0):
    return [(1.0 + i * spacing_deg, lat) for i in range(n)]


# --- the request ---------------------------------------------------------------

def test_the_whole_trace_goes_in_one_request():
    """The defect this guards is the reason the method works at all.

    Matched in windows, each window is placed with no knowledge of the road
    driven before it, and at a boundary the matcher may start on a slip road.
    That is what skipped a plaza and 13.70 EUR on a trace identical to ours.
    """
    routers = Recorded(matching([1, 2, 3]))

    asyncio.run(matched_nodes(routers, line(4000)))

    assert len(routers.asked) == 1, "a trace matched in more than one request"
    _base, path, _params = routers.asked[0]
    assert path.count(";") == len(optimize(line(4000))) - 1, \
        "the one request must carry every point of the trace"


def test_the_trace_is_matched_on_the_untouched_graph():
    routers = Recorded(matching([1, 2, 3]))

    asyncio.run(matched_nodes(routers, line(10)))

    base, path, params = routers.asked[0]
    assert "osrm-toll" in base, "a route is being placed on the map, not priced by it"
    assert path.startswith("/match/")
    assert params["annotations"] == "nodes"
    assert params["overview"] == "false", "the geometry is a megabyte nobody reads"


def test_a_trace_is_thinned_and_keeps_its_ends():
    dense = line(1000, spacing_deg=0.0001)      # about 8 m apart

    thinned = optimize(dense)

    assert thinned[0] == dense[0] and thinned[-1] == dense[-1]
    assert 1 < len(thinned) < len(dense) / 10


def test_a_short_trace_is_left_alone():
    assert optimize([(1.0, 45.0), (1.0001, 45.0)]) == [(1.0, 45.0), (1.0001, 45.0)]


# --- what thinning may not cost ------------------------------------------------
#
# The thinning measures in a projection. These say what that is allowed to do to
# the trace: choose which points go, and nothing else. A projection that started
# moving coordinates, or one that quietly stopped honouring the spacing, would
# still return a plausible trace and would be found only in a toll total.

def test_the_points_that_survive_are_the_ones_that_came_in():
    """No coordinate is recomputed, rounded, or nudged by the projection."""
    dense = line(2000, spacing_deg=0.0001)

    thinned = optimize(dense)

    assert set(thinned) <= set(dense)
    assert len(thinned) < len(dense)


def test_the_ends_are_kept_exactly():
    """They are where the journey begins and ends.

    A hundred metres of movement here is what puts a match on the wrong side of
    a junction, so these two are not approximately preserved.
    """
    dense = line(2000, spacing_deg=0.0001)

    thinned = optimize(dense)

    assert thinned[0] == dense[0]
    assert thinned[-1] == dense[-1]


def test_every_gap_really_is_the_spacing_measured_geodesically():
    """The spacing is honoured against the exact geodesic, not just the plane.

    The walk reads distances off a projection; this checks the result against
    `pyproj`'s WGS84 geodesic, so a projection that drifted would show up as a
    gap that is not the gap it claimed.
    """
    thinned = optimize(line(3000, spacing_deg=0.0001), spacing_m=250.0)

    latlon = [(lat, lon) for lon, lat in thinned]
    # The last gap is whatever was left over when the end was reached.
    gaps = lengths_m(latlon)[:-1]

    assert gaps.min() >= 250.0 * 0.999
    # And not wastefully far past it: a point every ~8 m means the first one
    # over the line is barely over it.
    assert gaps.max() < 250.0 * 1.05


def test_the_walk_skips_ahead_without_changing_what_it_keeps():
    """The searchsorted jump is an optimisation, not a different rule.

    Distance along the trace bounds distance across it, so the walk may jump
    over points that cannot qualify. This pins that the jump keeps exactly what
    testing every point one at a time would have kept.
    """
    trace = line(4000, spacing_deg=0.0002)

    def one_at_a_time(coordinates, spacing_m):
        out = [coordinates[0]]
        for point in coordinates[1:-1]:
            a, b = (out[-1][1], out[-1][0]), (point[1], point[0])
            if lengths_m([a, b])[0] >= spacing_m:
                out.append(point)
        out.append(coordinates[-1])
        return out

    assert optimize(trace, 250.0) == one_at_a_time(trace, 250.0)


# --- reading the answer --------------------------------------------------------

def test_a_repeated_leg_head_does_not_become_a_second_charge():
    """A leg's nodes begin with the node *before* it, so a booth reappears.

    Measured: three phantom crossings and 3.00 EUR on a route whose geometry was
    identical to ours.
    """
    b = build_booths(passthrough("SAINT-ARNOULT", price=3.00))
    booth = b["SAINT-ARNOULT"]
    routers = Recorded(matching([1, booth, 2], [booth, 2, 3]))

    nodes = asyncio.run(matched_nodes(routers, line(10)))

    assert account(b.data, nodes).cost == 3.00, "one plaza, one charge"


def test_the_matched_nodes_are_a_path():
    """No node twice running: that would be an edge of no length."""
    routers = Recorded(matching([1, 2, 3], [2, 3, 4], [3, 4, 5]))

    nodes = asyncio.run(matched_nodes(routers, line(10)))

    assert nodes == (1, 2, 3, 4, 5)


def test_the_first_legs_head_is_kept():
    """Only the repetition is dropped. The first leg's head is not a repetition."""
    b = build_booths(passthrough("BOULAY", price=2.00))
    booth = b["BOULAY"]
    routers = Recorded(matching([booth, 1, 2]))

    nodes = asyncio.run(matched_nodes(routers, line(10)))

    assert nodes[0] == booth
    assert account(b.data, nodes).cost == 2.00


def test_a_trace_matched_in_pieces_is_not_priced():
    """A break between an entrance and its exit misprices everything after it."""
    routers = Recorded(in_pieces([1, 2, 3], [7, 8, 9]))

    assert asyncio.run(matched_nodes(routers, line(10))) is None


def test_a_trace_the_router_could_not_match_is_not_priced():
    routers = Recorded({"code": "Ok", "matchings": []})

    assert asyncio.run(matched_nodes(routers, line(10))) is None


# --- the booths ----------------------------------------------------------------

def test_a_plaza_is_one_booth_whichever_lane_was_driven():
    """The whole comparison rests on this: a lane resolves to its plaza."""
    b = build_booths(
        passthrough("SAINT-ARNOULT", price=3.00),
        lane("SAINT-ARNOULT lane 4", of="SAINT-ARNOULT"),
    )

    assert booths_crossed(b.data, b.route(1, "SAINT-ARNOULT", 2)) == \
        booths_crossed(b.data, b.route(1, "SAINT-ARNOULT lane 4", 2))


def test_a_ticketed_section_is_two_booths_and_not_one_passage():
    """`peages` reports one line; the set has to hold both ends.

    A comparison built from passage names would call two routes equivalent when
    one of them entered somewhere else and happened to leave at the same exit.
    """
    b = build_booths(
        entrance("VOREPPE", gare="00001", prices={"00002": 13.70}),
        exit_("MOIRANS", gare="00002"),
    )

    crossed = booths_crossed(b.data, b.route("VOREPPE", 1, "MOIRANS"))

    assert crossed == {b["VOREPPE"], b["MOIRANS"]}


def test_a_plaza_crossed_twice_is_one_booth():
    b = build_booths(passthrough("SAINT-ARNOULT", price=3.00))

    crossed = booths_crossed(b.data, b.route("SAINT-ARNOULT", 1, "SAINT-ARNOULT"))

    assert crossed == {b["SAINT-ARNOULT"]}


def test_the_booths_of_a_geometry_come_from_the_matched_nodes():
    b = build_booths(passthrough("SAINT-ARNOULT", price=3.00))
    booth = b["SAINT-ARNOULT"]
    routers = Recorded(matching([1, booth, 2]))

    assert asyncio.run(booths_of(routers, b.data, line(10))) == {booth}


def test_an_unmatchable_geometry_has_no_booths_rather_than_none_of_them():
    """None and the empty set are different answers, and the difference decides."""
    b = build_booths(passthrough("SAINT-ARNOULT", price=3.00))
    routers = Recorded(in_pieces([1, 2], [8, 9]))

    assert asyncio.run(booths_of(routers, b.data, line(10))) is None
