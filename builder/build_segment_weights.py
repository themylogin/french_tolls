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

# How many rows of each findings table are printed. The full record always goes
# to the report file, so a cap costs nothing but the scrolling.
TABLE_ROWS = 40

# The pair the acceptance check uses. Fixed here rather than passed in: a graph
# built wrongly has to be caught where it is built, and a check whose subject is
# an argument is a check that can be pointed away from the failure.
CHECK_SOURCE = 36967365          # LE PERTHUS
CHECK_TARGET = 1676618837        # BEZIERS-OUEST
CHECK_TARIFF_EUR = 14.50


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

    def route(self, a, b):
        """(nodes, distance, duration, weight, metres) or None when there is no route."""
        (a_lat, a_lon), (b_lat, b_lon) = a, b
        try:
            resp = self._session().get(
                f"{self.base_url}/route/v1/driving/"
                f"{a_lon},{a_lat};{b_lon},{b_lat}",
                params={"annotations": ANNOTATIONS, "overview": "false",
                        "steps": "false"},
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


def index_ways(path, segments):
    """{(from, to): (way id, highway)} for every observed segment the extract carries."""
    wanted = set(segments.index)
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
# Judging one source's batch
# --------------------------------------------------------------------------

def crow_km(a, b):
    """Straight-line distance between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


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


def write_report(path, segments, records, unusable, mean, ways):
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
    }
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, separators=(",", ":"))
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def write_csv(path, segments, mean, wage):
    """The segment speed file: keep the speed, move the rate.

    Sorted by node pair so a rerun from the same inputs is byte-identical, and
    with no blank line anywhere -- OSRM rejects the whole file for one.
    """
    order = sorted(range(len(segments)),
                   key=lambda i: (segments.frm[i], segments.to[i]))
    tmp = path + ".part"
    written = 0
    with open(tmp, "w", encoding="utf-8") as fh:
        for i in order:
            metres, dur, weight = segments.dist[i], segments.dur[i], segments.weight[i]
            if metres <= 0 or dur <= 0 or weight <= 0:
                continue
            speed_kmh = metres / dur * 3.6
            toll_eur = mean[i] * metres / 1000.0
            target = weight + toll_eur / wage * 3600.0
            rate = metres / target
            fh.write(f"{segments.frm[i]},{segments.to[i]},"
                     f"{speed_kmh:.6f},{rate:.6f}\n")
            written += 1
    os.replace(tmp, path)
    return written


# --------------------------------------------------------------------------
# Acceptance check
# --------------------------------------------------------------------------

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
    inside, _barriers = bd.load_sides(args.sides, bidirectional)

    sources = sorted(g for g, r in priced.items() if r.get("prices"))
    pairs, rows, unresolved = enumerate_pairs(priced, gares)
    candidates = sum(len(t) for _s, _c, _n, t in pairs)
    print(f"    {len(sources)} source booth(s), {rows} price row(s),"
          f" {len(pairs)} resolved to {candidates} candidate pair(s)")
    if unresolved:
        print(f"    {len(unresolved)} row(s) name a gare no target booth carries:"
              f" {unresolved[:5]}")
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

    ways = {}
    if args.ways:
        started = time.monotonic()
        ways = index_ways(args.ways, segments)
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
    for line in summary(segments, records, unusable, over, single,
                        ways, fell_back,
                        rate if args.fit_iterations else None):
        print(line)

    write_report(args.report, segments, records, unusable, mean, ways)
    print(f"\n    report written to {args.report}")

    if args.survey:
        print(f"    --survey: nothing written to {args.out}")
        return 0

    written = write_csv(args.out, segments, mean, args.wage)
    print(f"    {written} row(s) written to {args.out}")
    return 0


def verify(args):
    """The acceptance check alone, run once both graphs exist."""
    _traversable, _resolve, position = bd.load_inventory(args.booths)
    for line in check_graphs(args.osrm, args.osrm_optimal, position,
                             args.wage, args.tolerance):
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
    ap.add_argument("--wage-eur-per-hour", type=float, default=20.0,
                    dest="wage", metavar="EUR",
                    help="what a driver's hour is worth (default 20)")
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
