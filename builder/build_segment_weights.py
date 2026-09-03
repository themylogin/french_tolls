#!/usr/bin/env python3
"""Step 9 -- spread the tariffs over the road segments they pay for.

Step 6 and step 8 leave `data/vinci_price.yaml` holding a tariff for each
entrance/exit pair the operator sells. A tariff names two points and says
nothing about the road between them, and a router knows only edges. So the
price has to be spread over the edges the ticket covers.

    for every priced pair
        route it on the untouched graph                    (local, batched)
        price / route length      -> one EUR/km sample on each segment driven
    per directed segment
        mean of its samples       -> the segment's price per kilometre
        spread of its samples     -> whether the samples agree at all

The output is an OSRM segment speed file. Each row keeps the segment's own
speed, so applying the file leaves its duration exactly as it was, and moves
only the rate:

    weight = osm_weight + segment_price / wage * 3600
    rate   = length / weight

`osrm-customize` inverts that as `weight = length / rate`, so the graph ends up
costing a tolled segment the driver's own time to pay for it. Turn weights are
untouched, so a route's weight rises by exactly the sum of its tolls.

Some booths charge a flat fee for passing one point rather than for a distance
driven. They sell no ticket, so they are in no priced pair and the sampling
above never reaches them. Such a booth carries a `price` and ends no placed
pair, and it is charged on the arcs leaving it instead:

    for every booth carrying a `price` that ends no placed pair
        for every arc whose tail is one of its lane nodes
            measure that arc on the graph
            the booth's whole tariff       -> that arc's own row

The tail is what makes it exact. A row is an oriented pair, so the two senses of
a two-way barrier are two rows that never interfere, and a vehicle can drive an
arc out of the booth only by standing on the booth node. Every lane is charged,
aliases included: a plaza with one lane charged and another free is worse than
one with neither, because the router finds the free lane every time.

The two sources add. A segment that is both sampled and leaves a barrier is
charged both, though measured against the current inputs none is.

The original speed, weight and length come from the router's own annotations on
those same routes rather than from a second reading of the extract: they are the
numbers the graph was built with, and anything derived elsewhere could disagree
with it.

Outputs:
    <--out>        the segment speed file, `from,to,speed_kmh,rate`
    <--report>     every segment and every pair, for the diagnostics
"""

import argparse
import array
import collections
import concurrent.futures
import json
import math
import os
import statistics
import sys
import time

import osmium
import requests
import yaml

import build_vinci_prices as bp
import build_vinci_direct_prices as bd
import osmurl

Abort = bp.Abort
table = bp.table

ENTER, EXIT = bp.ENTER, bp.EXIT
BIDIRECTIONAL, GANTRY = bp.BIDIRECTIONAL, bp.GANTRY

# A booth's role decides which end of a ticket it can be. A `gantry` is both: it
# opens a section when another gantry follows and closes one when it is the one
# that follows, so it appears as a source and as a target.
TARGET_TYPES = (EXIT, BIDIRECTIONAL, GANTRY)

# Where the tolled road begins at an entrance and ends at an exit, as step 9
# records them. A pair is routed between these rather than between the two
# barriers: the barrier is where the ticket is settled, not where the road the
# ticket paid for starts and stops. MERU to AMBLAINVILLE is 1.5 km barrier to
# barrier and 10.0 km between the extents.
FIRST, FIRST_AT, LAST, LAST_AT = bp.TOLL_EXTENT_KEYS

# A pair whose barrier-to-barrier route is this many times the straight line
# between the two barriers is not a journey. Two ramps of one interchange under
# two gare codes are the case: the router loops out and back, crossing no third
# booth, so nothing else rejects them. Measured, the detour ratio is 1.26x at
# the median and 2.09x at the 99th percentile, and then there is nothing until
# 5.6x, 29.7x, 48.3x and 69.1x -- four pairs, and all four are that shape.
#
# The test is on the barrier-to-barrier distance and not on the extent-to-extent
# one. MERU to AMBLAINVILLE is 1.0x barrier to barrier and 6.8x extent to
# extent, because its exit's tolled road runs 8 km past the barrier; testing the
# extent ratio would throw away exactly the pairs the extents exist to fix.
MAX_DETOUR = 5.0

# The fit, and how hard it is held to the means. See fit_rates.
#
# Twelve iterations is where the journey error stops moving. Lambda was swept:
#
#   lambda   median   p90    within10   max rate   >1 EUR/km   near 0
#   means      8.5%  23.2%     56.7%     0.5355        0          0
#        0     3.1%  11.3%     87.9%     7.9412      587       1909
#        1     3.3%  11.8%     86.8%     1.5786       29         10
#        2     3.3%  12.3%     86.0%     0.7612        0          0
#        5     3.5%  13.1%     84.4%     0.5386        0          0
#       10     3.7%  14.0%     82.8%     0.5372        0          0
#      250     6.1%  18.7%     71.3%     0.5356        0          0
#
# Five is the knee. It takes the median journey error from 8.5% to 3.5%, most
# of the 3.1% an unconstrained fit reaches, and leaves the highest rate at
# 0.5386 against the means' own highest of 0.5355 -- so no segment is priced
# outside the range some real journey actually paid. Below five that guarantee
# goes: at one, 29 segments exceed 1 EUR/km and ten fall to nothing.
FIT_ITERATIONS = 12
FIT_LAMBDA = 5.0

EARTH_KM = 6371.0

ROUTE_WORKERS = 16          # measured in step 8: throughput plateaus here
PROGRESS_EVERY = 25         # source booths

# The annotations the whole step is built on. `nodes` gives the segment identity
# the CSV keys on; the other three give the numbers the graph was built with.
ANNOTATIONS = "nodes,distance,duration,weight"

# The grid a weight is stored on. `osrm-customize` computes
# `round(length / rate * WEIGHT_MULTIPLIER)` and keeps that integer, so the graph
# holds no distinction finer than one over it, and the API reports a weight
# already divided by it.
#
# Ten, because the profile sets no `weight_precision` and OSRM's default is 1.
# Taken from the graph rather than trusted: over one run's report, all 249 448
# sampled segments and all 333 barrier arcs carry a weight that is an exact
# multiple of 0.1, and not one has a second decimal.
#
# Not parsed out of the profile at run time. `write_csv` has no business reading
# Lua, and a wrong value here does not pass quietly -- it snaps every target onto
# the wrong grid, which moves every arc's weight, which is the quantity
# `check_arcs` holds to 0.01 EUR.
WEIGHT_MULTIPLIER = 10

# How many rows of each findings table are printed. The full record always goes
# to the report file, so a cap costs nothing but the scrolling.
TABLE_ROWS = 40

# The pair the acceptance check uses. Fixed here rather than passed in: a graph
# built wrongly has to be caught where it is built, and a check whose subject is
# an argument is a check that can be pointed away from the failure.
CHECK_SOURCE = 36967365          # LE PERTHUS
CHECK_TARGET = 1676618837        # BEZIERS-OUEST
CHECK_TARIFF_EUR = 14.50

# The arithmetic of a flat charge is exact -- the whole tariff goes onto one arc
# rather than being reconstructed from means -- so the arc check is held far
# tighter than the pair check above. Anything outside this is a fault in the
# file or in the graph, not in the pricing.
ARC_TOLERANCE = 0.01

# How a booth's own arc is measured. Both ends of the arc are real OSM nodes
# with exact positions, so a route between them with the snapping radius held to
# a couple of metres can land on nothing else, and one call settles the arc.
# Where that fails the arc is measured again from a route that drives past it,
# with the two ends placed by dead reckoning along the arc's own bearing.
# Measured over 288 arcs: the first returns 287, the second 257, and over the
# 256 both return they agree to 0.000 m, 0.000 s and 0.000 weight.
ARC_RADII = (2.0, 6.0, 15.0)
ARC_STANDOFFS = (150.0, 400.0, 60.0, 1000.0)

# A measured arc whose routed length disagrees with the distance between its own
# two nodes by more than this did not measure the arc. The bound is the larger
# of the two: a metre, or a share of the arc's own length.
#
# The share is what a bend costs. A road curves between its nodes, so the routed
# length exceeds the chord in proportion to the length rather than by a fixed
# amount, and an absolute metre is a bound only a short arc can meet. A barrier
# sits in a plaza where the next node is 18 m away at the median; a free-flow
# point sits on open motorway where it can be half a kilometre. Measured over
# the 44 arcs of the booths this step gained, the disagreement is 0.07 m at the
# median and 1.53 m at the worst, which is 0.4874% of its own arc.
#
# The floor keeps a short arc held as tightly as it was: at the shortest arc in
# the inventory, 1.3 m, one per cent is 13 mm.
ARC_LENGTH_TOLERANCE_M = 1.0
ARC_LENGTH_TOLERANCE_FRACTION = 0.01


def stop(kind, message):
    """An Abort the survey can file under a heading."""
    exc = Abort(message)
    exc.kind = kind
    return exc


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

def load_gares(path):
    """group -> (gare code, the operator's own name for it)."""
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    out = {}
    for group, entry in (doc.get("toll_booths") or {}).items():
        out[int(group)] = (str((entry or {}).get("id") or ""),
                           str((entry or {}).get("name") or ""))
    return out


