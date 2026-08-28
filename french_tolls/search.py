# -*- coding=utf-8 -*-
"""Reducing the optimal route to the waypoints a fastest-path router needs.

A general-purpose navigation application computes the fastest route between the
points it is given. The optimal route is not the fastest one, so handing it only
an origin and a destination sends the driver down the expensive road. The job
here is to find the fewest intermediate points such that, for every consecutive
pair, the fastest route between them *is* the optimal route between them.

The untouched graph stands in for that navigation application. That is the
honest contract, and it is what the tests can measure: a leg verified here is
the fastest route on this project's own graph, not a promise about what any
particular third party will drive.
"""
from dataclasses import dataclass, field
import logging

from .osrm import BudgetExhausted, NoRoute, Route, Routers, Snap

logger = logging.getLogger(__name__)

__all__ = ["Divergence", "WaypointPlan", "plan_waypoints"]

# The most intermediate waypoints a Google Maps directions URL carries. Beyond
# it Maps drops the surplus without saying so, which is worse than a link that
# admits it is partial.
MAX_WAYPOINTS = 9


@dataclass(frozen=True)
class Divergence:
    """A stretch no waypoint can make a fastest-path router follow.

    The optimal route is optimal in the toll-weighted graph, so it may use a
    segment that lies on no fastest path between its own endpoints. That is a
    fact about the two graphs rather than an error: raising on it fails a whole
    journey over one segment, and retrying on it does not terminate.
    """

    from_index: int
    to_index: int
    from_location: tuple[float, float]
    to_location: tuple[float, float]

    def as_dict(self):
        return {
            "from": list(self.from_location),
            "to": list(self.to_location),
        }


@dataclass
class WaypointPlan:
    """The waypoints to put in a link, and how faithful that link is."""

    # Positions on the optimal route, in driven order, excluding the endpoints.
    indices: list[int] = field(default_factory=list)
    locations: list[tuple[float, float]] = field(default_factory=list)
    # How many the optimal route actually needed. May exceed len(locations) when
    # the cap or the budget cut the search short.
    needed: int = 0
    # False when the link does not reproduce the optimal route in full.
    complete: bool = True
    divergences: list[Divergence] = field(default_factory=list)
    # Why the plan is incomplete, where it is: "cap", "budget", or None.
    truncated_by: str | None = None


async def _reproduces(routers: Routers, optimal: Route, a: int, b: int,
                      start: Snap, end: Snap) -> bool:
    """Does the fastest route from position `a` to position `b` follow `optimal`?

    Equality is of the whole node sequence. A leg that leaves the optimal route
    and rejoins it before `b` drives a road the optimal route does not, and the
    driver pays for that road.

    One node at each end is bookkeeping rather than road. A coordinate taken from
    the optimal route's geometry snaps onto a segment, and the router's
    annotation then carries that segment's *other* end as well -- measured on the
    France graph, a leg from position i comes back as `(optimal[i - 1],) +
    optimal[i:b + 1]`. So a leading node equal to `optimal[a - 1]` and a trailing
    node equal to `optimal[b + 1]` are stripped before comparing.

    The tolerance cannot hide a detour. The only nodes it forgives are the
    endpoints' immediate neighbours *on the optimal route itself*; a leg that
    drove any other road differs in its interior and still fails.
    """
    try:
        leg = await routers.fast(start, end)
    except NoRoute:
        return False

    want = optimal.node_ids[a:b + 1]
    got = leg.node_ids

    if a > 0 and got and got[0] == optimal.node_ids[a - 1]:
        got = got[1:]
    if b + 1 < len(optimal) and got and got[-1] == optimal.node_ids[b + 1]:
        got = got[:-1]

    return got == want


def _snap_at(optimal: Route, index: int, snaps: dict[int, Snap],
             origin: Snap, destination: Snap) -> Snap | None:
    """The cached snap for a position, if one has been taken."""
    if index == 0:
        return origin
    if index == len(optimal) - 1:
        return destination
    return snaps.get(index)


