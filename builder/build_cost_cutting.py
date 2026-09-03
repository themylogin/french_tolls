#!/usr/bin/env python3
"""Step 12 -- where leaving the motorway and rejoining it costs less.

A closed-section tariff is not additive. Leaving at an intermediate gare and
re-entering immediately buys two short tickets instead of one long one, and the
two together are often cheaper: 12060 ROUMOIS sells a through ticket whose
Roumois-Gace portion costs 19.40 EUR, and the same portion on its own costs
10.50. Nothing else in the pipeline can find that. `build_segment_weights` turns
each tariff into a price per kilometre, which is linear in distance, so the
toll-weighted graph optimises geometry and the saving -- which lives in the
ticketing -- has been flattened away before the router ever sees it.

    for every sold pair
        grow stop sequences over the ticket graph
        keep the Pareto frontier of (fare, time)      -> no path beaten on both
    for every leg that starts at a stop
        route it and require a booth of that gare on the path   -> re-entry
    write where to stop and what it costs in time

No money is written. The saving is determined entirely by the price file, and a
second copy of it here would go stale the moment a booth is repriced with
nothing to notice -- which is why the price file is a real prerequisite of this
step rather than an order-only one.

Nothing here contacts the operator. Every duration is measured against the
project's own untouched graph.

Outputs:
    <--out>   data/cost-cutting.yaml, gare -> gare -> [{nodes, extra_time}]
"""

import argparse
import collections
import concurrent.futures
import os
import re
import sys

import requests

import overrides

# What a stop costs beyond the driving, in seconds. The first is the two
# transactions: paying on the way out and taking a ticket on the way back in.
BOOTH_S = 60

# A two-way booth is one node for both directions, so the router measures its
# turnaround as nothing -- there is no plaza in the graph to drive around. A
# vehicle cannot turn on the spot: it carries on to the next roundabout and
# comes back, about a minute each way on top of the transactions.
BIDIRECTIONAL_S = 180

# Stop sequences longer than this are not explored. Against the current data
# 96.6% of the sequences worth taking are a single stop and three of 11 843 use
# four, so the bound costs almost nothing -- but it is a bound, and raising it
# by one is how to prove it still costs nothing.
MAX_STOPS = 4

ROUTE_WORKERS = 16

BIDIRECTIONAL = "bidirectional"


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

def load_gares(path):
    """booth node -> gare code."""
    out, booth = {}, None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"  (\d+):", line)
            if m:
                booth = int(m.group(1))
                continue
            m = re.match(r"    id: '?([0-9A-Za-z]+)'?\s*$", line)
            if m and booth is not None:
                out[booth] = m.group(1)
    return out


def load_inventory(path):
    """(booth -> latlon, alias -> parent).

    The aliases matter here for one reason: a plaza is several parallel lanes
    and only one of them is the group representative. A vehicle re-entering may
    cross any lane, so a re-entry proved by an alias node is still a re-entry.
    Reading representatives alone rejects real ones.
    """
    pos, alias_parent = {}, {}
    section, booth = None, None
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^([a-z_]+):", line)
            if m:
                section, booth = m.group(1), None
                continue
            m = re.match(r"^  (\d+):\s*$", line)
            if m:
                booth = int(m.group(1))
                continue
            if booth is None:
                continue
            m = re.match(r"^    latlon: \[([0-9.\-]+), ([0-9.\-]+)\]", line)
            if m:
                pos[booth] = (float(m.group(1)), float(m.group(2)))
                continue
            m = re.match(r"^    parent_id: (\d+)", line)
            if m and section == "aliases":
                alias_parent[booth] = int(m.group(1))
    return pos, alias_parent


