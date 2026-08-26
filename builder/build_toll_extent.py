#!/usr/bin/env python3
"""Step 9 -- find where the tolled road begins and ends at each priced booth.

A tariff is priced between two booths, and the distance between the two booth
nodes is not the distance the driver was charged for. A booth sits where the
barrier is, and the tolled road runs on past it -- through the plaza, down the
slip road, to wherever the network actually releases the traffic.

The end of that road is discoverable by routing. Every journey leaving an exit
booth is on the same road until the network releases it; only then do they go to
different places. So the last node they all share is the last node of the road.

    for every priced booth
        route it against its 24 nearest places        (local, batched)
        exit:  booth -> place, keep the longest common prefix
        enter: place -> booth, keep the longest common suffix
        the far end of that shared run is the extent

MERU to AMBLAINVILLE on the A16 is priced at 1.90 EUR. Booth to booth it is
1.5 km, which reads 1.2422 EUR/km -- the highest sample in the whole segment
table. Measured to the extents it is 10.0 km and 0.19 EUR/km, an ordinary rate.

Output:
    <--out>   `first_toll_node_id` / `last_toll_node_id` folded into the price
              file's own booth entries
"""

import argparse
import collections
import concurrent.futures
import math
import sys
import time

import requests
import yaml

import build_vinci_prices as bp
import build_vinci_direct_prices as bd
import overrides as ov

Abort = bp.Abort
table = bp.table

ENTER, EXIT = bp.ENTER, bp.EXIT
BIDIRECTIONAL, GANTRY, PASSTHROUGH = bp.BIDIRECTIONAL, bp.GANTRY, bp.PASSTHROUGH

FIRST, FIRST_AT, LAST, LAST_AT = bp.TOLL_EXTENT_KEYS
COORD_OF = {FIRST: FIRST_AT, LAST: LAST_AT}

# Measured on AMBLAINVILLE: 24 places reach from 10.9 to 73.0 km, far enough
# that they genuinely lie in different directions, and 24 x ~1250 booths is
# about 30 000 routes -- the same order as the 23 835 step 10 does in 1.6 min.
PLACES = 24

# Convergence over three routes is not convergence; it is three routes that
# happen to start the same way.
MIN_ROUTES = 8

# A two-way booth's routes split between its two sides, and only one side serves
# the role being measured, so N places yield well under N usable routes. At N=24
# that left 64 of its 90 roles below the floor. Four times rescues about half;
# the rest have few reachable places on that side whatever N is.
BIDIRECTIONAL_PLACES = 4

ROUTE_WORKERS = 16
FLUSH_EVERY = 1             # one booth is the unit of work; see the module doc
PROGRESS_EVERY = 50
TABLE_ROWS = 40

EARTH_KM = 6371.0


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

def load_places(path):
    """[(name, node id, (lat, lon))] from the route set's own place list.

    The route set already carries the towns and villages the coverage search
    used. Reusing them keeps this step on committed inputs and introduces no
    file of its own.
    """
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    out = []
    for entry in doc.get("places") or []:
        latlon = entry.get("latlon") or []
        if len(latlon) != 2:
            continue
        out.append((str(entry.get("name") or ""), int(entry["node_id"]),
                    (float(latlon[0]), float(latlon[1]))))
    if not out:
        raise Abort(f"{path}: carries no usable `places` entries")
    return out


def great_circle_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def wanted_roles(priced, overrides):
    """{booth: (roles, ...)} -- which extent each booth needs, and why not.

    An `exit` wants the last node, an `enter` with prices the first, and a
    two-way booth with prices both: it is an entrance to a journey driven one
    way and an exit to the same journey driven the other.

    A `gantry` charges for a section travelled rather than closing someone
    else's ticket, so the road at it is not the end of anything a tariff is
    divided by. A `passthrough` carries one amount for itself and no pair. A
    two-way booth with no prices is a barrier. None of the three is measured.
    """
    work, skipped = {}, collections.Counter()
    for group, record in sorted(priced.items()):
        kind = record["type"]
        if group in overrides.ignored or _overridden(group, overrides):
            skipped["overridden"] += 1
            continue
        if kind == GANTRY:
            skipped["gantry"] += 1
            continue
        if kind == PASSTHROUGH:
            skipped["passthrough"] += 1
            continue
        roles = []
        if kind == EXIT:
            roles = [LAST]
        elif kind == ENTER and record.get("prices"):
            roles = [FIRST]
        elif kind == BIDIRECTIONAL and record.get("prices"):
            roles = [FIRST, LAST]
        if not roles:
            skipped["no role" if kind != BIDIRECTIONAL else "two-way barrier"] += 1
            continue
        work[group] = tuple(roles)
    return work, skipped