async def _snap_position(routers: Routers, optimal: Route, index: int,
                         snaps: dict[int, Snap], origin: Snap, destination: Snap) -> Snap | None:
    """Snap a position's coordinate with no hint, caching the result.

    Snapping only. Whether the position may be *emitted* is a separate question,
    answered by `_is_emittable` against the snap this returns. Keeping the two
    apart is what stops a cached snap taken for one purpose from being handed out
    for the other without being checked.
    """
    cached = _snap_at(optimal, index, snaps, origin, destination)
    if cached is not None:
        return cached

    try:
        snap = await routers.snap(optimal.coordinates[index], reach_m=float("inf"))
    except NoRoute:
        return None

    snaps[index] = snap
    return snap


def _is_emittable(snap: Snap, on_route: set[int]) -> bool:
    """May this snap be handed to a router as a waypoint?

    A waypoint is given to a router that has only the coordinate. Where the
    optimal route runs beside another road within the snapping distance -- the
    opposite carriageway, a parallel service road, a slip road -- a bare
    coordinate can land on the wrong one, and the router then drives somewhere
    else entirely. Pinning the leg with a hint hides that, because the hint names
    the carriageway the coordinate alone does not.

    `nodes` are the two ends of the segment the coordinate landed on. Both being
    on the route is what says the coordinate did not cross to a neighbour.
    """
    return bool(snap.nodes) and all(n in on_route for n in snap.nodes)


async def plan_waypoints(routers: Routers, optimal: Route, origin: Snap,
                         destination: Snap, *, max_waypoints: int = MAX_WAYPOINTS) -> WaypointPlan:
    """Find the fewest waypoints that make the fast graph drive the optimal route.

    Greedy from the origin. From the current anchor, find the furthest position
    whose leg from that anchor reproduces the optimal route, emit it, and take it
    as the next anchor.

    The furthest position is found by growing the offset -- one node, two, four,
    doubling -- until a leg fails, then bisecting the last bracket. Growing
    before bisecting costs a number of requests proportional to the logarithm of
    the step actually taken rather than of the whole route's length.

    This relies on a prefix of a fastest path being a fastest path, so that a
    leg reproducing the route implies every shorter leg from the same anchor
    does. Where the router breaks a tie in favour of an equally fast alternative
    the growth stops early; that costs one extra waypoint and never costs
    correctness, because every emitted waypoint is one whose own leg came back
    equal.
    """
    plan = WaypointPlan()
    last = len(optimal) - 1
    if last <= 0:
        return plan

    on_route = set(optimal.node_ids)
    snaps: dict[int, Snap] = {}
    anchor = 0
    anchor_snap = origin

    async def snap_for_leg(index):
        return await _snap_position(routers, optimal, index, snaps, origin, destination)

    async def reaches(index):
        """Does the leg from the anchor to `index` reproduce the optimal route?

        Deliberately does not ask whether `index` could be handed to a router as
        a waypoint. Those are two different questions, and letting the second
        stop the search makes it emit waypoints for a journey whose two routes
        are already the same road.
        """
        snap = await snap_for_leg(index)
        if snap is None:
            return None
        if not await _reproduces(routers, optimal, anchor, index, anchor_snap, snap):
            return None
        return snap

    try:
        while anchor < last:
            reach = await _furthest_reach(reaches, anchor, last)

            if reach is None:
                # Nothing from here to the destination reproduces the optimal
                # route. Step over one position and say so, rather than raising
                # or retrying: a retry from the origin re-issues every request
                # already made and does not terminate.
                plan.divergences.append(Divergence(
                    from_index=anchor,
                    to_index=anchor + 1,
                    from_location=optimal.coordinates[anchor],
                    to_location=optimal.coordinates[anchor + 1],
                ))
                plan.complete = False
                anchor += 1
                anchor_snap = await snap_for_leg(anchor)
                if anchor_snap is None:
                    # Nothing to route the next leg from. Keep what is verified.
                    plan.complete = False
                    break
                continue

            index, snap = reach
            if index == last:
                break

            # The leg is verified. Now the position has to be one a router can
            # be handed: it must snap back onto the optimal route from the bare
            # coordinate. Where it does not, fall back towards the anchor.
            emit = await _emittable_at_or_before(
                routers, optimal, index, anchor, snaps, origin, destination, on_route
            )

            if emit is None:
                # No position between the anchor and the furthest reach can be
                # handed to a router. Carry on from the furthest reach so the
                # walk terminates, and say the link is not faithful.
                logger.info("no emittable waypoint between %d and %d", anchor, index)
                plan.complete = False
                anchor, anchor_snap = index, snap
                continue

            emit_index, emit_snap = emit
            if emit_index != index:
                # A different position from the one whose leg was verified, so
                # its own leg is verified too. A prefix of a fastest path is a
                # fastest path, so this is expected to pass; it is asked because
                # "every emitted waypoint's leg was checked" is the one property
                # that makes the answer correct rather than plausible.
                if not await _reproduces(
                    routers, optimal, anchor, emit_index, anchor_snap, emit_snap
                ):
                    plan.complete = False
                    anchor, anchor_snap = index, snap
                    continue

            anchor, anchor_snap = emit_index, emit_snap

            plan.needed += 1
            if len(plan.indices) < max_waypoints:
                plan.indices.append(emit_index)
                plan.locations.append(optimal.coordinates[emit_index])
            else:
                # Past the cap the search keeps going, purely to report how many
                # the route really needed. The link itself cannot carry them.
                plan.complete = False
                plan.truncated_by = "cap"

    except BudgetExhausted as e:
        # Return what has been verified. A partial list of verified waypoints is
        # worth more to a driver than an error, and every one of them was
        # checked on the leg the driver drives.
        logger.info("waypoint search stopped on budget: %s", e)
        plan.complete = False
        plan.truncated_by = plan.truncated_by or "budget"

    return plan


