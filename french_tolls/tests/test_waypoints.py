# -*- coding=utf-8 -*-
"""Reducing the optimal route to the waypoints a fastest-path router needs.

Every test writes a graph, runs the search against a stub answering from it, and
asserts what the search did. Nothing here reaches a routing service, reads
`data/`, or imports `route`.

A graph names only the legs on which the fast graph *differs* from the optimal
route. Every other leg answers with the optimal slice, so `fast_legs={(0, 9): …}`
reads as "the fast graph disagrees over the whole route, and nowhere else".
"""
import asyncio

from ..waypoints import plan_waypoints
from .graph import FakeRouters, Graph, leg_rejoining, leg_with_extra_node

# Node ids well away from the position indices, so a node id and a position are
# never confused when a failure prints them.
NODES = [1000 + i for i in range(20)]


def search(graph, *, budget=1000, max_waypoints=9):
    """Run the search over a graph and hand back the plan and the stub."""
    routers = FakeRouters(graph, budget=budget)

    plan = asyncio.run(plan_waypoints(
        routers,
        graph.optimal_route(),
        routers.origin(),
        routers.destination(),
        max_waypoints=max_waypoints,
    ))

    return plan, routers


def detour_from(graph, a, b):
    """A leg between two positions that drives a road the optimal route does not."""
    return [graph.node_ids[a]] + [-1, -2, -3] + [graph.node_ids[b]]


# --------------------------------------------------------------------------
# Nothing to do
# --------------------------------------------------------------------------

def test_a_route_the_fast_graph_already_drives_needs_no_waypoint():
    graph = Graph(node_ids=NODES)

    plan, routers = search(graph)

    assert plan.locations == []
    assert plan.needed == 0
    assert plan.complete is True
    assert plan.divergences == []
    # The destination is probed first, so agreement costs one leg.
    assert routers.legs_asked == [(0, graph.last)]


def test_a_two_node_route_needs_no_waypoint():
    graph = Graph(node_ids=NODES[:2])

    plan, _routers = search(graph)

    assert plan.locations == []
    assert plan.complete is True


# --------------------------------------------------------------------------
# Reaching as far as the leg allows
# --------------------------------------------------------------------------

def test_the_search_reaches_the_furthest_reproducing_position():
    """The furthest reach is at nine tenths of the route, not at the midpoint.

    The search this replaces halved the interval and never widened it, so it
    could not find a step longer than half the remainder however far the fast
    graph agreed.
    """
    graph = Graph(
        node_ids=NODES,
        # Only the whole-route leg differs; every leg ending at 18 or earlier
        # reproduces the route.
        fast_legs={(0, 19): detour_from(Graph(node_ids=NODES), 0, 19)},
    )

    plan, _routers = search(graph)

    assert plan.indices == [18]
    assert plan.needed == 1
    assert plan.complete is True


def test_every_emitted_waypoint_had_its_own_leg_verified():
    """The leg the driver drives is the one that must have been checked.

    Verifying a leg between two interior positions and then emitting its far end
    as the first waypoint proves nothing: two fastest paths laid end to end are
    not a fastest path.
    """
    base = Graph(node_ids=NODES)
    graph = Graph(
        node_ids=NODES,
        fast_legs={
            (0, 19): detour_from(base, 0, 19),
            (0, 12): detour_from(base, 0, 12),
            (0, 11): detour_from(base, 0, 11),
            (0, 10): detour_from(base, 0, 10),
        },
    )

    plan, routers = search(graph)

    assert plan.indices, "this graph is meant to need a waypoint"

    anchors = [0] + plan.indices
    for anchor, waypoint in zip(anchors, plan.indices):
        assert (anchor, waypoint) in routers.legs_asked, (
            f"waypoint {waypoint} was emitted without its leg from {anchor} "
            f"being requested; legs asked were {routers.legs_asked}"
        )


def test_the_search_walks_the_whole_route():
    base = Graph(node_ids=NODES)
    graph = Graph(
        node_ids=NODES,
        fast_legs={
            (0, 19): detour_from(base, 0, 19),
            (0, 15): detour_from(base, 0, 15),
            (0, 14): detour_from(base, 0, 14),
            (0, 13): detour_from(base, 0, 13),
            (0, 12): detour_from(base, 0, 12),
            (0, 11): detour_from(base, 0, 11),
        },
    )

    plan, _routers = search(graph)

    assert plan.complete is True
    assert plan.indices == sorted(plan.indices), "waypoints must be in driven order"
    assert all(0 < i < graph.last for i in plan.indices), (
        "a waypoint is intermediate; the endpoints are not waypoints"
    )