def flat_charges(priced, ends_pair):
    """(group -> tariff in euros, the tally), for the booths that charge at a point.

    Two clauses, and neither is a test on the entry's `type`. That field names
    the hardware and not the charge: `gantry` comes from the OSM tag
    `highway=toll_gantry` and covers a ticketless entrance that takes no money,
    a point that opens and closes priced sections, and a point that charges a
    fixed amount for passing it. `bidirectional` names a lane a vehicle can
    drive either way, which says nothing about what it charges.

    Carrying a `price` says the operator charges for the passage itself: step 8
    records one only for a passage the service returned with no exit attached.

    Ending no placed pair says the passage is not already paid for. A booth that
    is the entrance or the exit of a priced pair has its tariff spread over that
    pair's route, and a flat row for it would charge the same passage twice.

    `ends_pair` comes from the pairs that produced samples, not from every pair
    enumerated. A pair rejected as unusable put its tariff on no segment, so its
    booths are not paid for by it and stay eligible here.

    There is deliberately no third clause refusing a group whose arc already
    carries a sample. It could fire on nothing -- `blockers_of` rejects a pair
    whose route crosses a third booth, so an arc leaving a booth is sampled only
    when that booth is one of the pair's own ends, and such a booth fails the
    second clause already. It would also contradict the rule that a flat charge
    and a per-kilometre rate add on the same segment, by dropping the tariff
    where that rule says to charge both.
    """
    charges, tally = {}, collections.Counter()
    for group, record in priced.items():
        if not record.get("price"):
            tally["carry no price"] += 1
            continue
        if group in ends_pair:
            tally["end a placed pair"] += 1
            continue
        charges[group] = record["price"] / 100.0
        tally["charge at a point"] += 1
    return charges, tally


def load_arcs(path, groups):
    """group -> [(tail, head, tail position, head position)], from the inventory.

    The arcs come from `onward_nodes`, which names the node a vehicle reaches
    after passing each lane node in each direction it can leave by. Which arc
    leaves a booth is a fact about the road network, and the inventory is where
    this pipeline records those; working it out again here would mean a second
    pass over the plaza neighbourhoods for a question step 3 has answered.

    Every lane of the plaza is taken, aliases included. A plaza where one lane
    carries the charge and another does not is worse than one where neither
    does: the router finds the free lane and takes it every time.
    """
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    booths = doc.get("toll_booths") or {}
    aliases = doc.get("aliases") or {}
    lanes = collections.defaultdict(list)
    for node, entry in booths.items():
        lanes[int(node)].append((int(node), entry or {}))
    for node, entry in aliases.items():
        lanes[int((entry or {})["parent_id"])].append((int(node), entry or {}))

    out, missing = {}, []
    for group in sorted(groups):
        arcs = []
        for node, entry in sorted(lanes.get(group, ()), key=lambda x: x[0]):
            onward = entry.get("onward_nodes")
            if not onward:
                missing.append(node)
                continue
            tail_at = tuple(entry["latlon"])
            for head, latlon in sorted(onward.items()):
                arcs.append((node, int(head), tail_at, tuple(latlon)))
        if not arcs:
            missing.append(group)
        out[group] = arcs
    if missing:
        missing = sorted(set(missing))
        raise stop("inventory", (
            f"{len(missing)} booth(s) that charge at a point carry no"
            f" `onward_nodes` in {path}: {missing[:5]}\n"
            f"       Without it this step cannot say which segment the booth"
            f" charges for, and the file it wrote would price every barrier at"
            f" nothing -- which reads exactly like a file with no barriers in"
            f" it. Regenerate the inventory with step 3."))
    return out


def enumerate_pairs(priced, gares):
    """[(source, gare code, cents, (candidate targets, ...))], and the counts.

    A price row names a gare, and a gare can be carried by more than one booth
    group -- the two directions of one plaza, usually. Both are candidates here;
    which one the tariff describes is settled by routing, because the one the
    ticket is for is the one a vehicle reaches without passing a third booth.
    """
    by_code = collections.defaultdict(list)
    for group, (code, _name) in gares.items():
        if priced.get(group, {}).get("type") in TARGET_TYPES:
            by_code[code].append(group)

    pairs, rows, unresolved = [], 0, []
    for src in sorted(priced):
        for code in sorted(priced[src].get("prices") or {}):
            rows += 1
            cents = priced[src]["prices"][code]
            targets = tuple(sorted(g for g in by_code.get(code, ()) if g != src))
            if not targets:
                unresolved.append((src, code))
                continue
            pairs.append((src, code, cents, targets))
    return pairs, rows, unresolved


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

class Router(bd.Router):
    """Step 8's router, asking for the four annotations this step reads.

    Subclassed rather than copied so the session-per-thread handling, the
    readiness wait and its message stay in one place.
    """

    def route(self, a, b, radius=None):
        """(nodes, distance, duration, weight, metres) or None when there is no route.

        `radius` bounds how far each end may snap. Held to a couple of metres it
        is what lets a route between two node positions land on the arc between
        them and on nothing else -- the lanes of a plaza are a median 15 m
        apart, which is near enough for an unbounded snap to pick the wrong one.
        """
        (a_lat, a_lon), (b_lat, b_lon) = a, b
        params = {"annotations": ANNOTATIONS, "overview": "false",
                  "steps": "false"}
        if radius is not None:
            params["radiuses"] = f"{radius};{radius}"
        try:
            resp = self._session().get(
                f"{self.base_url}/route/v1/driving/"
                f"{a_lon},{a_lat};{b_lon},{b_lat}",
                params=params,
                timeout=120,
            )
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if payload.get("code") != "Ok" or not payload.get("routes"):
            return None
        found = payload["routes"][0]
        nodes, dist, dur, weight = [], [], [], []
        for leg in found["legs"]:
            ann = leg.get("annotation") or {}
            nodes.extend(ann.get("nodes") or [])
            dist.extend(ann.get("distance") or [])
            dur.extend(ann.get("duration") or [])
            weight.extend(ann.get("weight") or [])
        if len(dist) != len(nodes) - 1:
            raise Abort(
                f"the router returned {len(nodes)} nodes and {len(dist)} segment"
                f" annotations; this step needs one annotation per node pair.\n"
                f"       Was it asked for {ANNOTATIONS}?")
        return nodes, dist, dur, weight, found["distance"]


# --------------------------------------------------------------------------
# The segment table
# --------------------------------------------------------------------------

class Segments:
    """Per directed segment: its samples, and the graph's own numbers for it.

    Parallel arrays behind one index rather than a dict of records. There are a
    few hundred thousand segments and twenty million observations of them, and
    the arrays are what keeps that in tens of megabytes instead of gigabytes.

    Samples are reduced by mean, which is what a price per kilometre is asked to
    be. Duration and weight are reduced by *minimum*, which is different and
    deliberate: OSRM folds a turn penalty into the segment before the turn, so
    the same segment reads longer on a route that turns off it than on one that
    runs straight through. A penalty only ever adds, so the smallest reading is
    the one free of it.
    """

    def __init__(self):
        self.index = {}                 # (from, to) -> i
        self.frm = array.array("q")
        self.to = array.array("q")
        self.count = array.array("i")
        self.total = array.array("d")   # sum of samples, for the mean
        self.low = array.array("d")
        self.high = array.array("d")
        self.low_pair = array.array("i")
        self.high_pair = array.array("i")
        self.dist = array.array("d")    # metres, the graph's own
        self.dur = array.array("d")     # seconds, minimum seen
        self.weight = array.array("d")  # weight units, minimum seen

    def __len__(self):
        return len(self.frm)

    def observe(self, frm, to, dist, dur, weight, sample, pair):
        i = self.index.get((frm, to))
        if i is None:
            i = self.index[(frm, to)] = len(self.frm)
            self.frm.append(frm)
            self.to.append(to)
            self.count.append(1)
            self.total.append(sample)
            self.low.append(sample)
            self.high.append(sample)
            self.low_pair.append(pair)
            self.high_pair.append(pair)
            self.dist.append(dist)
            self.dur.append(dur)
            self.weight.append(weight)
            return i
        self.count[i] += 1
        self.total[i] += sample
        if sample < self.low[i]:
            self.low[i] = sample
            self.low_pair[i] = pair
        if sample > self.high[i]:
            self.high[i] = sample
            self.high_pair[i] = pair
        # The graph's numbers, cleared of whatever turn penalty this reading
        # carried. Distance moves with them: a partial reading is short in all
        # three at once, and taking a short length against a full duration would
        # invent a speed the segment does not have.
        if dur < self.dur[i]:
            self.dur[i] = dur
            self.dist[i] = dist
        if weight < self.weight[i]:
            self.weight[i] = weight
        return i

    def mean(self, i):
        return self.total[i] / self.count[i]

    def deviation(self, i):
        """(high - low) / mean. Zero for a segment nothing disagrees about."""
        mean = self.mean(i)
        if mean <= 0:
            return 0.0
        return (self.high[i] - self.low[i]) / mean


# --------------------------------------------------------------------------
# Which way a segment belongs to
# --------------------------------------------------------------------------