async def _emittable_at_or_before(routers: Routers, optimal: Route, index: int, anchor: int,
                                  snaps: dict[int, Snap], origin: Snap, destination: Snap,
                                  on_route: set[int]):
    """The furthest position at or before `index`, above `anchor`, usable as a waypoint.

    Walks back one position at a time. Measured on the France graph most
    positions pass on the first try, and the query budget bounds the walk where
    they do not.
    """
    for candidate in range(index, anchor, -1):
        snap = await _snap_position(routers, optimal, candidate, snaps, origin, destination)
        if snap is not None and _is_emittable(snap, on_route):
            return candidate, snap

    return None


async def _furthest_reach(works, anchor: int, last: int):
    """The furthest position from `anchor` whose leg reproduces the optimal route.

    `works(index)` returns that position's snap, or None. Returns
    `(index, snap)`, or None when nothing between the anchor and the destination
    reproduces the route.
    """
    # The destination first. The search is greedy for the furthest reach, and the
    # furthest possible reach is the end: where the whole remainder reproduces
    # the optimal route, no waypoint is needed at all and one request settles it.
    #
    # Probing it first is not only cheaper. Growing from the anchor upwards, the
    # legs at offsets 1 and 2 come back one node longer than the optimal slice --
    # the router snaps the far end onto a segment and the annotation carries that
    # segment's other node -- while every offset from 5 up matches exactly. That
    # short-range miss would end the growth and put a spurious waypoint a few
    # metres into a journey whose two routes are the same road.
    snap = await works(last)
    if snap is not None:
        return last, snap

    # Grow: 1, 2, 4, 8, ...
    #
    # Growth stops at the first failure *that follows a success*, not at the
    # first failure outright, for the same short-range reason.
    best = None
    step = 1
    lo_fail = None
    while True:
        index = min(anchor + step, last)
        if index == last:
            # Already probed above, and it failed.
            break

        snap = await works(index)
        if snap is not None:
            best = (index, snap)
        elif best is not None:
            lo_fail = index
            break

        step *= 2

    if best is None:
        # Nothing from here to the destination reproduces the optimal route. That
        # is a genuine divergence: the optimal route is optimal in the weighted
        # graph, so it may use a segment lying on no fastest path of its own.
        return None

    # Bisect between the furthest success and the first failure. Where the growth
    # ran off the end without a failure above it, the destination is the bound --
    # it was probed first and did not reproduce.
    lo = best[0]
    hi = lo_fail if lo_fail is not None else last
    while hi - lo > 1:
        mid = (lo + hi) // 2
        snap = await works(mid)
        if snap is None:
            hi = mid
        else:
            lo = mid
            best = (mid, snap)

    return best