def _overridden(group, overrides):
    """Whether the override file speaks for this booth at all.

    Any entry is enough. The file is where a booth the road network describes
    wrongly is corrected by hand, and a derived extent would overwrite the
    correction on the next run -- so a booth named there is never routed,
    whether or not the entry states an extent.
    """
    return (group in overrides.forced or group in overrides.vinci
            or group in overrides.absent or group in overrides.price
            or group in overrides.isolated or group in overrides.one_way
            or group in overrides.first_toll_node
            or group in overrides.last_toll_node)


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

class Router(bd.Router):
    """Step 8's router, asking only for the node sequence."""

    def nodes(self, a, b):
        """(OSM nodes, [lon, lat] per node), or None when there is no route.

        `overview=full` returns one geometry point per annotated node, so the
        coordinates of any node on the route come free with the route itself.
        """
        (a_lat, a_lon), (b_lat, b_lon) = a, b
        try:
            resp = self._session().get(
                f"{self.base_url}/route/v1/driving/"
                f"{a_lon},{a_lat};{b_lon},{b_lat}",
                params={"annotations": "nodes", "overview": "full",
                        "geometries": "geojson", "steps": "false"},
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
        out = []
        for leg in found["legs"]:
            out.extend((leg.get("annotation") or {}).get("nodes") or [])
        points = (found.get("geometry") or {}).get("coordinates") or []
        if not out:
            return None
        # One point per node is what makes the coordinate lookup free. Where the
        # router disagrees, the nodes are still usable and the coordinates are
        # not, so the caller is told rather than handed a mismatched pair.
        return out, (points if len(points) == len(out) else None)

    def fan_out(self, origin, targets, outward):
        """[(nodes, points), ...] for one booth against many places."""
        def work(place):
            a, b = (origin, place) if outward else (place, origin)
            return self.nodes(a, b)

        with concurrent.futures.ThreadPoolExecutor(self.workers) as pool:
            answers = list(pool.map(work, targets))
        self.routes_made += len(targets)
        return answers


# --------------------------------------------------------------------------
# Convergence
# --------------------------------------------------------------------------

def oriented(nodes, booth, outward):
    """The route's nodes from the booth outward, or None when it has no booth.

    The router snaps the query coordinate onto a lane, so an outward route's
    annotation can begin one node *before* the booth -- AMBLAINVILLE's all read
    `[2587186119, 288919803, ...]`. That first node is upstream of the barrier
    and belongs to no journey through it, so the sequence starts at the booth.

    An inward route is reversed, which turns "the first node they converge on"
    into the same longest-common-prefix problem.
    """
    if booth not in nodes:
        return None
    if outward:
        return nodes[nodes.index(booth):]
    at = len(nodes) - 1 - nodes[::-1].index(booth)
    return nodes[:at + 1][::-1]


def oriented_points(nodes, points, booth, outward):
    """The geometry points, cut and reversed exactly as `oriented` cut the nodes."""
    if points is None or booth not in nodes:
        return None
    if outward:
        return points[nodes.index(booth):]
    at = len(nodes) - 1 - nodes[::-1].index(booth)
    return points[:at + 1][::-1]


def common_prefix(sequences):
    """The longest run of nodes every sequence starts with."""
    if not sequences:
        return []
    out = []
    for values in zip(*sequences):
        first = values[0]
        if any(v != first for v in values):
            break
        out.append(first)
    return out


def bound_at_next_booth(prefix, booth, traversable, resolve):
    """(prefix truncated before another booth, that booth or None).

    Beyond another booth is another ticket. A corridor whose nearby places all
    lie past a second barrier would otherwise converge into a section this
    tariff does not pay for, and the distance would be too long instead of too
    short.
    """
    for i, node in enumerate(prefix):
        if i == 0:
            continue
        if node in traversable:
            group = resolve.get(node, node)
            if group != booth:
                return prefix[:i], group
    return prefix, None


def keep_side_pairs(pairs, booth, inside, role):
    """`keep_side` over (sequence, points) pairs, keeping them aligned."""
    if booth not in inside:
        return pairs
    toll_side = inside[booth]
    return [(seq, pts) for seq, pts in pairs
            if len(seq) >= 2 and seq[1] not in toll_side]


def keep_side(sequences, booth, inside, role):
    """Drop routes that used the booth's free side for the role being measured.

    A two-way booth is an entrance driven one way and an exit driven the other,
    and both roles are measured from routes that touch the same node. Direction
    of query does not tell them apart; the side does. `inside_nodes` is the toll
    network, so the road *away* from the network is the one whose extent is
    wanted, and a route whose second node is on the inside is measuring the
    other role's road.
    """
    if booth not in inside:
        return sequences
    toll_side = inside[booth]
    kept = []
    for seq in sequences:
        if len(seq) < 2:
            continue
        if seq[1] in toll_side:
            continue
        kept.append(seq)
    return kept


def measure(booth, role, answers, inside, traversable, resolve, min_routes):
    """(extent, blocker, kept, latlon, km) or (None, reason, kept, None, None).

    The coordinates come from the geometry of one of the routes that agreed on
    the extent, and the distance from that same route's own metres. Both are
    free: the query already returned them.
    """
    outward = role == LAST
    oriented_pairs = []
    for nodes, points in answers:
        seq = oriented(nodes, booth, outward)
        if seq is None:
            continue
        oriented_pairs.append((seq, oriented_points(nodes, points, booth, outward)))
    kept_pairs = keep_side_pairs(oriented_pairs, booth, inside, role)
    seqs = [seq for seq, _pts in kept_pairs]
    if len(seqs) < min_routes:
        return None, f"only {len(seqs)} usable route(s)", len(seqs), None, None
    prefix = common_prefix(seqs)
    if not prefix:
        return None, "no route contained the booth node", len(seqs), None, None
    prefix, blocker = bound_at_next_booth(prefix, booth, traversable, resolve)
    extent = prefix[-1]
    latlon = None
    for seq, pts in kept_pairs:
        if pts is None:
            continue
        at = seq.index(extent)
        if at < len(pts):
            lon, lat = pts[at]
            latlon = bp.LatLon([round(float(lat), 7), round(float(lon), 7)])
            break
    return extent, blocker, len(seqs), latlon, len(prefix)


# --------------------------------------------------------------------------
# Distance, for the report
# --------------------------------------------------------------------------

def extent_km(router, booth_pos, place_pos, booth, extent, outward):
    """How far the extent node is from the barrier, along the road.

    For the report only, so a failure costs a column rather than the run.
    """
    a, b = (booth_pos, place_pos) if outward else (place_pos, booth_pos)
    try:
        resp = router._session().get(
            f"{router.base_url}/route/v1/driving/"
            f"{a[1]},{a[0]};{b[1]},{b[0]}",
            params={"annotations": "nodes,distance", "overview": "false",
                    "steps": "false"}, timeout=120)  # noqa: E501
        payload = resp.json()
        ann = payload["routes"][0]["legs"][0]["annotation"]
    except Exception:  # noqa: BLE001 - a missing distance costs a report column
        return None
    nodes, dist = ann["nodes"], ann["distance"]
    if booth not in nodes or extent not in nodes:
        return None
    lo, hi = sorted((nodes.index(booth), nodes.index(extent)))
    return sum(dist[lo:hi]) / 1000.0


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def osm_node(node):
    return f"https://www.openstreetmap.org/node/{node}"


def measured_table(rows, gares, limit=TABLE_ROWS):
    """Every measured booth with its extent distance, largest first."""
    rows = sorted(rows, key=lambda r: -(r["km"] if r["km"] is not None else -1))
    body = []
    for r in rows[:limit]:
        body.append([
            str(r["booth"]),
            gares.get(r["booth"], ("", ""))[0],
            gares.get(r["booth"], ("", ""))[1][:26],
            "first" if r["role"] == FIRST else "last",
            str(r["extent"]),
            f"{r['km']:.2f}" if r["km"] is not None else "",
            str(r["routes"]),
            str(r["blocker"] or ""),
            osm_node(r["extent"]),
        ])
    lines = table(["booth", "gare", "name", "role", "extent node", "km",
                   "routes", "bounded by", "link"], body, right={5, 6})
    if len(rows) > limit:
        lines.append(f"    ... and {len(rows) - limit} more")
    return lines


def unmeasured_table(rows, gares, limit=TABLE_ROWS):
    body = []
    for r in rows[:limit]:
        body.append([
            str(r["booth"]),
            gares.get(r["booth"], ("", ""))[0],
            gares.get(r["booth"], ("", ""))[1][:26],
            "first" if r["role"] == FIRST else "last",
            r["reason"],
            osm_node(r["booth"]),
        ])
    lines = table(["booth", "gare", "name", "role", "reason", "link"], body)
    if len(rows) > limit:
        lines.append(f"    ... and {len(rows) - limit} more")
    return lines


def locate(router, booth_pos, places, node, tries=8):
    """The coordinates of `node`, found on a route out of or into the booth.

    Used only for an extent the override file states. The nearest places are
    tried in both directions until one of their routes passes the node.
    """
    near = sorted(places, key=lambda p: great_circle_km(booth_pos, p[2]))[:tries]
    for outward in (True, False):
        answers = router.fan_out(booth_pos, [p[2] for p in near], outward)
        for nodes, points in answers:
            if points is None or node not in nodes:
                continue
            at = nodes.index(node)
            if at < len(points):
                lon, lat = points[at]
                return bp.LatLon([round(float(lat), 7), round(float(lon), 7)])
    return None


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def run(args):
    priced, done_routes = bp.load_state(args.out)
    traversable, resolve, position = bd.load_inventory(args.booths)
    gares = load_gares(args.gares)
    overrides = ov.load(args.overrides)
    bidirectional = {g for g, r in priced.items() if r["type"] == BIDIRECTIONAL}
    inside, _barriers = bd.load_sides(args.sides, bidirectional)
    places = load_places(args.route_set)

    work, skipped = wanted_roles(priced, overrides)
    stated = publish_stated(priced, overrides, None, None)
    stated = [(g, role, node) for g, role, node in stated
              if COORD_OF[role] not in priced[g]]

    outstanding = [(g, role) for g, roles in work.items() for role in roles
                   if role not in priced[g] or COORD_OF[role] not in priced[g]]
    total_roles = sum(len(r) for r in work.values())
    by_kind = collections.Counter(
        (priced[g]["type"], len(roles)) for g, roles in work.items())
    print(f"    {len(places)} place(s); {len(work)} booth(s) want"
          f" {total_roles} extent(s); {total_roles - len(outstanding)} already"
          f" recorded, {len(outstanding)} outstanding")
    print("    " + ", ".join(
        f"{n} {kind} x{count}" for (kind, count), n in sorted(by_kind.items())))
    print(f"    skipped: " + ", ".join(f"{n} {k}" for k, n in sorted(skipped.items()))
          + (f"; {len(stated)} stated by override" if stated else ""))
    if args.dry_run:
        return 0
    if not outstanding and not stated:
        print("    nothing outstanding; no route issued")
        return 0

    router = Router(args.osrm, workers=args.workers)
    router.wait_ready()

    # The override names a node and not a point, so its coordinates are looked
    # up before anything is derived. It is a lookup, not a derivation: the node
    # is the operator's and only its position is being asked for.
    for group, role, node in stated:
        latlon = locate(router, position[group], places, node)
        if latlon is None:
            raise Abort(
                f"the override states {role} = {node} for booth {group}, and no"
                f" route out of that booth passes it.\n"
                f"       An extent nothing can route to is not usable. Check the"
                f" node id, or remove the statement and let it be derived.")
        priced[group][role] = node
        priced[group][COORD_OF[role]] = latlon
        bp.write_state(args.out, priced, done_routes)
    if stated:
        print(f"    {len(stated)} stated extent(s) located")

    measured, unmeasured = [], []
    started = time.monotonic()
    by_booth = collections.defaultdict(list)
    for group, role in outstanding:
        by_booth[group].append(role)

    order = sorted(by_booth)
    if args.limit:
        order = order[:args.limit]
        print(f"    --limit {args.limit}: measuring {len(order)} booth(s)")

    for n, group in enumerate(order, 1):
        booth_pos = position[group]
        ordered = sorted(places, key=lambda p: great_circle_km(booth_pos, p[2]))
        # A two-way booth loses about half its routes to the side filter, so it
        # is given a multiple of the places a one-way booth gets.
        count = args.places
        if priced[group]["type"] == BIDIRECTIONAL:
            count *= args.bidirectional_places
        near = ordered[:count]
        for role in by_booth[group]:
            outward = role == LAST
            answers = router.fan_out(booth_pos, [p[2] for p in near], outward)
            extent, blocker, kept, latlon, _depth = measure(
                group, role, answers, inside, traversable, resolve,
                args.min_routes)
            if extent is None:
                unmeasured.append({"booth": group, "role": role,
                                   "reason": blocker})
                continue
            if latlon is None:
                unmeasured.append({"booth": group, "role": role,
                                   "reason": "no geometry for the extent node"})
                continue
            priced[group][role] = extent
            priced[group][COORD_OF[role]] = latlon
            km = extent_km(router, booth_pos, near[0][2], group, extent, outward)
            measured.append({"booth": group, "role": role, "extent": extent,
                             "km": km, "routes": kept, "blocker": blocker})
            bp.write_state(args.out, priced, done_routes)
        if n % PROGRESS_EVERY == 0 or n == len(order):
            rate = router.routes_made / max(time.monotonic() - started, 1e-6)
            print(f"    {n}/{len(order)} booth(s), {router.routes_made} routed,"
                  f" {len(measured)} measured, {len(unmeasured)} unmeasured,"
                  f" {rate:.0f} routes/s", flush=True)

    bp.write_state(args.out, priced, done_routes)
    print(f"\n    routed in {(time.monotonic() - started) / 60:.1f} min")

    print(f"\n  measured extents ({len(measured)})")
    for line in measured_table(measured, gares):
        print(line)
    if unmeasured:
        print(f"\n  unmeasured ({len(unmeasured)})")
        for line in unmeasured_table(unmeasured, gares):
            print(line)

    bounded = sum(1 for r in measured if r["blocker"])
    known = [r["km"] for r in measured if r["km"] is not None]
    print("\n  summary")
    print(f"    measured                    {len(measured)}")
    print(f"    ... bounded by a second booth   {bounded}")
    print(f"    unmeasured                  {len(unmeasured)}")
    for reason, count in sorted(collections.Counter(
            r["reason"] for r in unmeasured).items()):
        print(f"      {reason:<24}  {count}")
    for kind, count in sorted(skipped.items()):
        print(f"    skipped: {kind:<19}  {count}")
    if known:
        known.sort()
        print(f"    extent km  median {known[len(known) // 2]:6.2f}"
              f"   p90 {known[min(len(known) - 1, int(0.9 * len(known)))]:6.2f}"
              f"   max {known[-1]:7.2f}")
    return 0


def publish_stated(priced, overrides, router, position):
    """Record the extents the override file states, without deriving any.

    The override names a node and not a point, so the coordinates are looked up
    the same way a derived extent gets them: by routing away from the booth and
    reading the geometry where that node appears. That is a lookup rather than a
    derivation -- the node is the operator's, and only its position is asked for.
    """
    stated = []
    for group, node in sorted(overrides.first_toll_node.items()):
        if group in priced:
            stated.append((group, FIRST, node))
    for group, node in sorted(overrides.last_toll_node.items()):
        if group in priced:
            stated.append((group, LAST, node))
    return stated


def load_gares(path):
    """group -> (gare code, the operator's own name)."""
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return {int(g): (str((e or {}).get("id") or ""), str((e or {}).get("name") or ""))
            for g, e in (doc.get("toll_booths") or {}).items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="vinci_price.yaml, read and written")
    ap.add_argument("--booths", required=True, help="osm_toll_booths.yaml")
    ap.add_argument("--gares", required=True, help="vinci_toll_booth.yaml")
    ap.add_argument("--sides", required=True, help="bidirectional_booth_sides.yaml")
    ap.add_argument("--route-set", required=True, help="route_set.yaml, for its places")
    ap.add_argument("--overrides", required=True, help="hand-maintained booth overrides")
    ap.add_argument("--osrm", required=True, help="base URL of the untouched instance")
    ap.add_argument("--places", type=int, default=PLACES, metavar="N",
                    help=f"nearest places to route against (default {PLACES})")
    ap.add_argument("--bidirectional-places", type=int,
                    default=BIDIRECTIONAL_PLACES, metavar="K",
                    help=f"multiply --places by this for a two-way booth,"
                         f" whose routes the side filter halves"
                         f" (default {BIDIRECTIONAL_PLACES})")
    ap.add_argument("--min-routes", type=int, default=MIN_ROUTES, metavar="N",
                    help=f"leave a booth unmeasured below this many usable"
                         f" routes (default {MIN_ROUTES})")
    ap.add_argument("--workers", type=int, default=ROUTE_WORKERS, metavar="N")
    ap.add_argument("--dry-run", action="store_true",
                    help="enumerate the work and exit without routing")
    ap.add_argument("--limit", type=int, metavar="N",
                    help="diagnostic: measure only the first N booths")
    args = ap.parse_args()

    try:
        return run(args)
    except Abort as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