class WayIndex(osmium.SimpleHandler):
    """Segment -> (way id, highway class), for the findings.

    A node pair is what OSRM keys on and what the CSV carries, and it is not
    something anyone can look up. The way id is: it opens in an editor, and its
    class is what tells a reader whether the segment is mainline or a ramp.

    Only the segments already observed are kept, so the index is the size of the
    segment table rather than of France. Both directions are matched, because a
    way carries its nodes in one order and a route may drive either.
    """

    def __init__(self, wanted):
        super().__init__()
        self.wanted = wanted
        self.hit = {}

    def way(self, w):
        highway = w.tags.get("highway")
        if not highway:
            return
        refs = [n.ref for n in w.nodes]
        for a, b in zip(refs, refs[1:]):
            for key in ((a, b), (b, a)):
                if key in self.wanted and key not in self.hit:
                    self.hit[key] = (w.id, highway)


def index_ways(path, segments, extra=()):
    """{(from, to): (way id, highway)} for every observed segment the extract carries."""
    wanted = set(segments.index) | set(extra)
    wanted |= {(b, a) for a, b in wanted}
    handler = WayIndex(wanted)
    handler.apply_file(path)
    return handler.hit


# --------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------

def endpoint(priced, position, group, key, coord_key):
    """(coordinates to route from or to, whether the booth was used instead).

    An end with no recorded extent falls back to the booth's own node, so a
    partially measured inventory still prices every pair.
    """
    entry = priced.get(group) or {}
    if coord_key in entry:
        lat, lon = entry[coord_key]
        return (lat, lon), False
    return position[group], True


def sample_route(segments, answer, price_eur, pair):
    """Record one pair's samples and return the segment indices it drove.

    The first and last segments are dropped. The router snaps each endpoint part
    of the way along a segment and reports the part rather than the whole, so
    their length, duration and weight are a fraction of the segment's own -- and
    for an endpoint that lands exactly on a node, the first is a zero-length
    stub. Either way they are not a measurement of the segment.

    The denominator is the route's full length, including those two. That is the
    distance the driver was charged for.
    """
    nodes, dist, dur, weight, metres = answer
    if metres <= 0:
        return None
    per_km = price_eur / (metres / 1000.0)
    drove = array.array("i")
    for i in range(1, len(dist) - 1):
        idx = segments.observe(nodes[i], nodes[i + 1],
                               dist[i], dur[i], weight[i], per_km, pair)
        drove.append(idx)
    return per_km, drove


# --------------------------------------------------------------------------
# The arc a booth charges for
# --------------------------------------------------------------------------

def arc_in(answer, tail, head, interior=False):
    """(metres, seconds, weight) for one arc of a route, or None.

    `interior` demands the arc be neither the first nor the last segment. Those
    two carry whatever fraction of the segment the endpoint snapped into, so on
    a route that merely drives past the arc they are not a measurement of it.
    On a route snapped to the arc's own two nodes they are the whole arc, which
    is why the tight measurement does not ask for it.
    """
    nodes, dist, dur, weight, _metres = answer
    lo = 1 if interior else 0
    hi = len(dist) - 1 if interior else len(dist)
    for i in range(lo, hi):
        if nodes[i] == tail and nodes[i + 1] == head:
            return dist[i], dur[i], weight[i]
    return None


def measure_arc(router, tail, head, tail_at, head_at):
    """(metres, seconds, weight, how) for one arc, or (None, reason, None, None).

    Two ways of asking, tried in that order. The first routes between the arc's
    own two node positions with the snapping radius held tight, so the router
    has nowhere to go but along the arc. The second drives past the arc from a
    standoff placed by dead reckoning either side and takes the arc out of the
    interior of the annotation.

    Both are checked against the distance between the two nodes. A route that
    came back with some other stretch of road would otherwise be taken for the
    arc, and the whole tariff would land on it.
    """
    want_m = crow_km(tail_at, head_at) * 1000.0
    slack = arc_length_slack(want_m)
    reason = "no route"

    def wrong_length(found):
        if abs(found[0] - want_m) <= slack:
            return None
        return (f"routed {found[0]:.1f} m against {want_m:.1f} m between the"
                f" two nodes, outside the {slack:.1f} m allowed")

    for radius in ARC_RADII:
        answer = router.route(tail_at, head_at, radius=radius)
        if answer is None:
            continue
        found = arc_in(answer, tail, head)
        if found is None:
            reason = "the arc is not on the route between its own ends"
            continue
        off = wrong_length(found)
        if off:
            reason = off
            continue
        return (*found, f"radius {radius:g} m")

    brg = bearing(tail_at, head_at)
    for standoff in ARC_STANDOFFS:
        answer = router.route(along(tail_at, brg + math.pi, standoff),
                              along(head_at, brg, standoff))
        if answer is None:
            continue
        found = arc_in(answer, tail, head, interior=True)
        if found is None:
            reason = "the arc is not inside a route driving past it"
            continue
        off = wrong_length(found)
        if off:
            reason = off
            continue
        return (*found, f"standoff {standoff:g} m")
    return None, reason, None, None


def arc_length_slack(want_m):
    """How far a measured arc may differ from the line between its own nodes."""
    return max(ARC_LENGTH_TOLERANCE_M, ARC_LENGTH_TOLERANCE_FRACTION * want_m)


def measure_flat(router, arcs_by_group, charges, gares, workers):
    """{(tail, head): (metres, seconds, weight, eur, group, how)}.

    Every arc of every group, or the step stops. A group with one lane measured
    and another not is a plaza with a free lane, and the router takes a free
    lane every time -- so a partial answer here is worse than none.
    """
    jobs = [(group, arc) for group, arcs in sorted(arcs_by_group.items())
            for arc in arcs]
    out, failed = {}, []
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        futures = {
            pool.submit(measure_arc, router, tail, head, tail_at, head_at):
                (group, tail, head)
            for group, (tail, head, tail_at, head_at) in jobs}
        for future in concurrent.futures.as_completed(futures):
            group, tail, head = futures[future]
            metres, dur, weight, how = future.result()
            if metres is None:
                failed.append((group, tail, head, dur))
                continue
            out[(tail, head)] = (metres, dur, weight,
                                 charges[group], group, how)
    if failed:
        lines = [f"{len(failed)} arc(s) leaving a booth that charges at a point"
                 f" could not be measured:"]
        for group, tail, head, why in sorted(failed)[:10]:
            name = gares.get(group, ("", ""))[1]
            lines.append(f"         {group} ({name}), {charges[group]:.2f} EUR:"
                         f" {tail} -> {head}: {why}")
        lines.append("       A plaza with one lane charged and another free is"
                     " worse than one with neither: the router finds the free"
                     " lane and takes it every time.")
        raise stop("flat", "\n       ".join(lines))
    return out


# --------------------------------------------------------------------------
# Judging one source's batch
# --------------------------------------------------------------------------

