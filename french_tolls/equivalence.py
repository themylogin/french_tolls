# -*- coding=utf-8 -*-
import logging
import math

import numpy as np

from .geometry import project
from .osrm import BudgetExhausted, NoRoute, RouterUnavailable
from .tolls import booths_crossed

logger = logging.getLogger(__name__)

__all__ = ["booths_of", "matched_nodes", "optimize"]


def optimize(coordinates, spacing_m=250.0):
    """Keep one point every `spacing_m`, drop the rest, keep both ends.

    A Google route carries far too many points -- 30 000 on average, about 15 m
    apart even where the motorway runs straight -- and OSRM cannot match one. It
    refuses a trace that long, and one in five of the short ones it does accept
    comes back in pieces (because points that crowded make it lose the road in
    the middle). So points have to go.

    250 m is what the measurement chose. All 2 450 Google routes we have stored,
    matched at each spacing, booths compared against the 100 m answer:

                                                                 passed through
        spacing   points   matched whole   in pieces   too big      same booths
              0    30448        123/2450          33      2294          123/123
            100     4693       2025/2450         401        24        2025/2025
            250     2034       2314/2450         136         0        2024/2025
            500     1045       2390/2450          60         0        1988/1998
           1000      526       2276/2450         174         0        1888/1905

    Denser is not safer. 100 m breaks into pieces three times as often as 250 m.
    Coarser is not either. 500 m breaks least of all, and pays for it: ten of its
    routes cross different booths from the 100 m answer, against one of 250 m's.

    Dropping points bends the line, and that is fine. The points are a hint about
    where the driver went. The matcher puts each one back on a road and drives
    the real road between them, so a cut corner comes back.

    Douglas-Peucker is the wrong tool. It would leave two points on 40 km of
    straight motorway, and the matcher is then free to fill that stretch with the
    toll-free road beside it. What has to be bounded here is the gap between the
    points, not how far the line strays from the road.

    Distances are read in the projection `geometry` works in, not off a sphere.
    That is the more accurate of the two -- 0.0007% against 0.22% -- but accuracy
    is not why: at a 250 m spacing the sphere's error is half a metre and no
    matcher notices. It is so that one distance model decides every measure in
    this project, and there is no second constant to drift.
    """
    if len(coordinates) < 3 or spacing_m <= 0:
        return [tuple(c) for c in coordinates]

    # (longitude, latitude) -> (latitude, longitude)
    xy = project(np.asarray(coordinates, dtype=float)[:, ::-1])

    # How far along the trace each point is
    along = np.concatenate([[0.0], np.cumsum(np.hypot(*(xy[1:] - xy[:-1]).T))])

    # `along` only ever increases, so it can be binary-searched, and
    # `searchsorted` does that for every point in one call: `reach[i]` is the
    # first point that is `spacing_m` further *along the trace* than point i.
    reach = np.searchsorted(along, along + spacing_m, side="left").tolist()

    # Back to plain lists. The walk reads one coordinate at a time, and each
    # read from a numpy table builds a small object, where a list just hands
    # over the float.
    xs, ys = xy[:, 0].tolist(), xy[:, 1].tolist()

    last, keep = 0, [0]
    end = len(coordinates) - 1
    while True:
        i = reach[last]
        x0, y0 = xs[last], ys[last]
        while i < end and math.hypot(xs[i] - x0, ys[i] - y0) < spacing_m:
            i += 1
        if i >= end:
            break
        keep.append(i)
        last = i

    keep.append(end)
    return [tuple(coordinates[i]) for i in keep]


async def matched_nodes(routers, coordinates):
    """The OSM nodes a foreign geometry runs over, or None where that is unknown.

    `coordinates` are `[longitude, latitude]`, as the routers speak.
    """
    trace = optimize(coordinates)
    if len(trace) < 2:
        return None

    try:
        match = await routers.match(trace)
    except (NoRoute, RouterUnavailable, BudgetExhausted) as e:
        logger.info("could not match a %d-point trace: %s", len(trace), e)
        return None

    if not match.whole:
        # The matcher lost the road and started again.
        logger.info("a %d-point trace matched in %d pieces", len(trace), match.pieces)
        return None

    return match.node_ids


async def booths_of(routers, data, coordinates):
    """Which booths a foreign geometry crosses, or None where that is unknown."""
    nodes = await matched_nodes(routers, coordinates)
    return None if nodes is None else booths_crossed(data, nodes)