# --------------------------------------------------------------------------
# What counts as reproducing the route
# --------------------------------------------------------------------------

def test_a_leg_that_leaves_the_route_and_rejoins_it_does_not_reproduce_it():
    """Its two ends match, and everything outside the detour matches.

    A comparison of endpoints alone would wave it through, and the driver would
    pay for the road it took instead.
    """
    base = Graph(node_ids=NODES)
    graph = Graph(
        node_ids=NODES,
        fast_legs={(0, 19): leg_rejoining(base, 0, 19, at=9, detour=[-1, -2])},
    )

    plan, _routers = search(graph)

    assert plan.needed >= 1, (
        "a rejoining leg was accepted as reproducing the optimal route"
    )


def test_a_leg_carrying_an_endpoints_neighbour_on_the_route_does_reproduce_it():
    """The router snaps onto a segment and annotates that segment's other end.

    Measured on the France graph: a leg from position i comes back as
    `optimal[i - 1]` followed by `optimal[i..b]`. Forgiving it is what keeps an
    ordinary journey from reading as a wall of divergences.
    """
    base = Graph(node_ids=NODES)
    graph = Graph(
        node_ids=NODES,
        # The whole-route leg carries the node *after* the destination... which
        # does not exist, so use a leg from an interior anchor instead: make the
        # whole route fail, then let the leg from 0 to 18 carry node 19.
        fast_legs={
            (0, 19): detour_from(base, 0, 19),
            (0, 18): leg_with_extra_node(base, 0, 18, trailing=NODES[19]),
        },
    )

    plan, _routers = search(graph)

    assert plan.indices == [18], (
        "a leg carrying the destination's own next node was rejected"
    )


def test_a_leg_carrying_any_other_extra_node_does_not_reproduce_it():
    base = Graph(node_ids=NODES)
    graph = Graph(
        node_ids=NODES,
        fast_legs={
            (0, 19): detour_from(base, 0, 19),
            # Not the route's node at 19 — a node from another road entirely.
            (0, 18): leg_with_extra_node(base, 0, 18, trailing=-99),
        },
    )

    plan, _routers = search(graph)

    assert plan.indices != [18], (
        "an extra node that is not the endpoint's neighbour on the route was forgiven"
    )


# --------------------------------------------------------------------------
# A waypoint has to survive being handed over bare
# --------------------------------------------------------------------------

def test_a_position_that_snaps_off_the_route_is_not_emitted():
    """Google is handed a coordinate and nothing else.

    Where the optimal route runs beside another road within snapping distance,
    a bare coordinate can land on the wrong one and the router drives elsewhere.
    A hinted leg answers a different question and hides it.
    """
    base = Graph(node_ids=NODES)
    graph = Graph(
        node_ids=NODES,
        fast_legs={(0, 19): detour_from(base, 0, 19)},
        off_route={18},
    )

    plan, _routers = search(graph)

    assert 18 not in plan.indices, "a waypoint was emitted beside another road"
    assert plan.indices == [17], "the search should fall back to the position before it"


def test_the_fallback_position_had_its_own_leg_verified_too():
    base = Graph(node_ids=NODES)
    graph = Graph(
        node_ids=NODES,
        fast_legs={(0, 19): detour_from(base, 0, 19)},
        off_route={18, 17},
    )

    plan, routers = search(graph)

    assert plan.indices == [16]
    assert (0, 16) in routers.legs_asked


def test_off_route_positions_do_not_stop_the_search_reaching_the_end():
    """Emittability and reproduction are different questions.

    Letting the first end the search makes it emit a waypoint a few metres into
    a journey whose two routes are the same road.
    """
    graph = Graph(node_ids=NODES, off_route={4, 8, 12})

    plan, _routers = search(graph)

    assert plan.locations == []
    assert plan.needed == 0
    assert plan.complete is True


# --------------------------------------------------------------------------
# The bounds
# --------------------------------------------------------------------------

def _graph_needing_several_waypoints():
    """A graph on which the fast graph agrees only over short stretches."""
    base = Graph(node_ids=NODES)
    fast_legs = {}
    for a in range(0, 20):
        for b in range(a + 4, 20):
            fast_legs[(a, b)] = detour_from(base, a, b)
    return Graph(node_ids=NODES, fast_legs=fast_legs)