def crow_km(a, b):
    """Straight-line distance between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def bearing(a, b):
    """Initial bearing from a to b, in radians."""
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    y = math.sin(dlon) * math.cos(lat2)
    x = (math.cos(lat1) * math.sin(lat2)
         - math.sin(lat1) * math.cos(lat2) * math.cos(dlon))
    return math.atan2(y, x)


def along(point, brg, metres):
    """The point `metres` from `point` on bearing `brg`."""
    lat1, lon1 = math.radians(point[0]), math.radians(point[1])
    d = metres / (EARTH_KM * 1000.0)
    lat2 = math.asin(math.sin(lat1) * math.cos(d)
                     + math.cos(lat1) * math.sin(d) * math.cos(brg))
    lon2 = lon1 + math.atan2(math.sin(brg) * math.sin(d) * math.cos(lat1),
                             math.cos(d) - math.sin(lat1) * math.sin(lat2))
    return (math.degrees(lat2), math.degrees(lon2))


def detour_of(answer, src, tgt, resolve, position):
    """(ratio, barrier-to-barrier metres) for a route that passes both booths.

    The barrier distance is read off the route already in hand rather than
    fetched again: the route runs extent to extent and crosses both barriers on
    the way, so the stretch between them is a slice of its own annotation.
    """
    nodes, dist = answer[0], answer[1]
    i = group_at(nodes, src, resolve)
    j = group_at(nodes, tgt, resolve, last=True)
    if i is None or j is None or j <= i:
        return None, None
    metres = sum(dist[i:j])
    line = crow_km(position[src], position[tgt])
    if line <= 0.001:
        return float("inf"), metres
    return (metres / 1000.0) / line, metres


def group_at(nodes, group, resolve, last=False):
    """Index of the first (or last) node on the route belonging to `group`.

    A plaza has one lane per booth and the inventory records the others as
    aliases of it, so a route crosses a group by whichever lane it used. Asking
    whether the group's own node id appears is the wrong question -- it is the
    question `blockers_of` already answers by resolving, and this does the same.
    """
    order = range(len(nodes) - 1, -1, -1) if last else range(len(nodes))
    for i in order:
        if resolve.get(nodes[i], nodes[i]) == group:
            return i
    return None


def wrong_side(nodes, src, tgt, inside, resolve):
    """Step 8's side test, tolerant of a route that used a different lane.

    Step 8 routes barrier to barrier from the booth's own coordinates, so the
    node it queried is the node it gets back. This step routes from further out,
    where the router is free to pick another lane of the same plaza, so the
    traversed node has to be found by group rather than assumed.
    """
    at = group_at(nodes, src, resolve)
    if src in inside and at is not None:
        leaves = nodes[at + 1] if at + 1 < len(nodes) else None
        if leaves not in inside[src]:
            return f"source {src} is left by {leaves}, which is not its toll side"
    at = group_at(nodes, tgt, resolve, last=True)
    if tgt in inside and at:
        reached = nodes[at - 1]
        if reached not in inside[tgt]:
            return f"target {tgt} is reached from {reached}, which is not its toll side"
    return None


def judge(src, wanted, answers, gares, traversable, resolve, inside,
          position, max_detour):
    """({code: (target, answer)}, [(code, target, reason, blocker, metres)]).

    A gare carried by several groups is one tariff, so the group the router
    reaches without passing a third booth is the one the tariff describes. Where
    more than one qualifies the shorter route wins -- the same rule step 8 uses
    to decide which group to ask about.
    """
    clean, rejects = {}, []
    for code, targets in wanted.items():
        for tgt in targets:
            answer = answers.get(tgt)
            if answer is None:
                rejects.append((code, tgt, "no route", None, None))
                continue
            nodes, _dist, _dur, _weight, metres = answer
            if (group_at(nodes, src, resolve) is None
                    or group_at(nodes, tgt, resolve) is None):
                rejects.append((code, tgt, "booth not on the route", None,
                                round(metres)))
                continue
            blockers = bd.blockers_of(nodes, src, tgt, traversable, resolve)
            if blockers:
                rejects.append((code, tgt, "booth", blockers[0], round(metres)))
                continue
            side = wrong_side(nodes, src, tgt, inside, resolve)
            if side:
                rejects.append((code, tgt, "wrong side", None, round(metres)))
                continue
            ratio, barrier_m = detour_of(answer, src, tgt, resolve, position)
            if ratio is not None and ratio > max_detour:
                rejects.append((code, tgt, f"detour {ratio:.0f}x", None,
                                round(barrier_m)))
                continue
            if code not in clean or metres < clean[code][1][4]:
                clean[code] = (tgt, answer)
    # A code with a clean group is not outstanding because its other group was
    # blocked: the tariff was placed, and the blocked group was never its subject.
    rejects = [r for r in rejects if r[0] not in clean]
    return clean, rejects


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def collect(router, pairs, priced, gares, traversable, resolve, position, inside,
            max_detour=MAX_DETOUR, progress=True):
    """Route every pair, sample the clean ones, and return the whole picture.

    Batched per source booth rather than issued pair by pair, for the reason
    step 8 batches: one source against many targets keeps the router's queue
    full and takes the routing from tens of minutes to a few.
    """
    segments = Segments()
    records = []        # one per placed pair, for the reconstruction
    unusable = []       # (src, code, target, reason, blocker, metres)
    by_source = collections.defaultdict(dict)
    for src, code, cents, targets in pairs:
        by_source[src][code] = targets

    started = time.monotonic()
    routed = 0
    fell_back = collections.Counter()
    for n, src in enumerate(sorted(by_source), 1):
        wanted = by_source[src]
        targets = sorted({t for ts in wanted.values() for t in ts})
        src_at, src_fallback = endpoint(priced, position, src, FIRST, FIRST_AT)
        if src_fallback:
            fell_back["entrance has no extent"] += 1
        ends = {}
        for t in targets:
            ends[t], tgt_fallback = endpoint(priced, position, t, LAST, LAST_AT)
            if tgt_fallback:
                fell_back["exit has no extent"] += 1
        answers = router.route_many(src_at, [(t, ends[t]) for t in targets])
        routed += len(targets)
        # Routing between the extents can produce a route that misses a booth
        # altogether: the extent is out on the open road, and from there the
        # fastest way to the other extent need not pass the barrier. Such a
        # route is not the journey the tariff is for, so that pair goes back to
        # barrier-to-barrier, which by construction passes both.
        for tgt in targets:
            answer = answers.get(tgt)
            if answer is None:
                continue
            nodes = answer[0]
            if (group_at(nodes, src, resolve) is not None
                    and group_at(nodes, tgt, resolve) is not None):
                continue
            fell_back["route missed a booth"] += 1
            answers[tgt] = router.route(position[src], position[tgt])
            routed += 1
        clean, rejects = judge(src, wanted, answers, gares, traversable,
                               resolve, inside, position, max_detour)
        for code, tgt, reason, blocker, metres in rejects:
            unusable.append((src, code, tgt, reason, blocker, metres))
        for code, (tgt, answer) in clean.items():
            # The route must actually pass the nodes the extents name. Where it
            # does not -- a coordinate that snapped onto a different lane, say --
            # the end is taken back to its booth and the pair routed again, so a
            # pair is never priced over a distance nobody drove.
            tgt_entry = priced.get(tgt) or {}
            missing = []
            if FIRST in priced[src] and priced[src][FIRST] not in answer[0]:
                missing.append("src")
            if LAST in tgt_entry and tgt_entry[LAST] not in answer[0]:
                missing.append("tgt")
            if missing:
                fell_back["extent node not on the route"] += len(missing)
                a = position[src] if "src" in missing else src_at
                b = position[tgt] if "tgt" in missing else ends[tgt]
                again = router.route(a, b)
                routed += 1
                if again is not None:
                    answer = again
            price_eur = priced[src]["prices"][code] / 100.0
            # A tariff of nothing is not a price per kilometre of nothing. The
            # operator records a few pairs at 0.00 EUR, and each one would put a
            # 0 EUR/km sample on every segment of a real motorway journey and
            # drag its mean down -- measured, one such pair set the low end of a
            # segment 1 504 journeys use. What a free section means is a
            # question for the price file, not for this step's arithmetic.
            if price_eur <= 0:
                unusable.append((src, code, tgt, "zero tariff", None,
                                 round(answer[4])))
                continue
            taken = sample_route(segments, answer, price_eur, len(records))
            if taken is None:
                unusable.append((src, code, tgt, "zero length", None, 0))
                continue
            per_km, drove = taken
            records.append({
                "src": src, "tgt": tgt, "code": code,
                "src_code": gares.get(src, ("", ""))[0],
                "eur": price_eur, "metres": answer[4],
                "per_km": per_km, "segments": drove,
            })
        if progress and (n % PROGRESS_EVERY == 0 or n == len(by_source)):
            rate = routed / max(time.monotonic() - started, 1e-6)
            print(f"    {n}/{len(by_source)} sources, {routed} routed,"
                  f" {len(records)} placed, {len(segments)} segments,"
                  f" {rate:.0f} routes/s", flush=True)
    return segments, records, unusable, fell_back


def reconstruct(segments, records, rate):
    """Add each pair's reconstructed tariff and its errors to its record."""
    for rec in records:
        total = 0.0
        for idx in rec["segments"]:
            total += rate[idx] * segments.dist[idx] / 1000.0
        rec["built"] = total
        rec["abs_error"] = total - rec["eur"]
        rec["rel_error"] = (total - rec["eur"]) / rec["eur"] if rec["eur"] else 0.0
    return rate


def fit_rates(segments, records, iterations, lam, report=None):
    """Per-segment rates that reproduce the tariffs, pulled toward their means.

    The mean of a segment's samples is the wrong answer whenever the journeys
    through it pay different rates for the same distance. Every journey votes
    one number -- its tariff over its own length -- onto all of its segments
    equally, so a segment shared by a dear section and a cheap one lands
    between, and summing the means back misses both. Measured, ROUMOIS to
    ALENCON NORD is 34.80 EUR and reconstructs at 22.82.

    So the rates are fitted instead. Each journey is one equation,

        sum over its segments of  rate * length  =  tariff

    and the fit minimises the error in those equations -- which is the journey
    error itself, rather than a per-segment agreement that journeys need not
    follow. It is solved in log space by iteration: each journey asks for the
    correction it needs, and each segment takes the mean of what its journeys
    asked. That keeps every rate positive without a constraint, and needs no
    linear algebra library.

    Left alone the fit is dangerous, because 23 352 equations do not pin
    249 454 unknowns. A segment four journeys cross can take any value that
    balances the books elsewhere, and unregularised it does: rates reach
    7.94 EUR/km, 35 times the mean, on a slip road at VAL DE LOING. The graph
    is asked about journeys nobody priced, and there such a segment is a
    12-minute penalty over half a kilometre.

    `lam` is what stops that. Each segment is a weighted average of what its
    journeys want and what its own samples said, with the data weighted by how
    many journeys there are and the prior weighted by `lam`:

        x <- (count * (x + correction) + lam * log(mean)) / (count + lam)

    A segment 1 500 journeys cross moves where the data says; one 4 journeys
    cross barely moves at all. The shrinkage is `lam / (count + lam)`, so the
    single number `lam` says how many journeys it takes before a segment is
    trusted over its own mean.
    """
    n = len(segments)
    prior = [math.log(segments.mean(i)) if segments.mean(i) > 0 else None
             for i in range(n)]
    x = [p if p is not None else 0.0 for p in prior]
    length = [segments.dist[i] / 1000.0 for i in range(n)]
    count = [segments.count[i] for i in range(n)]
    lines = []
    for step in range(1, iterations + 1):
        total = [0.0] * n
        seen = [0] * n
        worst = 0.0
        for rec in records:
            built = 0.0
            for i in rec["segments"]:
                built += math.exp(x[i]) * length[i]
            if built <= 0 or rec["eur"] <= 0:
                continue
            ask = math.log(rec["eur"] / built)
            worst = max(worst, abs(ask))
            for i in rec["segments"]:
                total[i] += ask
                seen[i] += 1
        for i in range(n):
            if not seen[i] or prior[i] is None:
                continue
            want = x[i] + total[i] / seen[i]
            x[i] = (count[i] * want + lam * prior[i]) / (count[i] + lam)
        lines.append(f"      iteration {step:2d}: largest journey correction"
                     f" {100 * (math.exp(worst) - 1):6.1f}%")
    if report is not None:
        report.extend(lines)
    return [math.exp(v) if prior[i] is not None else 0.0
            for i, v in enumerate(x)]


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def percentiles(values):
    """(median, p90, max) of an already-collected list, or zeros when empty."""
    if not values:
        return 0.0, 0.0, 0.0
    ordered = sorted(values)
    return (statistics.median(ordered),
            ordered[min(len(ordered) - 1, int(0.9 * len(ordered)))],
            ordered[-1])


