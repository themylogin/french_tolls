# -*- coding=utf-8 -*-
"""Reducing the optimal route to the waypoints a fastest-path router (e.g.
Google Maps) needs.
"""
from dataclasses import dataclass, field
import logging

from .osrm import BudgetExhausted, NoRoute, Route, Routers, Snap

logger = logging.getLogger(__name__)

__all__ = ["Divergence", "WaypointPlan", "plan_waypoints"]

# The most intermediate waypoints a Google Maps directions URL carries.
MAX_WAYPOINTS = 9


@dataclass(frozen=True)
class Divergence:
    """A stretch no waypoint can make a fastest-path router follow."""

    from_index: int
    to_index: int
    from_location: tuple[float, float]
    to_location: tuple[float, float]


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
    """Does the fastest route from position `a` to position `b` follow `optimal`?"""
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
    """Snap a position's coordinate with no hint, caching the result."""
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
    does. Where the router breaks a tie in favour of an equally fast alternative,
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
        """Does the leg from the anchor to `index` reproduce the optimal route?"""
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
                # Nothing from here to the destination reproduces the optimal route.
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
                # handed to a router.
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

    except BudgetExhausted:
        # Return what has been verified. A partial list of verified waypoints is
        # worth more to a driver than an error, and every one of them was
        # checked on the leg the driver drives.
        plan.complete = False
        plan.truncated_by = plan.truncated_by or "budget"

    return plan


async def _emittable_at_or_before(routers: Routers, optimal: Route, index: int, anchor: int,
                                  snaps: dict[int, Snap], origin: Snap, destination: Snap,
                                  on_route: set[int]):
    """The furthest position at or before `index`, above `anchor`, usable as a waypoint."""
    for candidate in range(index, anchor, -1):
        snap = await _snap_position(routers, optimal, candidate, snaps, origin, destination)
        if snap is not None and _is_emittable(snap, on_route):
            return candidate, snap

    return None


async def _furthest_reach(works, anchor: int, last: int):
    """The furthest position from `anchor` whose leg reproduces the optimal route.

    Returns `(index, snap)`, or None when nothing between the anchor and the destination
    reproduces the route.
    """
    # Where the whole remainder reproduces the optimal route, no waypoint is
    # needed at all and one request settles it.
    snap = await works(last)
    if snap is not None:
        return last, snap

    # Grow: 1, 2, 4, 8, ...
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
        # Nothing from here to the destination reproduces the optimal route.
        return None

    # Bisect between the furthest success and the first failure.
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
