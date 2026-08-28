# -*- coding=utf-8 -*-
"""A routing graph written out in a test, and a stub that answers from it.

For the waypoint search, a hand-built graph is not a weaker substitute for
France; it is a stronger one. The cases that decide whether the search is right
-- a position whose bare coordinate lands on a parallel carriageway, a stretch
that lies on no fastest path, a leg that leaves the optimal route and rejoins it
-- can be written down here. In the real extract they have to be hunted for, and
they move whenever the graph is rebuilt.

A graph is three things:

- the optimal route, as a sequence of node ids;
- the legs on which the fast graph *differs* from it, named by their two
  positions. Every leg not named answers with the optimal slice, so a test
  writes down only what is supposed to be different;
- the positions whose bare coordinate snaps onto something the optimal route
  does not drive.
"""
from dataclasses import dataclass, field

from ..osrm import BudgetExhausted, NoRoute, Route, Snap

__all__ = ["FakeRouters", "Graph", "leg_rejoining", "leg_with_extra_node"]

# One coordinate per position, spaced far enough apart that no two compare equal
# and near enough that they read as one road.
def _coordinate(position):
    return (4.0 + position / 10000.0, 45.0 + position / 10000.0)


@dataclass
class Graph:
    """The optimal route, and how the fast graph disagrees with it."""

    # The optimal route's node ids, in driven order. Position i is index i.
    node_ids: list[int]

    # (from position, to position) -> the node id sequence the fast graph
    # returns for that leg. A pair absent from here answers with the optimal
    # slice, meaning the fast graph agrees over that stretch.
    fast_legs: dict[tuple[int, int], list[int]] = field(default_factory=dict)

    # Positions whose bare coordinate snaps onto a segment the optimal route
    # does not drive -- the opposite carriageway, a service road, a slip road.
    # A position listed here must never be emitted as a waypoint.
    off_route: set[int] = field(default_factory=set)

    # Positions the router cannot snap at all.
    unsnappable: set[int] = field(default_factory=set)

    # (from position, to position) pairs for which the fast graph has no route.
    no_route: set[tuple[int, int]] = field(default_factory=set)

    @property
    def last(self):
        return len(self.node_ids) - 1

    def coordinate(self, position):
        return _coordinate(position)

    def position_of(self, coordinate):
        """The position a coordinate belongs to.

        The stub is handed coordinates, not positions, so it has to get back.
        Exact rather than nearest: every coordinate it sees came from this
        graph, and a coordinate it does not recognise is a bug in the test.
        """
        for i in range(len(self.node_ids)):
            if _coordinate(i) == tuple(coordinate):
                return i
        raise AssertionError(f"{coordinate} is not a coordinate of this graph")

    def optimal_route(self):
        """The optimal route as the search reads one."""
        return _route(self.node_ids, [_coordinate(i) for i in range(len(self.node_ids))])

    def leg(self, a, b):
        """The node ids the fast graph returns between two positions."""
        if (a, b) in self.no_route:
            raise NoRoute(f"no route from {a} to {b}")

        declared = self.fast_legs.get((a, b))
        return list(declared) if declared is not None else self.node_ids[a:b + 1]


def _route(node_ids, coordinates):
    n = len(node_ids)
    return Route(
        node_ids=tuple(node_ids),
        coordinates=tuple(tuple(c) for c in coordinates),
        # One metre and one second per segment. Nothing in the waypoint search
        # reads them; they are here so the shape is the shape the real client
        # returns, and a search that started reading them would not silently
        # get zeros.
        segment_distance=tuple(1.0 for _ in range(n - 1)),
        segment_duration=tuple(1.0 for _ in range(n - 1)),
        distance=float(n - 1),
        duration=float(n - 1),
        weight=float(n - 1),
    )


def leg_with_extra_node(graph, a, b, *, leading=None, trailing=None):
    """The optimal slice with an extra node at one end.

    The real router does this: a coordinate snaps onto a *segment*, and the
    annotation then carries that segment's other end as well. `_reproduces`
    forgives exactly one such node at each end, and only when it is the
    endpoint's neighbour on the optimal route itself. This builds both the leg
    that must be forgiven and the leg that must not.
    """
    out = list(graph.node_ids[a:b + 1])
    if leading is not None:
        out.insert(0, leading)
    if trailing is not None:
        out.append(trailing)
    return out


def leg_rejoining(graph, a, b, *, at, detour):
    """A leg that leaves the optimal route and rejoins it before the far end.

    Its two ends match, and so does everything outside the detour, which is what
    makes it the case a comparison of endpoints alone would wave through.
    """
    out = list(graph.node_ids[a:b + 1])
    out[at - a:at - a + 1] = detour
    return out


class FakeRouters:
    """Answers the two questions the waypoint search asks, from a `Graph`.

    It answers routing questions and nothing else. What the search does with the
    answers is what the tests are measuring, so nothing here reimplements any
    part of the search.
    """

    def __init__(self, graph, budget=1000):
        self.graph = graph
        self.budget = budget
        self.requests = 0
        # Every leg asked for, in order, so a test can assert that a waypoint's
        # own leg was verified and that no leg was requested twice.
        self.legs_asked = []
        self.snaps_asked = []

    @property
    def exhausted(self):
        return self.requests >= self.budget

    def _charge(self):
        """Count one request, and stop at the budget as the real client does."""
        if self.exhausted:
            raise BudgetExhausted(f"{self.requests} requests issued, budget is {self.budget}")
        self.requests += 1

    async def snap(self, location, *, reach_m=None):
        self._charge()
        position = self.graph.position_of(location)
        self.snaps_asked.append(position)

        if position in self.graph.unsnappable:
            raise NoRoute(f"position {position} cannot be snapped")

        if position in self.graph.off_route:
            # The coordinate landed on a road the optimal route does not drive.
            # `nodes` are the two ends of that segment, and neither is on the
            # route, which is what makes the position unusable as a waypoint.
            nodes = (-position, -position - 1)
        else:
            neighbour = position + 1 if position < self.graph.last else position - 1
            nodes = (self.graph.node_ids[position], self.graph.node_ids[neighbour])

        return Snap(
            location=self.graph.coordinate(position),
            hint=f"hint-{position}",
            nodes=nodes,
            distance_m=0.0,
        )

    async def fast(self, start, end):
        self._charge()
        a = self.graph.position_of(start.location)
        b = self.graph.position_of(end.location)
        self.legs_asked.append((a, b))

        node_ids = self.graph.leg(a, b)
        return _route(node_ids, [_coordinate(a) for _ in node_ids])

    async def optimal(self, start, end):
        self._charge()
        return self.graph.optimal_route()

    def origin(self):
        """The snap the search is given for position 0."""
        return _snap_of(self.graph, 0)

    def destination(self):
        return _snap_of(self.graph, self.graph.last)


def _snap_of(graph, position):
    neighbour = position + 1 if position < graph.last else position - 1
    return Snap(
        location=graph.coordinate(position),
        hint=f"hint-{position}",
        nodes=(graph.node_ids[position], graph.node_ids[neighbour]),
        distance_m=0.0,
    )