def osm_node(node):
    return f"https://www.openstreetmap.org/node/{node}"


def deviation_table(segments, over, records, ways, limit=TABLE_ROWS):
    """The widest-spread segments, worst first, with the pairs behind each extreme.

    A diagnostic about the tariffs rather than about the file: it says which
    stretches of road two journeys disagree about, which is how four separate
    measurement errors were found. It is not what the rates are derived from --
    see `fit_rates` -- and nothing about it stops the run.
    """
    lines = []
    rows = []
    for i in over[:limit]:
        lo, hi = records[segments.low_pair[i]], records[segments.high_pair[i]]
        way, klass = ways.get((segments.frm[i], segments.to[i]), ("", ""))
        rows.append([
            f"{segments.frm[i]}->{segments.to[i]}",
            str(way),
            klass,
            str(segments.count[i]),
            f"{segments.low[i]:.4f}",
            f"{segments.high[i]:.4f}",
            f"{segments.mean(i):.4f}",
            f"{100 * segments.deviation(i):.1f}%",
            f"{lo['src_code']}->{lo['code']} {lo['eur']:.2f}EUR {lo['metres']/1000:.0f}km",
            f"{hi['src_code']}->{hi['code']} {hi['eur']:.2f}EUR {hi['metres']/1000:.0f}km",
        ])
    lines += table(
        ["segment", "way", "class", "n", "lowest", "highest", "mean", "dev",
         "pair at lowest", "pair at highest"],
        rows, right={3, 4, 5, 6, 7})
    if len(over) > limit:
        lines.append(f"    ... and {len(over) - limit} more, all in the report file")
    return lines


def price_table(records, worst, limit=TABLE_ROWS):
    """The outstanding prices, largest absolute error first."""
    lines = []
    rows = []
    for rec in worst[:limit]:
        rows.append([
            f"{rec['src']} ({rec['src_code']})",
            f"{rec['tgt']} ({rec['code']})",
            f"{rec['eur']:.2f}",
            f"{rec['built']:.2f}",
            f"{rec['abs_error']:+.2f}",
            f"{100 * rec['rel_error']:+.1f}%",
            f"{rec['metres'] / 1000:.1f}",
        ])
    lines += table(
        ["source", "target", "tariff", "built", "error", "rel", "km"],
        rows, right={2, 3, 4, 5, 6})
    if len(worst) > limit:
        lines.append(f"    ... and {len(worst) - limit} more, all in the report file")
    return lines


def unusable_table(unusable, gares, limit=TABLE_ROWS):
    """The pairs that reached no segment, with the reason and the booth in the way."""
    lines = []
    rows = []
    for src, code, tgt, reason, blocker, metres in unusable[:limit]:
        rows.append([
            f"{src} ({gares.get(src, ('', ''))[0]})",
            f"{tgt} ({code})",
            reason,
            str(blocker) if blocker else "",
            f"{metres / 1000:.1f}" if metres else "",
        ])
    lines += table(["source", "target", "reason", "booth in the way", "km"],
                   rows, right={4})
    if len(unusable) > limit:
        lines.append(f"    ... and {len(unusable) - limit} more, all in the report file")
    return lines


def flat_report(flat, segments, gares, wage, ways, limit=TABLE_ROWS):
    """Every booth that charges at a point, dearest first, with its arcs.

    A flat row is the whole tariff on one short arc, so it is the row most worth
    reading back. Nothing else in the report would show that these rates are
    three orders of magnitude below the fitted ones.
    """
    lines = ["", f"  booths that charge at a point ({len(flat)} arc(s))"]
    by_group = collections.defaultdict(list)
    for key, value in flat.items():
        by_group[value[4]].append((key, value))
    lines.append(f"    {len(by_group)} group(s),"
                 f" {sum(len(v) for v in by_group.values())} arc(s)")

    rows = []
    order = sorted(by_group, key=lambda g: (-flat[by_group[g][0][0]][3], g))
    for group in order[:limit]:
        code, name = gares.get(group, ("", ""))
        for key, (metres, dur, weight, eur, _g, how) in sorted(by_group[group]):
            klass = ways.get(key, ("", ""))[1]
            target = weight + eur / wage * 3600.0
            shared = "yes" if key in segments.index else ""
            rows.append([
                str(group), code, name,
                f"{key[0]}->{key[1]}", klass,
                f"{metres:.1f}", f"{weight:.2f}",
                f"{eur:.2f}", f"{target:.1f}",
                f"{metres / target:.9f}", how, shared,
            ])
    lines += table(
        ["group", "gare", "name", "arc", "class", "m", "weight", "EUR",
         "target", "rate", "measured by", "sampled too"],
        rows, right={5, 6, 7, 8, 9})
    if len(by_group) > limit:
        lines.append(f"    ... and {len(by_group) - limit} more group(s),"
                     f" all in the report file")

    shared = sum(1 for key in flat if key in segments.index)
    lines.append(f"    arcs that also carry samples from priced pairs: {shared}")
    rates = sorted(m / (w + e / wage * 3600.0)
                   for m, _d, w, e, _g, _h in flat.values())
    if rates:
        lines.append(f"    rate written  min {rates[0]:.9f}"
                     f"   max {rates[-1]:.9f}")
    how = collections.Counter(v[5].split()[0] for v in flat.values())
    lines.append("    measured by   "
                 + "   ".join(f"{k}: {n}" for k, n in sorted(how.items())))
    return lines


def journey_report(records, position, gares, limit=5):
    """What the rates cost a driver on each priced journey, and where worst.

    Two lists, because they disagree and both matter. The largest errors in
    euros are long journeys on dear sections, and they are what can send a
    driver down the wrong motorway. The largest errors in proportion are short
    cheap hops, where being twice the price is worth a minute and changes
    nothing. A report giving only one of the two misreads the data.

    Every row carries a link to the journey on the map, because a number
    without a road is not something anyone can check.
    """
    out = ["", "  journey error: what the rates charge against what the operator does"]
    real = sum(r["eur"] for r in records)
    built = sum(r["built"] for r in records)
    rel = sorted(abs(r["rel_error"]) for r in records)
    ab = sorted(abs(r["abs_error"]) for r in records)
    n = len(records)
    out.append(f"    {n} journeys, {real:,.0f} EUR of real toll,"
               f" {built:,.0f} EUR charged, net bias"
               f" {100 * (built - real) / real:+.2f}%")
    out.append(f"    relative  median {100 * rel[n // 2]:5.1f}%"
               f"   p90 {100 * rel[int(0.9 * n)]:5.1f}%"
               f"   p99 {100 * rel[int(0.99 * n)]:6.1f}%"
               f"   max {100 * rel[-1]:6.1f}%")
    out.append(f"    absolute  median {ab[n // 2]:5.2f}"
               f"   p90 {ab[int(0.9 * n)]:5.2f}"
               f"   p99 {ab[int(0.99 * n)]:6.2f}"
               f"   max {ab[-1]:6.2f} EUR")
    bands = "   ".join(f"{100 * t:.0f}%: {100 * sum(1 for x in rel if x <= t) / n:.1f}%"
                       for t in (0.05, 0.10, 0.20, 0.25))
    out.append(f"    journeys priced within   {bands}")

    out.append("")
    out.append(f"    error by journey length")
    rows = []
    for lo, hi in ((0, 25), (25, 100), (100, 200), (200, 400), (400, 99999)):
        sel = [r for r in records if lo <= r["metres"] / 1000 < hi]
        if not sel:
            continue
        rr = sorted(abs(r["rel_error"]) for r in sel)
        ee = sorted(abs(r["abs_error"]) for r in sel)
        rows.append([f"{lo}-{hi if hi < 99999 else ''} km", str(len(sel)),
                     f"{100 * rr[len(rr) // 2]:.1f}%",
                     f"{100 * rr[int(0.9 * len(rr))]:.1f}%",
                     f"{ee[len(ee) // 2]:.2f}", f"{ee[int(0.9 * len(ee))]:.2f}"])
    out += table(["length", "journeys", "median", "p90", "median EUR", "p90 EUR"],
                 rows, right={1, 2, 3, 4, 5})

    for title, key in ((f"worst {limit} in euros", lambda r: abs(r["abs_error"])),
                       (f"worst {limit} in proportion", lambda r: abs(r["rel_error"]))):
        out.append("")
        out.append(f"    {title}")
        for r in sorted(records, key=key, reverse=True)[:limit]:
            src, tgt = r["src"], r["tgt"]
            out.append(f"      {r['src_code']}->{r['code']}"
                       f"  {gares.get(src, ('', ''))[1]} -> {gares.get(tgt, ('', ''))[1]}")
            out.append(f"        real {r['eur']:7.2f}   charged {r['built']:7.2f}"
                       f"   error {r['abs_error']:+7.2f}"
                       f" ({100 * r['rel_error']:+.1f}%)"
                       f"   {r['metres'] / 1000:.1f} km"
                       f"   {abs(r['abs_error']) / 20 * 60:.0f} min of work")
            link = osmurl.url(position.get(src), position.get(tgt))
            if link:
                out.append(f"        {link}")
    return out