def load_prices(path, gare):
    """(gare -> {gare: cents}, booth -> type).

    An `enter` entry's `prices` map is a sold ticket from that booth's gare to
    the exit gare it is keyed by. Two booths of one gare are the two lanes of
    one plaza and quote the same tariff; the lower is taken so a stale duplicate
    cannot inflate a fare.
    """
    edges = collections.defaultdict(dict)
    kind = {}
    booth, gare_in, inside = None, None, False
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.startswith("toll_booths:"):
                inside = True
                continue
            if line.startswith("routes:"):
                inside = False
            if not inside:
                continue
            m = re.match(r"  (\d+):\s*$", line)
            if m:
                booth = int(m.group(1))
                gare_in = gare.get(booth)
                continue
            m = re.match(r"    type: (\w+)", line)
            if m and booth is not None:
                kind[booth] = m.group(1)
                continue
            m = re.match(r"      '?([0-9A-Za-z]+)'?: ([0-9.]+)\s*$", line)
            if m and gare_in:
                out_gare, cents = m.group(1), int(round(float(m.group(2)) * 100))
                if out_gare == gare_in:
                    continue
                if cents < edges[gare_in].get(out_gare, 1 << 60):
                    edges[gare_in][out_gare] = cents
    return edges, kind


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------

class Osrm:
    def __init__(self, base_url, workers=ROUTE_WORKERS):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.mount(
            "http://", requests.adapters.HTTPAdapter(pool_maxsize=workers * 2))
        self.workers = workers

    def leg(self, a, b, want_nodes):
        """(seconds, node ids) for a drive, or (None, ()) if unroutable."""
        (la, loa), (lb, lob) = a, b
        url = f"{self.base_url}/route/v1/driving/{loa},{la};{lob},{lb}"
        try:
            resp = self.session.get(
                url,
                params={"overview": "false", "steps": "false",
                        "annotations": "nodes" if want_nodes else "false"},
                timeout=120,
            )
            payload = resp.json()
        except (requests.RequestException, ValueError):
            return None, ()
        if payload.get("code") != "Ok":
            return None, ()
        route = payload["routes"][0]
        if not want_nodes:
            return route["duration"], ()
        nodes = []
        for part in route["legs"]:
            nodes += part["annotation"]["nodes"]
        return route["duration"], nodes


def measure(osrm, legs, enter_pos, exit_pos, nodes_of, report_every=5000):
    """{leg: seconds}, with a leg that never re-enters recorded as unusable.

    A leg keyed `(True, a, b)` starts at a's entrance: the first leg of a
    journey, and the direct leg it is compared against. One keyed `(False, a, b)`
    starts at a's exit plaza, which is where a vehicle stands after a stop.

    The second kind is only a split if the vehicle gets back onto the tolled
    road, and the way to know is whether the route crosses a booth of a again.
    Without that check the router is free to leave the motorway and drive across
    country -- for Roumois -> Luigny it answers 96.7 km at 63 km/h against
    242.4 km at 102 km/h on the A28, shorter and no slower, so the split looks
    free while the fare charges a second motorway ticket nobody bought.
    """
    seconds, rejected, done = {}, 0, 0

    def work(leg):
        at_entrance, a, b = leg
        start = enter_pos[a] if at_entrance else exit_pos[a]
        secs, nodes = osrm.leg(start, exit_pos[b], not at_entrance)
        if secs is None:
            return leg, None, False
        if at_entrance:
            return leg, secs, False
        # nodes[0] IS the exit booth this leg starts from, so it proves nothing.
        # Re-entry is a booth of the same gare appearing later: the entrance
        # lane of an ordinary plaza, or the same node crossed twice at a two-way
        # booth.
        if not any(n in nodes_of[a] for n in nodes[1:]):
            return leg, None, True
        return leg, secs, False

    with concurrent.futures.ThreadPoolExecutor(max_workers=osrm.workers) as pool:
        # A leg the router could not answer at all is not the same finding as one
        # that answered and drove somewhere else. Counting them together would
        # report a graph fault as a tariff observation.
        for leg, secs, no_reentry in pool.map(work, legs):
            seconds[leg] = secs
            if no_reentry:
                rejected += 1
            done += 1
            if done % report_every == 0:
                print(f"    {done}/{len(legs)} legs, {rejected} not a re-entry",
                      flush=True)
    return seconds, rejected


# --------------------------------------------------------------------------
# The search
# --------------------------------------------------------------------------