def test_the_cap_truncates_the_list_and_says_how_many_were_needed():
    graph = _graph_needing_several_waypoints()

    full, _ = search(graph)
    assert full.needed >= 4, f"this graph should need several waypoints, needs {full.needed}"

    capped, _ = search(graph, max_waypoints=2)

    assert len(capped.locations) == 2
    assert capped.needed == full.needed
    assert capped.complete is False
    assert capped.truncated_by == "cap"


def test_under_the_cap_the_answer_is_not_marked():
    graph = _graph_needing_several_waypoints()

    plan, _routers = search(graph)

    assert len(plan.locations) == plan.needed
    assert plan.complete is True
    assert plan.truncated_by is None


def test_the_budget_returns_what_was_verified_and_raises_nothing():
    graph = _graph_needing_several_waypoints()

    full, full_routers = search(graph)
    budget = full_routers.requests // 2

    plan, routers = search(graph, budget=budget)

    assert routers.requests <= budget
    assert plan.complete is False
    assert plan.truncated_by == "budget"
    assert len(plan.locations) == plan.needed
    assert plan.needed < full.needed


def test_a_budget_of_one_still_returns_a_plan():
    graph = _graph_needing_several_waypoints()

    plan, _routers = search(graph, budget=1)

    assert plan.locations == []
    assert plan.complete is False


# --------------------------------------------------------------------------
# A stretch no waypoint can help
# --------------------------------------------------------------------------

def test_a_stretch_that_reproduces_nowhere_is_recorded_as_a_divergence():
    """The optimal route is optimal in the weighted graph, not the fast one.

    So it may use a segment lying on no fastest path of its own. Raising on that
    fails a whole journey over one segment; retrying on it does not terminate.
    """
    base = Graph(node_ids=NODES)
    # Every leg from position 0 fails, so nothing can be reached from the origin.
    fast_legs = {(0, b): detour_from(base, 0, b) for b in range(1, 20)}
    graph = Graph(node_ids=NODES, fast_legs=fast_legs)

    plan, _routers = search(graph)

    assert plan.divergences, "no divergence was recorded"
    assert plan.divergences[0].from_index == 0
    assert plan.divergences[0].to_index == 1
    assert plan.complete is False


def test_the_search_continues_past_a_divergence_to_the_destination():
    base = Graph(node_ids=NODES)
    fast_legs = {(0, b): detour_from(base, 0, b) for b in range(1, 20)}
    graph = Graph(node_ids=NODES, fast_legs=fast_legs)

    plan, routers = search(graph)

    # From position 1 onwards nothing is declared, so the rest reproduces and
    # the walk reaches the end.
    assert (1, 19) in routers.legs_asked, (
        f"the search did not carry on past the divergence; asked {routers.legs_asked}"
    )


def test_no_leg_is_requested_twice():
    """A retry from the origin re-issues every request already made.

    That is what the search this replaces did on failure, and against a ten
    second budget it is what turned a hard route into an error.
    """
    base = Graph(node_ids=NODES)
    fast_legs = {(0, b): detour_from(base, 0, b) for b in range(1, 20)}
    fast_legs.update({(1, b): detour_from(base, 1, b) for b in range(10, 20)})
    graph = Graph(node_ids=NODES, fast_legs=fast_legs)

    _plan, routers = search(graph)

    assert len(routers.legs_asked) == len(set(routers.legs_asked)), (
        f"a leg was requested more than once: {routers.legs_asked}"
    )


def test_nothing_raises_when_no_position_can_be_snapped():
    """A waypoint is needed and no position can be snapped to serve as one.

    The route itself is unaffected — it is still returned — but the link cannot
    be made faithful, and the answer has to say so rather than raise.
    """
    base = Graph(node_ids=NODES)
    graph = Graph(
        node_ids=NODES,
        fast_legs={(0, 19): detour_from(base, 0, 19)},
        unsnappable=set(range(1, 19)),
    )

    plan, _routers = search(graph)

    assert plan.locations == []
    assert plan.complete is False


def test_unsnappable_positions_alone_do_not_spoil_a_route_that_needs_nothing():
    """No waypoint is needed, so no position has to be snapped for one."""
    graph = Graph(node_ids=NODES, unsnappable=set(range(1, 19)))

    plan, _routers = search(graph)

    assert plan.locations == []
    assert plan.complete is True