def report(segments, records, unusable, over, worst, gares, ways):
    """Everything the run found, printed before the file is written."""
    out = []
    out.append("")
    out.append(f"  widest per-segment spread ({len(segments)} segments, worst first)")
    out += deviation_table(segments, over, records, ways)
    out.append("")
    out.append(f"  unusable pairs ({len(unusable)})")
    if unusable:
        out += unusable_table(unusable, gares)
    else:
        out.append("    none; every priced pair reached at least one segment")
    return out


def summary(segments, records, unusable, over, single, ways,
            fell_back, fitted=None):
    """Counts by kind, so a run's totals are readable without the tables."""
    devs = [segments.deviation(i) for i in range(len(segments))]
    rates = fitted if fitted is not None else [segments.mean(i)
                                               for i in range(len(segments))]
    rels = [abs(r["rel_error"]) for r in records]
    d_med, d_p90, d_max = percentiles(devs)
    r_med, r_p90, r_max = percentiles(rels)
    lines = [
        "",
        "  summary",
        f"    segments                    {len(segments)}",
        f"    ... on a single sample      {single}",
        f"    priced pairs placed         {len(records)}",
        f"    unusable pairs              {len(unusable)}",
        f"    sample spread  median {100 * d_med:6.1f}%   p90 {100 * d_p90:6.1f}%"
        f"   max {100 * d_max:8.1f}%",
        f"    journey error  median {100 * r_med:6.1f}%   p90 {100 * r_p90:6.1f}%"
        f"   max {100 * r_max:8.1f}%",
        f"    rate  min {min(rates):.4f}   max {max(rates):.4f} EUR/km"
        + ("   (fitted)" if fitted is not None else "   (means)"),
    ]
    if fell_back:
        lines.append("    ends taken back to the booth")
        for reason, count in sorted(fell_back.items()):
            lines.append(f"      {reason:<28}  {count}")
    if ways:
        # Which classes the spread actually sits on. Asked because a ramp looked
        # like the obvious culprit; the answer is that it is not one -- mainline
        # motorway deviates more than the links do, so a class filter would drop
        # the better-behaved half and change nothing.
        by_class = collections.defaultdict(list)
        for i in range(len(segments)):
            key = (segments.frm[i], segments.to[i])
            if key in ways:
                klass = ways[key][1]
                by_class["*_link" if klass.endswith("_link") else klass].append(
                    segments.deviation(i))
        lines.append("")
        lines.append("  sample spread by highway class")
        rows = []
        for klass, devs in sorted(by_class.items(), key=lambda kv: -len(kv[1])):
            devs.sort()
            rows.append([
                klass, str(len(devs)),
                f"{100 * statistics.median(devs):.1f}%",
                f"{100 * devs[min(len(devs) - 1, int(0.9 * len(devs)))]:.1f}%",
                f"{100 * devs[-1]:.1f}%",
            ])
        lines += table(["class", "n", "median", "p90", "max"],
                       rows, right={1, 2, 3, 4})
    return lines


def write_report(path, segments, records, unusable, mean, ways, flat, wage):
    """Every segment and every pair, whatever the tables had room for."""
    doc = {
        # `lo_pair` and `hi_pair` index into `pairs` below. Without them a
        # segment's extremes name no journey, and the whole point of the
        # deviation report is which two tariffs disagree.
        "segments": [
            {"f": segments.frm[i], "t": segments.to[i], "n": segments.count[i],
             "lo": round(segments.low[i], 6), "hi": round(segments.high[i], 6),
             "lo_pair": segments.low_pair[i], "hi_pair": segments.high_pair[i],
             "mean": round(mean[i], 6), "dev": round(segments.deviation(i), 6),
             "m": round(segments.dist[i], 3), "s": round(segments.dur[i], 3),
             "w": round(segments.weight[i], 3),
             "way": ways.get((segments.frm[i], segments.to[i]), (None, None))[0],
             "class": ways.get((segments.frm[i], segments.to[i]), (None, None))[1]}
            for i in range(len(segments))],
        "pairs": [
            {"src": r["src"], "tgt": r["tgt"], "src_code": r["src_code"],
             "code": r["code"], "eur": round(r["eur"], 2),
             "built": round(r["built"], 4),
             "abs_error": round(r["abs_error"], 4),
             "rel_error": round(r["rel_error"], 6),
             "m": round(r["metres"], 1), "segments": len(r["segments"])}
            for r in records],
        "unusable": [
            {"src": s, "code": c, "tgt": t, "reason": rn,
             "blocker": b, "m": m}
            for s, c, t, rn, b, m in unusable],
        # One record per arc leaving a booth that charges at a point. `shared`
        # says the arc also carries samples from priced pairs, which is what
        # makes its row the sum of the two rather than the flat charge alone.
        # Kept to more places than the sampled segments above. An arc can be
        # 1.9 m long, and at three decimals the record no longer reproduces the
        # rate its own row carries -- which is the one thing this record is for.
        "flat": [
            {"group": group, "f": key[0], "t": key[1],
             "eur": round(eur, 2), "m": round(metres, 6),
             "s": round(dur, 6), "w": round(weight, 6),
             "rate": round(metres / (weight + eur / wage * 3600.0), 9),
             "how": how, "shared": key in segments.index,
             "way": ways.get(key, (None, None))[0],
             "class": ways.get(key, (None, None))[1]}
            for key, (metres, dur, weight, eur, group, how)
            in sorted((flat or {}).items())],
    }
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def merge_rows(segments, mean, flat):
    """{(from, to): (metres, seconds, weight, toll in euros)} for every row.

    The two sources add rather than replace. A segment sampled by priced pairs
    is charged what those pairs say its own length is worth; a segment leaving a
    booth that charges at a point is charged that booth's whole tariff; a
    segment that is both is charged both. Measured against the current price
    file and inventory no segment is both, and the rule is stated because the
    two sources are independent and a later inventory can make them meet.
    """
    rows = {}
    for i in range(len(segments)):
        key = (segments.frm[i], segments.to[i])
        rows[key] = (segments.dist[i], segments.dur[i], segments.weight[i],
                     mean[i] * segments.dist[i] / 1000.0)
    for key, (metres, dur, weight, eur, _group, _how) in (flat or {}).items():
        if key in rows:
            # The graph's own numbers for a segment both sources measured are
            # one segment's numbers, so the sampled reading stands and only the
            # money is added to.
            had = rows[key]
            rows[key] = (had[0], had[1], had[2], had[3] + eur)
        else:
            rows[key] = (metres, dur, weight, eur)
    return rows


def write_csv(path, rows, wage):
    """The segment speed file: keep the speed, move the rate.

    Sorted by node pair so a rerun from the same inputs is byte-identical, and
    with no blank line anywhere -- OSRM rejects the whole file for one.

    The target weight is rounded onto the grid the graph stores before it is
    inverted into a rate, rather than after. `osrm-customize` computes
    `round(length / rate * WEIGHT_MULTIPLIER)` and keeps that integer, so a
    target between two grid points is a target the graph will not hold. Rounding
    it here does not change the graph -- the integer OSRM arrives at is the same
    one either way -- and it changes the file, because the row now names a weight
    that survives the trip.

    What that buys is a diff that means something. The fit couples every segment
    to every other through the journeys that cross them, so one journey routing
    differently moves a rate almost everywhere, by a median of 3e-9. Unrounded,
    every one of those becomes a line in the diff of a file that is committed:
    measured at one regeneration, 38 306 rows moved and 3 of them changed a
    stored weight. Rounded, a rerun that leaves the graph alone leaves the file
    alone.

    The rate is still written to nine decimal places rather than six, and now for
    a sharper reason than before. Nine is what it takes to name a grid point
    rather than its neighbour at the small end of the range: a whole tariff on
    one short arc asks for a rate near 0.0014, where six places land 0.08% away
    and pick up a different integer. The fitted rows never ask for less than
    1.09, so six was never tested below that.

    The rounded target is never zero. An annotated weight above zero is at least
    one grid step, being a multiple of it, and the toll term only ever adds.
    """
    tmp = path + ".part"
    written = 0
    with open(tmp, "w", encoding="utf-8") as fh:
        for (frm, to) in sorted(rows):
            metres, dur, weight, toll_eur = rows[(frm, to)]
            if metres <= 0 or dur <= 0 or weight <= 0:
                continue
            speed_kmh = metres / dur * 3.6
            target = weight + toll_eur / wage * 3600.0
            stored = round(target * WEIGHT_MULTIPLIER) / WEIGHT_MULTIPLIER
            rate = metres / stored
            fh.write(f"{frm},{to},{speed_kmh:.6f},{rate:.9f}\n")
            written += 1
    os.replace(tmp, path)
    return written