def pareto_add(front, fare, seconds, path):
    """Keep (fare, seconds, path) unless something already beats it on both.

    Only the frontier is worth exploring. A sequence that is dearer *and* slower
    than another to the same gare can never be preferred however an hour is
    valued, and dropping it is what keeps the search finite. Keeping only the
    cheapest instead would answer a different question: for LE BOULOU -> NIMES-O
    the cheapest chain saves 6.00 EUR for 22.6 minutes where one stop at
    AGDE-PEZENAS saves 2.40 for 2.5, and the second is what a driver wants.
    """
    for kept_fare, kept_secs, _ in front:
        if kept_fare <= fare and kept_secs <= seconds:
            return False
    front[:] = [entry for entry in front
                if not (fare <= entry[0] and seconds <= entry[1])]
    front.append((fare, seconds, path))
    return True


def candidates_from(source, edges, seconds, stop_cost, max_stops):
    """{destination: [(fare, seconds, path)]} for journeys that start at source."""
    labels = collections.defaultdict(list)
    frontier = []
    for first, fare in edges[source].items():
        secs = seconds.get((True, source, first))
        if secs is None:
            continue
        if pareto_add(labels[first], fare, secs, (source, first)):
            frontier.append((first, fare, secs, (source, first)))
    for _ in range(max_stops):
        nxt = []
        for at, fare, secs, path in frontier:
            for onward, leg_fare in edges.get(at, {}).items():
                if onward in path:
                    continue
                leg_secs = seconds.get((False, at, onward))
                if leg_secs is None:
                    continue
                new = (fare + leg_fare, secs + leg_secs + stop_cost(at),
                       path + (onward,))
                if pareto_add(labels[onward], *new):
                    nxt.append((onward, *new))
        frontier = nxt
        if not frontier:
            break
    return labels


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def write_advice(path, advice):
    """Sorted, quoted, and renamed into place.

    Gare codes are digit strings with leading zeros, so they are quoted here and
    compared as strings everywhere. The order is fixed so that a rerun that
    learns nothing produces no diff.
    """
    lines = ["toll_booths:\n"]
    for gare_in in sorted(advice):
        by_exit = advice[gare_in]
        if not by_exit:
            continue
        lines.append(f"  '{gare_in}':\n")
        for gare_out in sorted(by_exit):
            lines.append(f"    '{gare_out}':\n")
            for nodes, extra in by_exit[gare_out]:
                joined = ", ".join(str(n) for n in nodes)
                lines.append(f"      - nodes: [{joined}]\n")
                lines.append(f"        extra_time: {extra}\n")
    tmp = f"{path}.{os.getpid()}.part"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.writelines(lines)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prices", required=True, help="vinci_price.yaml")
    ap.add_argument("--gares", required=True, help="vinci_toll_booth.yaml")
    ap.add_argument("--booths", required=True, help="osm_toll_booths.yaml")
    ap.add_argument("--overrides", required=True,
                    help="hand-maintained booth overrides YAML")
    ap.add_argument("--out", required=True, help="cost-cutting.yaml to write")
    ap.add_argument("--osrm", required=True,
                    help="base URL of the untouched instance")
    ap.add_argument("--max-stops", type=int, default=MAX_STOPS, metavar="N",
                    help=f"longest stop sequence to explore (default {MAX_STOPS})")
    ap.add_argument("--booth-seconds", type=int, default=BOOTH_S, metavar="S",
                    help=f"what one stop costs beyond driving (default {BOOTH_S})")
    ap.add_argument("--bidirectional-seconds", type=int, default=BIDIRECTIONAL_S,
                    metavar="S", dest="bidi_seconds",
                    help=f"what a stop at a two-way booth costs beyond driving"
                         f" (default {BIDIRECTIONAL_S})")
    ap.add_argument("--workers", type=int, default=ROUTE_WORKERS, metavar="N")
    args = ap.parse_args()

    try:
        overrides.load(args.overrides)
    except overrides.OverrideError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    gare = load_gares(args.gares)
    pos, alias_parent = load_inventory(args.booths)
    edges, kind = load_prices(args.prices, gare)

    # Which lanes prove a re-entry at each gare: the representatives the gare
    # mapping names, plus every alias lane of the same plaza.
    nodes_of = collections.defaultdict(set)
    for booth, code in gare.items():
        nodes_of[code].add(booth)
    aliased = 0
    for alias, parent in alias_parent.items():
        code = gare.get(parent)
        if code:
            nodes_of[code].add(alias)
            aliased += 1

    # One entrance booth and one exit booth per gare, resolved once. A two-way
    # booth is both, and the pair is then the same node twice -- which is the
    # honest record: there is one node, and the turnaround it cannot show is
    # what `--bidirectional-seconds` pays for.
    enter_pos, exit_pos, two_way = {}, {}, set()
    enter_node, exit_node = {}, {}
    for booth in sorted(gare):
        code = gare[booth]
        if booth not in pos:
            continue
        role = kind.get(booth)
        if role == BIDIRECTIONAL:
            two_way.add(code)
        if role in ("enter", BIDIRECTIONAL, "passthrough", "gantry"):
            enter_pos.setdefault(code, pos[booth])
            enter_node.setdefault(code, booth)
        if role in ("exit", BIDIRECTIONAL, "passthrough", "gantry"):
            exit_pos.setdefault(code, pos[booth])
            exit_node.setdefault(code, booth)

    # A ticket is only usable if both its ends can be driven to. A gare the
    # operator sells tickets into and none out of -- 04216 AUBERIVES is one --
    # can be a destination but never a stop, because nothing leaves it.
    edges = {a: {z: c for z, c in d.items() if z in exit_pos}
             for a, d in edges.items() if a in enter_pos}
    edges = {a: d for a, d in edges.items() if d}
    tickets = sum(len(d) for d in edges.values())
    print(f"==> {len(edges)} gare(s) with an entrance, {tickets} sold ticket(s);"
          f" {len(two_way & set(edges))} two-way", flush=True)
    print(f"    re-entry is proved by {len(gare)} booth node(s)"
          f" and {aliased} alias lane(s)", flush=True)

    legs = set()
    for a, d in edges.items():
        for z in d:
            legs.add((True, a, z))
            if a in exit_pos:
                legs.add((False, a, z))
    legs = sorted(legs)
    print(f"==> routing {len(legs)} leg(s) against {args.osrm}", flush=True)

    osrm = Osrm(args.osrm, args.workers)
    seconds, rejected = measure(osrm, legs, enter_pos, exit_pos, nodes_of)
    post = sum(1 for leg in legs if not leg[0])
    print(f"    {rejected} of {post} post-stop leg(s) never re-enter and were"
          f" dropped ({100.0 * rejected / max(post, 1):.1f}%)", flush=True)

    def stop_cost(code):
        return args.bidi_seconds if code in two_way else args.booth_seconds

    advice = collections.defaultdict(lambda: collections.defaultdict(list))
    pairs = 0
    for n, source in enumerate(sorted(edges), 1):
        labels = candidates_from(source, edges, seconds, stop_cost,
                                 args.max_stops)
        for dest, direct in edges[source].items():
            baseline = seconds.get((True, source, dest))
            if baseline is None:
                continue
            found = []
            for fare, secs, path in labels.get(dest, ()):
                if fare >= direct or len(path) < 3:
                    continue
                stops = path[1:-1]
                # Two legs joined at a stop that sits on the direct path can
                # measure faster than the single direct leg. That is snapping
                # noise, not a saving: the transactions are pure addition and
                # floor the extra time.
                floor = sum(stop_cost(code) for code in stops)
                extra = max(int(round(secs - baseline)), floor)
                nodes = []
                for code in stops:
                    nodes += [exit_node[code], enter_node[code]]
                found.append((extra, tuple(nodes)))
            if not found:
                continue
            found.sort()
            advice[source][dest] = [(nodes, extra) for extra, nodes in found]
            pairs += 1
        if n % 100 == 0:
            print(f"    {n}/{len(edges)} source(s), {pairs} pair(s) with advice",
                  flush=True)

    print(f"==> {pairs} of {tickets} sold pair(s) are cheaper if the ticket is"
          f" split", flush=True)
    write_advice(args.out, advice)
    print(f"    written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