# --------------------------------------------------------------------------
# Acceptance check
# --------------------------------------------------------------------------

def check_arcs(toll, optimal, arcs_by_group, charges, gares, wage, workers):
    """Every booth that charges at a point costs its tariff and no more.

    Tight where the pair check is loose, and deliberately so. A flat charge is
    not reconstructed from means -- it is written whole onto one arc -- so the
    arithmetic is exact and any disagreement is a fault in the file or in the
    graph rather than in the pricing.

    It is also the only check that catches the three ways a flat row fails
    silently: a rate the customization clamps, a rate the written precision
    rounds away, and a row whose segment `osrm-customize` never matched. All
    three leave the barrier free, and a route across it looks entirely normal.
    """
    jobs = [(group, arc) for group, arcs in sorted(arcs_by_group.items())
            for arc in arcs]

    def both(group, tail, head, tail_at, head_at):
        before = measure_arc(toll, tail, head, tail_at, head_at)
        after = measure_arc(optimal, tail, head, tail_at, head_at)
        return before, after

    results = {}
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        futures = {pool.submit(both, group, *arc): (group, arc[0], arc[1])
                   for group, arc in jobs}
        for future in concurrent.futures.as_completed(futures):
            results[futures[future]] = future.result()

    bad, errors = [], []
    for (group, tail, head), (before, after) in sorted(results.items()):
        expected = charges[group] / wage * 3600.0
        if before[0] is None or after[0] is None:
            which = "untouched" if before[0] is None else "toll-weighted"
            why = before[1] if before[0] is None else after[1]
            errors.append((group, tail, head, f"{which} graph: {why}"))
            continue
        got = after[2] - before[2]
        if abs(got - expected) > tolerance_of(expected):
            bad.append((group, tail, head, got, expected))

    out = ["", f"  booths that charge at a point:"
               f" {len(jobs)} arc(s) over {len(arcs_by_group)} group(s)"]
    if not bad and not errors:
        worst = max(
            (abs((after[2] - before[2]) - charges[g] / wage * 3600.0)
             for (g, _t, _h), (before, after) in results.items()),
            default=0.0)
        out.append(f"    every arc costs its tariff, worst disagreement"
                   f" {worst:.2f} weight units")
        return out

    for group, tail, head, why in errors[:10]:
        out.append(f"    {group} ({gares.get(group, ('', ''))[1]}):"
                   f" {tail} -> {head}: {why}")
    for group, tail, head, got, expected in bad[:10]:
        name = gares.get(group, ("", ""))[1]
        out.append(f"    {group} ({name}), {charges[group]:.2f} EUR:"
                   f" {tail} -> {head} costs {got:+.1f} against"
                   f" {expected:+.1f} expected")
    out.append("")
    raise Abort("\n".join(out) + "\n"
                f"       {len(bad)} arc(s) outside the"
                f" {100 * ARC_TOLERANCE:.0f}% tolerance and {len(errors)}"
                f" unmeasurable. A barrier that costs nothing on the"
                f" toll-weighted graph is a barrier the router drives through"
                f" for free.")


def tolerance_of(expected):
    """The absolute slack allowed on one arc's weight difference.

    Proportional, with a floor of one weight unit: the cheapest barrier is
    0.40 EUR, which is 72 weight units, and a proportional bound alone would
    make the check turn on the last decimal place of the smallest tariff.
    """
    return max(ARC_TOLERANCE * expected, 1.0)


def check_graphs(toll_url, optimal_url, position, wage, tolerance):
    """The two graphs must differ by the toll on the fixed pair and nothing else.

    Run after the file is applied, which is the only time both graphs exist. The
    pair is fixed in the source rather than passed in: a check whose subject is
    an argument is a check that can be pointed away from the failure.
    """
    expected = CHECK_TARIFF_EUR / wage * 3600.0
    out = []
    got = {}
    for name, url in (("toll", toll_url), ("optimal", optimal_url)):
        router = Router(url)
        router.wait_ready()
        answer = router.route(position[CHECK_SOURCE], position[CHECK_TARGET])
        if answer is None:
            raise Abort(f"the {name} graph returned no route for"
                        f" {CHECK_SOURCE} -> {CHECK_TARGET}")
        resp = requests.get(
            f"{url.rstrip('/')}/route/v1/driving/"
            f"{position[CHECK_SOURCE][1]},{position[CHECK_SOURCE][0]};"
            f"{position[CHECK_TARGET][1]},{position[CHECK_TARGET][0]}",
            params={"overview": "false", "steps": "false"}, timeout=120)
        route = resp.json()["routes"][0]
        got[name] = (route["weight"], route["duration"], route["distance"])
    dw = got["optimal"][0] - got["toll"][0]
    dd = got["optimal"][1] - got["toll"][1]
    out.append("")
    out.append(f"  acceptance check: {CHECK_SOURCE} (LE PERTHUS) ->"
               f" {CHECK_TARGET} (BEZIERS-OUEST), {CHECK_TARIFF_EUR:.2f} EUR")
    for name in ("toll", "optimal"):
        w, d, m = got[name]
        out.append(f"    {name:<8} weight {w:10.1f}   duration {d:9.1f} s"
                   f"   distance {m / 1000:7.1f} km")
    out.append(f"    weight   difference {dw:+.1f}  expected {expected:+.1f}"
               f"  ({dw / 60:.1f} min against {expected / 60:.1f} min)")
    out.append(f"    duration difference {dd:+.2f} s")
    ok = abs(dw - expected) <= tolerance * expected
    if not ok:
        out.append("")
        raise Abort("\n".join(out) + "\n"
                    f"       the weight difference is outside the"
                    f" {100 * tolerance:.0f}% tolerance.")
    return out


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def run(args):
    priced, _done = bp.load_state(args.prices)
    traversable, resolve, position = bd.load_inventory(args.booths)
    gares = load_gares(args.gares)
    bidirectional = {g for g, r in priced.items() if r["type"] == BIDIRECTIONAL}
    inside, _barriers, _unsettled = bd.load_sides(args.sides, bidirectional)

    sources = sorted(g for g, r in priced.items() if r.get("prices"))
    pairs, rows, unresolved = enumerate_pairs(priced, gares)
    candidates = sum(len(t) for _s, _c, _n, t in pairs)
    print(f"    {len(sources)} source booth(s), {rows} price row(s),"
          f" {len(pairs)} resolved to {candidates} candidate pair(s)")
    if unresolved:
        print(f"    {len(unresolved)} row(s) name a gare no target booth carries:"
              f" {unresolved[:5]}")

    # Which booths charge at a point is not known until the pairs are routed:
    # the second clause asks which of them ended one. So the count printed here
    # is the groups carrying a `price`, which is what can be known without the
    # router, and the set itself is settled after `collect`.
    priced_groups = sum(1 for r in priced.values() if r.get("price"))
    print(f"    {priced_groups} booth(s) carrying a price; how many of them"
          f" charge at a point is settled after the pairs are routed")
    if args.dry_run:
        return 0

    if args.limit:
        keep = {s for s in sources[:args.limit]}
        pairs = [p for p in pairs if p[0] in keep]
        candidates = sum(len(t) for _s, _c, _n, t in pairs)
        print(f"    --limit {args.limit}: {len(pairs)} pair(s),"
              f" {candidates} candidate(s)")

    router = Router(args.osrm, workers=args.workers)
    router.wait_ready()

    started = time.monotonic()
    segments, records, unusable, fell_back = collect(
        router, pairs, priced, gares, traversable, resolve, position, inside,
        max_detour=args.max_detour)
    print(f"    routed in {(time.monotonic() - started) / 60:.1f} min")

    if not records:
        raise Abort("no priced pair produced a single segment; nothing to write")

    # A booth is paid for by a pair only where that pair reached a segment, so
    # the set is built from the placed records rather than from every pair
    # enumerated. A pair rejected as unusable put its tariff nowhere, and its
    # booths stay eligible for a flat row.
    ends_pair = {r["src"] for r in records} | {r["tgt"] for r in records}
    charges, tally = flat_charges(priced, ends_pair)
    arcs_by_group = load_arcs(args.booths, charges)
    arc_count = sum(len(a) for a in arcs_by_group.values())
    lane_count = len({a[0] for arcs in arcs_by_group.values() for a in arcs})
    print(f"    {len(charges)} booth(s) charging at a point,"
          f" {lane_count} lane node(s), {arc_count} arc(s) to charge")
    for reason, count in sorted(tally.items()):
        print(f"      {reason:<24}  {count}")

    started = time.monotonic()
    flat = measure_flat(router, arcs_by_group, charges, gares, args.workers)
    print(f"    {len(flat)} arc(s) leaving a booth that charges at a point,"
          f" measured in {time.monotonic() - started:.0f}s")

    ways = {}
    if args.ways:
        started = time.monotonic()
        ways = index_ways(args.ways, segments, flat)
        # `ways` is keyed both ways round, because a way carries its nodes in one
        # order and a route may drive either. Count the forward keys only.
        matched = sum(1 for i in range(len(segments))
                      if (segments.frm[i], segments.to[i]) in ways)
        print(f"    {matched} of {len(segments)} segment(s) matched to a way"
              f" in {(time.monotonic() - started) / 60:.1f} min")

    if args.fit_iterations:
        fit_log = []
        started = time.monotonic()
        rate = fit_rates(segments, records, args.fit_iterations,
                         args.fit_lambda, fit_log)
        print(f"    fitted in {time.monotonic() - started:.0f}s,"
              f" {args.fit_iterations} iteration(s), lambda {args.fit_lambda:g}")
        for line in fit_log[-3:]:
            print(line)
    else:
        rate = [segments.mean(i) for i in range(len(segments))]
    mean = reconstruct(segments, records, rate)
    over = sorted(range(len(segments)), key=segments.deviation, reverse=True)
    single = sum(1 for i in range(len(segments)) if segments.count[i] == 1)
    worst = sorted(records, key=lambda r: abs(r["abs_error"]), reverse=True)

    for line in report(segments, records, unusable, over, worst, gares, ways):
        print(line)
    for line in journey_report(records, position, gares):
        print(line)
    for line in flat_report(flat, segments, gares, args.wage, ways):
        print(line)
    for line in summary(segments, records, unusable, over, single,
                        ways, fell_back,
                        rate if args.fit_iterations else None):
        print(line)

    write_report(args.report, segments, records, unusable, mean, ways,
                 flat, args.wage)
    print(f"\n    report written to {args.report}")

    if args.survey:
        print(f"    --survey: nothing written to {args.out}")
        return 0

    rows = merge_rows(segments, mean, flat)
    written = write_csv(args.out, rows, args.wage)
    print(f"    {written} row(s) written to {args.out}"
          f" ({len(segments)} sampled, {len(flat)} flat,"
          f" {sum(1 for k in flat if k in segments.index)} both)")
    return 0


def flat_from_report(path, booths):
    """(group -> tariff, group -> [arc]) as the run that wrote the file chose them.

    The check routes no priced pair, so it cannot tell which booths ended one
    and cannot apply the second clause itself. Deriving the set here by some
    other rule would mean checking a set this file was not written from, which
    is not a check of the file at all.

    The arcs' positions still come from the inventory: the report carries the
    node ids and the tariff, and `measure_arc` needs the two coordinates.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except OSError as exc:
        raise Abort(
            f"the acceptance check reads the flat charges from {path},"
            f" and it could not be opened: {exc}\n"
            f"       Run the step that writes it before verifying. A check with"
            f" no subjects passes on a graph with every barrier free.")
    records = doc.get("flat")
    if not records:
        raise Abort(
            f"{path} carries no `flat` records, so the acceptance check has no"
            f" barrier to check.\n"
            f"       Either the file predates the flat charges or the run wrote"
            f" none. A check with no subjects passes on a graph with every"
            f" barrier free, which is the failure it exists to catch.")

    position = {}
    with open(booths, encoding="utf-8") as fh:
        inv = yaml.safe_load(fh) or {}
    for section in ("toll_booths", "aliases"):
        for node, entry in (inv.get(section) or {}).items():
            position[int(node)] = tuple((entry or {})["latlon"])
            for head, latlon in ((entry or {}).get("onward_nodes") or {}).items():
                position.setdefault(int(head), tuple(latlon))

    charges, arcs = {}, collections.defaultdict(list)
    missing = []
    for rec in records:
        group, tail, head = rec["group"], rec["f"], rec["t"]
        if tail not in position or head not in position:
            missing.append((group, tail, head))
            continue
        charges[group] = rec["eur"]
        arcs[group].append((tail, head, position[tail], position[head]))
    if missing:
        raise Abort(
            f"{path} names {len(missing)} arc(s) the inventory no longer"
            f" places: {missing[:5]}\n"
            f"       The report and {booths} disagree about the road. Rerun the"
            f" step against this inventory rather than checking an arc whose"
            f" ends are unknown.")
    return charges, dict(arcs)


def check_rows_present(out_path, arcs_by_group, gares, charges):
    """Every arc the report names must be a row of the file being checked."""
    want = {(tail, head) for arcs in arcs_by_group.values()
            for tail, head, _t, _h in arcs}
    have = set()
    try:
        with open(out_path, encoding="utf-8") as fh:
            for line in fh:
                parts = line.split(",")
                if len(parts) == 4:
                    have.add((int(parts[0]), int(parts[1])))
    except OSError as exc:
        raise Abort(f"could not read {out_path} to check it carries every arc"
                    f" the report names: {exc}")
    absent = sorted(want - have)
    if absent:
        by_arc = {(t, h): g for g, arcs in arcs_by_group.items()
                  for t, h, _a, _b in arcs}
        lines = [f"{len(absent)} arc(s) named in the report are not rows of"
                 f" {out_path}:"]
        for tail, head in absent[:10]:
            group = by_arc[(tail, head)]
            lines.append(f"         {group} ({gares.get(group, ('', ''))[1]}),"
                         f" {charges[group]:.2f} EUR: {tail} -> {head}")
        lines.append("       The report and the file were written by different"
                     " runs. A barrier with no row is a barrier the router"
                     " drives through for free.")
        raise stop("flat", "\n       ".join(lines))


def verify(args):
    """The acceptance check alone, run once both graphs exist."""
    _traversable, _resolve, position = bd.load_inventory(args.booths)
    gares = load_gares(args.gares)
    charges, arcs_by_group = flat_from_report(args.report, args.booths)
    check_rows_present(args.out, arcs_by_group, gares, charges)
    print(f"    {len(charges)} booth(s) charging at a point,"
          f" {sum(len(a) for a in arcs_by_group.values())} arc(s)"
          f" from {args.report}")

    for line in check_graphs(args.osrm, args.osrm_optimal, position,
                             args.wage, args.tolerance):
        print(line)

    toll = Router(args.osrm, workers=args.workers)
    optimal = Router(args.osrm_optimal, workers=args.workers)
    optimal.wait_ready()
    for line in check_arcs(toll, optimal, arcs_by_group, charges, gares,
                           args.wage, args.workers):
        print(line)
    print("\n    acceptance check passed")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prices", required=True, help="vinci_price.yaml")
    ap.add_argument("--booths", required=True, help="osm_toll_booths.yaml")
    ap.add_argument("--gares", required=True, help="vinci_toll_booth.yaml")
    ap.add_argument("--sides", required=True, help="bidirectional_booth_sides.yaml")
    ap.add_argument("--out", required=True, help="the segment speed file to write")
    ap.add_argument("--report", required=True, help="the diagnostic report to write")
    ap.add_argument("--ways", metavar="PBF",
                    help="OSM extract to name the way behind each segment in the"
                         " findings; adds about four minutes")
    ap.add_argument("--osrm", required=True, help="base URL of the untouched instance")
    ap.add_argument("--osrm-optimal", help="base URL of the toll-weighted instance")
    ap.add_argument("--fit-iterations", type=int, default=FIT_ITERATIONS,
                    metavar="N",
                    help=f"fit the rates to the tariffs over N iterations"
                         f" instead of taking the mean of each segment's"
                         f" samples; 0 disables (default {FIT_ITERATIONS})")
    ap.add_argument("--fit-lambda", type=float, default=FIT_LAMBDA, metavar="F",
                    help=f"how many journeys it takes before a segment is"
                         f" trusted over its own mean (default {FIT_LAMBDA:g})")
    ap.add_argument("--max-detour", type=float, default=MAX_DETOUR, metavar="F",
                    help=f"drop a pair whose barrier-to-barrier route is more"
                         f" than this many times the straight line between the"
                         f" barriers (default {MAX_DETOUR})")
    # Required, with no default here. It is EUR_PER_HOUR in .env, passed by the
    # Makefile, and the route service reads the same setting: a default in this
    # file would be a second answer to "what is an hour worth", and a graph
    # weighted at one rate while the advice is offered at another.
    ap.add_argument("--wage-eur-per-hour", type=float, required=True,
                    dest="wage", metavar="EUR",
                    help="what a driver's hour is worth; set EUR_PER_HOUR in .env")
    ap.add_argument("--tolerance", type=float, default=0.20, metavar="F",
                    help="acceptance check tolerance on the weight difference")
    ap.add_argument("--workers", type=int, default=ROUTE_WORKERS, metavar="N")
    ap.add_argument("--survey", action="store_true",
                    help="enforce nothing, report everything, write nothing")
    ap.add_argument("--verify", action="store_true",
                    help="run the acceptance check against both graphs and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="enumerate the pairs and exit without routing")
    ap.add_argument("--limit", type=int, metavar="N",
                    help="diagnostic: use only the first N source booths")
    args = ap.parse_args()

    try:
        if args.verify:
            if not args.osrm_optimal:
                raise Abort("--verify needs --osrm-optimal as well as --osrm")
            return verify(args)
        return run(args)
    except Abort as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
