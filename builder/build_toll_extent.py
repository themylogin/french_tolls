#!/usr/bin/env python3
"""Step 9 -- find where the tolled road begins and ends at each priced booth.

A tariff is priced between two booths, and the distance between the two booth
nodes is not the distance the driver was charged for. A booth sits where the
barrier is, and the tolled road runs on past it -- through the plaza, down the
slip road, to wherever the network releases the traffic.

That point is where the driver commits, and commitment is a property of the road
rather than of any journey over it:

    enter:  the region every path through which reaches the booth
    exit:   the region every path into which came from the booth
    the extent is the node just outside that region, on the free side

Grown backwards from the booth, a predecessor joins the region when every road
leaving it is already inside. A public roundabout node therefore never joins
one: it always carries an arm that goes somewhere else. So the tolled section
stops where the slip road meets the ring instead of running around it, which is
what the previous derivation did for 753 of 990 extents, 436 of them onto a ring.

A `highway=service` roundabout is the exception, and the rest area is why. Its
arms lead to the pumps, the parking and the restaurant, and every one of them
comes back to the carriageway -- so it *is* a place every path out of which
reaches the booth, and it belongs inside the region. Saint-Arnoult's exit runs
through the Aire de Limours - Briis-sous-Forges nineteen kilometres up the A10,
and treating that ring as an escape stopped the step on a region that was right.

The graph has to admit exactly what the router admits, or a region stops at a
fork the driver never sees. Access tags, the barrier whitelist and the gate
values are read out of the routing profile itself; the gate rule and the node
blacklist are the ones builder/patch_car_profile.py compiles into it. A locked
gate is the one difference. The router keeps it as a last resort, and this
graph closes it, because a last resort is not an escape.

It also has to reach further than the answer. A tolled slip road runs 8 km past
AMBLAINVILLE, and a graph carved 2 km around the booth ends in the middle of it
-- with no junction to stop at, which reads as "the tolled road ends here" and
is a fabrication. So this step carves its own extract: the drive classes of the
whole country, cut to cells that reach at least 11 km beyond every booth. A
region that still runs off the edge is reported, never published.

MERU to AMBLAINVILLE on the A16 is priced at 1.90 EUR. Booth to booth it is
1.5 km, which reads 1.2422 EUR/km -- the highest sample in the whole segment
table. Measured to the extents it is an ordinary rate.

Output:
    <--out>   `first_toll_node_id` / `last_toll_node_id` folded into the price
              file's own booth entries
"""

import argparse
import collections
import gc
import heapq
import math
import os
import re
import subprocess
import sys
import time

import osmium
import yaml

import booth_groups
import build_vinci_prices as bp
import build_vinci_direct_prices as bd
import patch_car_profile as pc
import overrides as ov

Abort = bp.Abort
table = bp.table

ENTER, EXIT = bp.ENTER, bp.EXIT
BIDIRECTIONAL, GANTRY, PASSTHROUGH = bp.BIDIRECTIONAL, bp.GANTRY, bp.PASSTHROUGH

FIRST, FIRST_AT, LAST, LAST_AT = bp.TOLL_EXTENT_KEYS
COORD_OF = {FIRST: FIRST_AT, LAST: LAST_AT}

# The tags a car profile consults for permission, most specific first. The
# first one present decides; the rest are not read. Same order as the profile's
# own `access_tags_hierarchy`.
ACCESS_HIERARCHY = ("motorcar", "motor_vehicle", "vehicle", "access")

# A guard, not a parameter. A region is bounded by the road, and the largest
# over the whole inventory is 240 nodes. Reaching this many means a one-way
# tagging error has made a corridor out of a town, and the booth is reported
# rather than published.
MAX_REGION = 4000

# Distance from the barrier past which an extent is named in the report rather
# than only counted. A long extent is either a real approach road or a region
# that ran too far, and the two are told apart by looking.
REPORT_KM = 1.0

# How far a branch is followed before it is taken to have reached the open
# network. This bounds what counts as "not really a way out": a plaza's own
# roads and the ramp between two adjacent barriers, which is metres, and not a
# tolled motorway section, which is tens of kilometres.
#
# The distinction matters more than it looks. ARGENTAN's merging ramp is fed by
# a booth seven metres back, a pocket of two nodes. Raise this to 20 000 and a
# whole tolled carriageway counts as a pocket instead, so an exit's region runs
# on until the network releases it -- past the edge of the carve for a quarter
# of all roles, which would need a second carve the size of France.
ESCAPE_CAP = 500

# How far from the barrier an absorbed dead end has to lie before the region is
# sent to the wider carve. The first carve reaches at least 11 km, so a branch
# that stops within this distance stops because the map says so, not because the
# file ended -- Péage de Gye's stub is fifty metres out. Only a dead end near
# the carve's own edge is worth a second look.
STUB_FAR_M = 8000

# The carve's cell size, in degrees. One cell of padding on every side, so the
# extract reaches at least this far beyond any booth: 0.1 deg is 11.1 km of
# latitude, against a longest measured extent of 8.11 km. The grouping carve's
# 0.02 deg is far too tight -- it ends inside AMBLAINVILLE's slip road.
CELL_DEG = 0.1

# The second carve, for the handful of booths the first one cannot bound. A
# region on a motorway with no junction for miles genuinely runs that far:
# RESTIGNE's is 17.5 km, which the first carve cannot see the end of. Cut around
# those booths alone, so the reach costs a small file rather than the memory of
# a country. 0.3 deg is 33.3 km.
WIDE_CELL_DEG = 0.3

PROGRESS_EVERY = 200
TABLE_ROWS = 40

EARTH_M = 6371000.0


# --------------------------------------------------------------------------
# What the router admits
# --------------------------------------------------------------------------

def lua_set(source, name):
    """The string values of a `name = Set { 'a', 'b' }` table in the profile.

    Read out of the profile rather than restated here, for the reason
    `patch_car_profile.penalised_barriers` gives: an image that admits a
    different set has that set governed by the rule, and a restatement here
    would drift from it silently -- taking the extents with it.
    """
    match = re.search(rf"{name}\s*=\s*Set\s*\{{(.*?)\}}", source, re.S)
    if match is None:
        raise Abort(f"no {name} table in the routing profile;"
                    f" the extent graph cannot mirror what the router drives")
    return frozenset(re.findall(r"['\"]([^'\"]+)['\"]", match.group(1)))


class Profile:
    """The three questions the extent graph asks of the routing profile."""

    def __init__(self, source):
        self.access_barred = lua_set(source, "access_tag_blacklist")
        self.service_barred = lua_set(source, "service_access_tag_blacklist")
        self.barrier_open = lua_set(source, "barrier_whitelist")
        # `barrier=gate` and `barrier=lift_gate`: passable for a penalty in the
        # stock profile, and passable only where an allowed class carries them
        # once patch_car_profile has had its way.
        self.gates = frozenset(pc.penalised_barriers(source))

    def way_barred(self, tags):
        """Whether the profile refuses a car this way."""
        for key in ACCESS_HIERARCHY:
            value = tags.get(key)
            if value is not None:
                return value in self.access_barred
        return False

    def service_way_barred(self, tags):
        """The extra rule the profile applies to `highway=service` alone."""
        return tags.get("access") in self.service_barred


def read_profile(path):
    with open(path, encoding="utf-8") as fh:
        return Profile(fh.read())


def load_blacklist(path):
    """The nodes the map asserts and the ground does not."""
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return {int(n) for n in (doc.get("nodes_blacklist") or [])}


class BarrierScan(osmium.SimpleHandler):
    """Every `barrier=*` node in the extract, with its value, and the locked ones."""

    def __init__(self):
        super().__init__()
        self.values = {}
        self.locked = set()

    def node(self, n):
        value = n.tags.get("barrier")
        if value is not None:
            self.values[n.id] = value
            if n.tags.get("locked") == "yes":
                self.locked.add(n.id)


def impassable_nodes(plaza_pbf, profile, blacklist):
    """(nodes no car can cross, how many of each kind were seen).

    Four rules. A barrier value the profile does not whitelist stops a car
    where it stands. A gate stops one everywhere an allowed highway class does
    not carry it, which is the rule patch_car_profile compiles into the
    profile. A blacklisted node is not a connection at all.

    A gate tagged `locked=yes` stops a car too, even where an allowed class
    carries it. The router keeps such a gate as a last resort, so a route that
    starts or ends behind it still crosses it. No driver leaves a tolled road
    through it, so it is not an escape.

    A booth is `barrier=toll_booth` and the profile whitelists it, so the
    inventory stays reachable.
    """
    scan = BarrierScan()
    scan.apply_file(plaza_pbf)
    gates, opened = pc.scan_gates(plaza_pbf, sorted(profile.gates))
    unlocked = opened - scan.locked
    blocked = set(blacklist)
    for node, value in scan.values.items():
        if value in profile.barrier_open:
            continue
        if value in profile.gates and node in unlocked:
            continue
        blocked.add(node)
    counts = {"barrier nodes": len(scan.values), "gates": len(gates),
              "gates an allowed class carries": len(opened),
              "of them locked": len(opened) - len(unlocked),
              "blacklisted": len(blacklist)}
    return blocked, counts


# --------------------------------------------------------------------------
# The graph
# --------------------------------------------------------------------------

def metres(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_M * math.asin(min(1.0, math.sqrt(h)))


class Graph(osmium.SimpleHandler):
    """Directed adjacency over the roads a car may drive, in metres.

    The classes are `booth_groups.DRIVE_CLASSES` and the direction comes from
    `booth_groups.two_way`, so this graph and the one the booths were grouped on
    can never disagree about which way a road runs.

    An edge touching an impassable node is not built at all, which is what makes
    a locked gate stop a region rather than open one.

    No coordinate is kept. The extract carries eighteen million nodes and the
    step publishes about a thousand, so their positions are read back in one
    further pass rather than held for every node -- three gigabytes of the
    eleven this otherwise costs.
    """

    def __init__(self, profile, blocked):
        super().__init__()
        self.profile = profile
        self.blocked = blocked
        self.fwd = collections.defaultdict(dict)
        self.rev = collections.defaultdict(dict)
        self.roundabout = set()
        self.ways_barred = 0
        self.nodes_seen = 0

    def way(self, w):
        highway = w.tags.get("highway")
        if highway not in booth_groups.DRIVE_CLASSES:
            return
        tags = dict(w.tags)
        if self.profile.way_barred(tags) or (
                highway == "service" and self.profile.service_way_barred(tags)):
            self.ways_barred += 1
            return
        junction = tags.get("junction")
        points = []
        for node in w.nodes:
            if not node.location.valid():
                return
            points.append((node.ref, (node.location.lat, node.location.lon)))
        # A service roundabout is a rest area's own ring, not a way out of the
        # tolled road: every arm returns to the carriageway. See the module
        # docstring -- it belongs inside a region rather than bounding one.
        if junction == "roundabout" and highway != "service":
            self.roundabout.update(ref for ref, _ in points)
        both = booth_groups.two_way(highway, tags.get("oneway"), junction)
        self.nodes_seen += len(points)
        for (a, at), (b, bt) in zip(points, points[1:]):
            if a in self.blocked or b in self.blocked:
                continue
            length = metres(at, bt)
            self.fwd[a][b] = length
            self.rev[b][a] = length
            if both:
                self.fwd[b][a] = length
                self.rev[a][b] = length

    @property
    def edges(self):
        return sum(len(v) for v in self.fwd.values())


class Positions(osmium.SimpleHandler):
    """The coordinates of a named handful of nodes."""

    def __init__(self, wanted):
        super().__init__()
        self.wanted = wanted
        self.found = {}

    def node(self, n):
        if n.id in self.wanted:
            self.found[n.id] = (n.location.lat, n.location.lon)


def positions_of(path, wanted):
    scan = Positions(set(wanted))
    scan.apply_file(path)
    return scan.found


def carve_wide(drive_pbf, coords, out_pbf, cell_deg):
    """A carve around named booths alone, for the regions the first cannot bound.

    Not cached. It exists only when the first pass has found a region that ran
    out of data, its booth set is that pass's finding rather than an input, and a
    file kept from an earlier set would answer for the wrong booths.
    """
    if os.path.exists(out_pbf):
        os.unlink(out_pbf)
    booth_groups.carve_neighbourhoods(
        drive_pbf, coords, out_pbf, os.path.dirname(out_pbf) or ".",
        cell_deg=cell_deg, poly_name="extent_wide_cells.geojson")
    print(f"    wider extract: {os.path.getsize(out_pbf) / 1e6:.1f} MB")
    return out_pbf


def carve(source_pbf, booths, ways_pbf, drive_pbf, cell_deg):
    """The extract this step reasons over, carved once and kept.

    Two stages, both `osmium` and both cached, for the reason
    `build_osm_toll_booths.run_tags_filter` gives: a C++ streaming pass reduces
    the country before pyosmium reads any of it.

    Stage one keeps the drive classes of the whole country. Stage two cuts that
    to cells around the booths, which is what makes the graph fit in memory --
    the country's drive network is forty million nodes and the carve is
    eighteen.
    """
    if os.path.exists(ways_pbf):
        print(f"    reusing {ways_pbf}"
              f" ({os.path.getsize(ways_pbf) / 1e6:.1f} MB)")
        return ways_pbf
    if not os.path.exists(drive_pbf):
        expression = "w/highway=" + ",".join(sorted(booth_groups.DRIVE_CLASSES))
        tmp = drive_pbf + ".part"
        cmd = ["osmium", "tags-filter", "--overwrite", "-f", "pbf",
               "-o", tmp, source_pbf, expression]
        print("    " + " ".join(cmd), flush=True)
        subprocess.run(cmd, check=True)
        os.replace(tmp, drive_pbf)
        print(f"    drive-class ways: {os.path.getsize(drive_pbf) / 1e6:.1f} MB")
    else:
        print(f"    reusing {drive_pbf}"
              f" ({os.path.getsize(drive_pbf) / 1e6:.1f} MB)")
    coords = {int(g): tuple(e["latlon"])
              for g, e in (booths.get("toll_booths") or {}).items()}
    coords.update({int(a): tuple(e["latlon"])
                   for a, e in (booths.get("aliases") or {}).items()})
    booth_groups.carve_neighbourhoods(
        drive_pbf, coords, ways_pbf, os.path.dirname(ways_pbf) or ".",
        cell_deg=cell_deg, poly_name="extent_cells.geojson")
    print(f"    extent extract: {os.path.getsize(ways_pbf) / 1e6:.1f} MB")
    return ways_pbf


# --------------------------------------------------------------------------
# The region
# --------------------------------------------------------------------------

def escapes_freely(node, onward, toll_nodes, cap, memo):
    """Whether a driver taking `node` reaches the open network without paying.

    The closure runs in the direction the driver would travel the branch --
    forward out of an entrance's corridor, backward into an exit's -- and stops
    at every toll point. A branch whose closure stays small is a stub or a pocket
    of the toll network, and neither is a way out.

    `cap` bounds the walk. A pocket larger than it reads as open, which is the
    conservative direction: the tolled section ends early rather than running
    over road nobody paid for.
    """
    hit = memo.get(node)
    if hit is not None:
        return hit
    seen = {node}
    queue = collections.deque([node])
    free = False
    while queue:
        current = queue.popleft()
        for other in onward.get(current, ()):
            if other in seen or other in toll_nodes:
                continue
            if len(seen) >= cap:
                free = True
                queue.clear()
                break
            seen.add(other)
            queue.append(other)
    for reached in seen:
        memo.setdefault(reached, free)
    return free


def region_of(seed, onward, back, traversable, resolve, group, cap=MAX_REGION,
              toll_nodes=frozenset(), escape_cap=ESCAPE_CAP, memo=None):
    """(the region, the booth group that bounded it, capped, stubbed).

    `onward` is the direction a driver travels and `back` the direction the
    region grows in. For an entrance those are (fwd, rev): a predecessor joins
    when every road leaving it is already inside. For an exit they are swapped.

    A road that does not get the driver out is not a way out, and there are two
    ways to fail that. One is to lead nowhere: Péage de Gye sits on the A 31
    mainline and the junction before it carries a two-node `motorway_link` that
    stops dead, so a driver taking it reaches the end of the data and can only
    turn round and pay. The other is to lead further into the toll network:
    ARGENTAN's exit has an on-ramp merging fifty metres past the barrier, and
    that ramp is fed seven metres back by a booth of its own, so its traffic has
    paid too. Both ended a tolled road at its barrier.

    A branch therefore bars its predecessor only when its own closure reaches the
    open network without crossing a toll point -- see `escapes_freely`.

    Whether a stub is a mapping artefact or the edge of the carve cannot be told
    from here, so `stubbed` is returned with the region and the caller sends it
    to the wider carve, where a road that really continues will.

    Another booth group bounds the region rather than joining it. Beyond another
    booth is another ticket, and a corridor that ran on through a second barrier
    would carry a section this tariff does not pay for.
    """
    if memo is None:
        memo = {}
    inside = set(seed)
    queue = collections.deque(seed)
    blocker = None
    capped = False
    stubs = set()
    while queue:
        node = queue.popleft()
        for other in back.get(node, ()):
            if other in inside:
                continue
            if other in traversable and resolve.get(other, other) != group:
                blocker = blocker or resolve.get(other, other)
                continue
            forward = onward.get(other)
            if not forward:
                continue
            escapes = [n for n in forward if n not in inside]
            if escapes:
                if any(escapes_freely(n, onward, toll_nodes, escape_cap, memo)
                       for n in escapes):
                    continue
                # Absorbed. A branch that leads into the toll network is a
                # confident answer; one that leads nowhere might be the edge of
                # the carve, and only that wants a wider look.
                if any(not onward.get(n) for n in escapes):
                    # Record the node that absorbed the dead end, not the dead
                    # end itself: the region node is the one the caller can
                    # measure a distance to.
                    stubs.add(other)
            if len(inside) >= cap:
                capped = True
                queue.clear()
                break
            inside.add(other)
            queue.append(other)
    return inside, blocker, capped, stubs


def boundary_of(inside, back):
    """(the region's own boundary nodes, the free nodes just outside them)."""
    edge, free = set(), set()
    for node in inside:
        for other in back.get(node, ()):
            if other not in inside:
                edge.add(node)
                free.add(other)
    return edge, free


def distances(sources, adj, limit=20000.0):
    """Road distance from every node within `limit` to the booth, in metres."""
    dist = {s: 0.0 for s in sources}
    queue = [(0.0, s) for s in sources]
    heapq.heapify(queue)
    while queue:
        d, node = heapq.heappop(queue)
        if d > dist.get(node, math.inf) or d > limit:
            continue
        for other, length in adj.get(node, {}).items():
            step = d + length
            if step < dist.get(other, math.inf):
                dist[other] = step
                heapq.heappush(queue, (step, other))
    return dist


def side_limited(back, seed, toll_side):
    """`back` with the booth's own toll side removed from it.

    A two-way booth is an entrance driven one way and an exit driven the other,
    and only the free side serves the role being measured. Growing a region
    through an `inside_nodes` node would measure the other role's road.
    """
    if not toll_side:
        return back
    limited = collections.defaultdict(dict, back)
    for node in seed:
        limited[node] = {k: v for k, v in back.get(node, {}).items()
                         if k not in toll_side}
    return limited


def measure(group, role, graph, seed, toll_side, traversable, resolve, cap,
            boundary="inside", toll_nodes=frozenset()):
    """Everything the report and the price file want about one booth's extent.

    `boundary` names which side of the region is published. "free" is the node
    just outside it, the last one at which a choice still existed. "inside" is
    the node that one attaches to, one segment into the corridor -- the first
    node the driver reaches already committed.

    Both name the same junction and they differ by one segment, a median of 19 m,
    so neither is a better measurement. What separates them is that a consumer
    routes between the published coordinates, and a junction is exactly where a
    router's snapping is ambiguous: asked to start from one, OSRM may take a
    different arm and never traverse the node it was given, and
    `build_segment_weights` then discards the pair. Measured over the priced
    pairs, publishing the free node discards 3 912 of them and publishing the
    inside node discards 326.
    """
    onward, back = ((graph.fwd, graph.rev) if role == FIRST
                    else (graph.rev, graph.fwd))
    back = side_limited(back, seed, toll_side)
    inside, blocker, capped, stubs = region_of(
        seed, onward, back, traversable, resolve, group, cap,
        toll_nodes=toll_nodes, memo={})
    edge, free = boundary_of(inside, back)
    toward = graph.rev if role == FIRST else graph.fwd
    dist = distances(seed, toward)
    reachable = sorted((dist[n], n) for n in free if n in dist)
    extent = reachable[0][1] if reachable else None
    if extent is not None and boundary == "inside":
        # The region node the chosen free node attaches to. Nearest to the
        # booth, so the same tie-break as the free side: a region with two
        # approaches never claims the road the other one drove.
        attached = sorted((dist[n], n) for n in inside
                          if extent in back.get(n, ()) and n in dist)
        if attached:
            extent = attached[0][1]
    # A node the graph simply stops at is either a cul-de-sac or the edge of the
    # carve, and the two are not told apart from inside. Only one near the edge
    # of the carve's own reach is worth a wider look: a road that starts a few
    # hundred metres from a barrier starts because the map says so.
    truncated = [n for n in inside
                 if not back.get(n) and dist.get(n, 0.0) > STUB_FAR_M]
    return {
        "extent": extent,
        "metres": (dist.get(extent) if extent is not None else None),
        "blocker": blocker,
        "capped": capped,
        "size": len(inside) - len(seed),
        "free": len(free),
        "edge": len(edge),
        "truncated": bool(truncated) or any(
            dist.get(n, 0.0) > STUB_FAR_M for n in stubs),
        "truncated_at": max((dist[n] for n in truncated if n in dist), default=0.0),
        "on_roundabout": bool(inside & graph.roundabout),
        "at_barrier": bool(edge) and min(
            (dist[n] for n in edge if n in dist), default=math.inf) < 1.0,
    }


# --------------------------------------------------------------------------
# Which booths want an extent
# --------------------------------------------------------------------------

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
    correction on the next run -- so a booth named there is never derived,
    whether or not the entry states an extent.
    """
    return (group in overrides.forced or group in overrides.vinci
            or group in overrides.absent or group in overrides.price
            or group in overrides.isolated or group in overrides.one_way
            or group in overrides.first_toll_node
            or group in overrides.last_toll_node)


def lanes_of(group, traversable, resolve):
    """The group's own node and every lane the inventory records as its alias."""
    lanes = {group} if group in traversable else set()
    lanes.update(n for n, parent in resolve.items() if parent == group)
    return lanes


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
            str(r["size"]),
            str(r["blocker"] or ""),
            osm_node(r["extent"]),
        ])
    lines = table(["booth", "gare", "name", "role", "extent node", "km",
                   "nodes", "bounded by", "link"], body, right={5, 6})
    if len(rows) > limit:
        lines.append(f"    ... and {len(rows) - limit} more")
    return lines


def named_table(rows, gares, threshold):
    """Every extent past the threshold, named rather than counted."""
    rows = [r for r in rows if r["km"] is not None and r["km"] >= threshold]
    body = []
    for r in sorted(rows, key=lambda r: -r["km"]):
        body.append([
            str(r["booth"]),
            gares.get(r["booth"], ("", ""))[0],
            gares.get(r["booth"], ("", ""))[1][:26],
            "first" if r["role"] == FIRST else "last",
            f"{r['km']:.2f}",
            osm_node(r["extent"]),
        ])
    return rows, table(["booth", "gare", "name", "role", "km", "link"], body,
                       right={4})


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


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------

def derive_pass(graph, order, by_booth, args, priced, done_routes, traversable,
                resolve, inside_nodes, measured, unmeasured, pending, tally,
                defer_unbounded, toll_nodes=frozenset(), unsettled_sides=frozenset()):
    """Derive every role in `by_booth` over one graph.

    Returns the roles this graph could not bound: a region that ran to a node
    the graph stops at, or one that found no free side at all. On the first
    carve those are deferred to a wider one; on the wider carve there is nowhere
    left to go, so they are reported as unmeasured.
    """
    unbounded = []
    for n, group in enumerate(order, 1):
        seed = {node for node in lanes_of(group, traversable, resolve)
                if node in graph.fwd or node in graph.rev}
        toll_side = {int(node) for node in inside_nodes.get(group, ())}
        for role in by_booth[group]:
            if not seed:
                unmeasured.append({"booth": group, "role": role,
                                   "reason": "no lane on a road a car may drive"})
                continue
            if group in unsettled_sides:
                # A two-way booth whose sides did not settle has an incomplete
                # `inside_nodes`, so the restriction that tells its two roles
                # apart cannot be applied. Growing a region without one runs it
                # through the toll side and answers for the wrong role -- a
                # wrong measurement, where leaving it out is only a gap.
                unmeasured.append({"booth": group, "role": role,
                                   "reason": "two-way booth's sides did not settle"})
                continue
            found = measure(group, role, graph, seed, toll_side,
                            traversable, resolve, args.max_region, args.boundary,
                            toll_nodes)
            if found["capped"]:
                unmeasured.append({"booth": group, "role": role,
                                   "reason": f"region past {args.max_region} nodes"})
                continue
            if found["truncated"] or found["extent"] is None:
                if defer_unbounded:
                    unbounded.append((group, role))
                    continue
                tally["truncated"] += 1
                if found["extent"] is None:
                    unmeasured.append({"booth": group, "role": role,
                                       "reason": "no free side within the extract"})
                    continue
            extent = found["extent"]
            if found["free"] > 1:
                tally["ambiguous"] += 1
            if found["at_barrier"]:
                tally["at_barrier"] += 1
            if found["on_roundabout"]:
                tally["on_roundabout"] += 1
            priced[group][role] = extent
            pending[(group, role)] = extent
            measured.append({"booth": group, "role": role, "extent": extent,
                             "km": None if found["metres"] is None else found["metres"] / 1000.0,
                             "size": found["size"], "blocker": found["blocker"],
                             "free": found["free"]})
            bp.write_state(args.out, priced, done_routes)
        if n % PROGRESS_EVERY == 0 or n == len(order):
            print(f"    {n}/{len(order)} booth(s), {len(measured)} measured,"
                  f" {len(unmeasured)} unmeasured", flush=True)
    return unbounded


def run(args):
    priced, done_routes = bp.load_state(args.out)
    traversable, resolve, position = bd.load_inventory(args.booths)
    gares = load_gares(args.gares)
    overrides = ov.load(args.overrides)
    bidirectional = {g for g, r in priced.items() if r["type"] == BIDIRECTIONAL}
    inside_nodes, _barriers, unsettled_sides = bd.load_sides(
        args.sides, bidirectional, bd.load_adjacent(args.booths))

    # A booth the override ignores is still a barrier on the ground. `ignore`
    # says "no route goes through this lane", which is right for pricing and
    # grouping and wrong here: traffic that came past one has paid, so the road
    # it merges onto is still tolled. ARGENTAN's exit ended at its barrier
    # because a ramp fed by such a booth looked like free road.
    toll_nodes = frozenset(traversable) | frozenset(overrides.ignored)

    work, skipped = wanted_roles(priced, overrides)
    stated = [(g, role, node) for g, role, node in publish_stated(priced, overrides)
              if COORD_OF[role] not in priced[g]]

    outstanding = [(g, role) for g, roles in work.items() for role in roles
                   if role not in priced[g]]
    # A role whose node is recorded but whose coordinates are not: the run that
    # derived it was interrupted before the positions pass. It wants a lookup,
    # not a derivation.
    unpositioned = {(g, role): priced[g][role]
                    for g, roles in work.items() for role in roles
                    if role in priced[g] and COORD_OF[role] not in priced[g]}
    total_roles = sum(len(r) for r in work.values())
    by_kind = collections.Counter(
        (priced[g]["type"], len(roles)) for g, roles in work.items())
    print(f"    {len(work)} booth(s) want {total_roles} extent(s);"
          f" {total_roles - len(outstanding)} already recorded,"
          f" {len(outstanding)} outstanding")
    print("    " + ", ".join(
        f"{n} {kind} x{count}" for (kind, count), n in sorted(by_kind.items())))
    print(f"    skipped: " + ", ".join(f"{n} {k}" for k, n in sorted(skipped.items()))
          + (f"; {len(stated)} stated by override" if stated else ""))
    if args.dry_run:
        return 0
    if unpositioned:
        print(f"    {len(unpositioned)} extent(s) recorded without a position")
    if not outstanding and not stated and not unpositioned:
        print("    nothing outstanding; no region derived")
        return 0

    started = time.monotonic()
    profile = read_profile(args.profile)
    blacklist = load_blacklist(args.blacklist)
    with open(args.booths, encoding="utf-8") as fh:
        inventory = yaml.safe_load(fh) or {}
    ways = carve(args.pbf, inventory, args.ways, args.drive_ways, args.cell_deg)
    blocked, counts = impassable_nodes(ways, profile, blacklist)
    print("    " + ", ".join(f"{v} {k}" for k, v in counts.items())
          + f" -> {len(blocked)} impassable node(s)", flush=True)
    graph = Graph(profile, blocked)
    graph.apply_file(ways, locations=True, idx="flex_mem")
    print(f"    graph: {graph.edges} edge(s),"
          f" {graph.ways_barred} way(s) barred to a car,"
          f" {len(graph.roundabout)} roundabout node(s)"
          f" in {time.monotonic() - started:.0f}s", flush=True)

    measured, unmeasured = [], []
    pending_position, wide_pending, wide_positions = {}, {}, {}
    by_booth = collections.defaultdict(list)
    for group, role in outstanding:
        by_booth[group].append(role)

    order = sorted(by_booth)
    if args.limit:
        order = order[:args.limit]
        print(f"    --limit {args.limit}: measuring {len(order)} booth(s)")

    tally = collections.Counter()
    unbounded = derive_pass(
        graph, order, by_booth, args, priced, done_routes, traversable, resolve,
        inside_nodes, measured, unmeasured, pending_position, tally,
        defer_unbounded=True, toll_nodes=toll_nodes,
        unsettled_sides=unsettled_sides)

    # The regions the first carve could not bound. A region that runs to a node
    # the graph stops at has been ended by the data rather than by the road, and
    # a booth on a motorway with no junction for miles genuinely reaches that
    # far. Those booths -- and only those -- get a carve three times as wide.
    if unbounded and args.wide_cell_deg > 0:
        booths = sorted({g for g, _role in unbounded})
        print(f"\n    {len(unbounded)} region(s) over {len(booths)} booth(s) ran"
              f" out of extract; carving {args.wide_cell_deg} deg around them",
              flush=True)
        coords = {g: position[g] for g in booths if g in position}
        # The first graph is eleven gigabytes and nothing below reads it. Freed
        # before the second is built, so the two never sit in memory together.
        graph = None
        gc.collect()
        wide = carve_wide(args.drive_ways, coords, args.wide_ways,
                          args.wide_cell_deg)
        wide_blocked, _counts = impassable_nodes(wide, profile, blacklist)
        wide_graph = Graph(profile, wide_blocked)
        wide_graph.apply_file(wide, locations=True, idx="flex_mem")
        print(f"    wider graph: {wide_graph.edges} edge(s)", flush=True)
        wide_by_booth = collections.defaultdict(list)
        for group, role in unbounded:
            wide_by_booth[group].append(role)
        derive_pass(
            wide_graph, sorted(wide_by_booth), wide_by_booth, args, priced,
            done_routes, traversable, resolve, inside_nodes, measured,
            unmeasured, wide_pending, tally, defer_unbounded=False,
            toll_nodes=toll_nodes, unsettled_sides=unsettled_sides)
        pending_position.update(wide_pending)
        wide_positions = positions_of(wide, set(wide_pending.values()))
        tally["widened"] = len(wide_pending)
        del wide_graph
    elif unbounded:
        for group, role in unbounded:
            unmeasured.append({"booth": group, "role": role,
                               "reason": "region ran out of extract"})

    # One pass for every position this run publishes. A node id alone cannot be
    # routed to -- the consumer takes coordinates -- and holding a position for
    # each of the extract's eighteen million nodes costs three gigabytes to
    # answer about a thousand questions.
    pending_position.update(unpositioned)
    pending_position.update({(g, role): node for g, role, node in stated})
    if pending_position:
        print(f"    reading {len(pending_position)} position(s) from {ways}",
              flush=True)
        found = positions_of(ways, set(pending_position.values()))
        found.update(wide_positions)
        for (group, role), node in sorted(pending_position.items()):
            latlon = found.get(node)
            if latlon is None:
                raise Abort(
                    f"node {node}, recorded as {role} for booth {group}, has no"
                    f" position in {ways}.\n"
                    f"       An extent nothing can route to is not usable. If an"
                    f" override states it, check the node id; otherwise this is"
                    f" a defect in the carve.")
            priced[group][role] = node
            priced[group][COORD_OF[role]] = bp.LatLon(
                [round(float(latlon[0]), 7), round(float(latlon[1]), 7)])
        bp.write_state(args.out, priced, done_routes)
    print(f"\n    derived in {(time.monotonic() - started) / 60:.1f} min")

    print(f"\n  measured extents ({len(measured)})")
    for line in measured_table(measured, gares):
        print(line)
    named, lines = named_table(measured, gares, args.report_km)
    if named:
        print(f"\n  beyond {args.report_km:.2f} km ({len(named)})")
        for line in lines:
            print(line)
    if unmeasured:
        print(f"\n  unmeasured ({len(unmeasured)})")
        for line in unmeasured_table(unmeasured, gares):
            print(line)

    bounded = sum(1 for r in measured if r["blocker"])
    known = sorted(r["km"] for r in measured if r["km"] is not None)
    print("\n  summary")
    print(f"    measured                    {len(measured)}")
    print(f"    ... bounded by a second booth   {bounded}")
    print(f"    ... ambiguous boundary          {tally['ambiguous']}")
    print(f"    ... ending at the barrier       {tally['at_barrier']}")
    print(f"    ... needing the wider carve     {tally['widened']}")
    print(f"    ... still unbounded there       {tally['truncated']}")
    print(f"    ... region on a roundabout      {tally['on_roundabout']}")
    print(f"    unmeasured                  {len(unmeasured)}")
    for reason, count in sorted(collections.Counter(
            r["reason"] for r in unmeasured).items()):
        print(f"      {reason:<24}  {count}")
    for kind, count in sorted(skipped.items()):
        print(f"    skipped: {kind:<19}  {count}")
    if known:
        print(f"    extent km  median {known[len(known) // 2]:6.2f}"
              f"   p90 {known[min(len(known) - 1, int(0.9 * len(known)))]:6.2f}"
              f"   max {known[-1]:7.2f}")
    if tally["on_roundabout"]:
        raise Abort(
            f"{tally['on_roundabout']} region(s) contain a roundabout node.\n"
            f"       A roundabout always carries an arm that goes somewhere"
            f" else, so it cannot lie inside a region every path through which"
            f" reaches the booth. This means the graph or the rule is wrong.")
    return 0


def publish_stated(priced, overrides):
    """The extents the override file states, without deriving any."""
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
    ap.add_argument("--pbf", required=True,
                    help="france-latest.osm.pbf, carved on first use")
    ap.add_argument("--ways", required=True,
                    help="the carved extent extract, made here if absent")
    ap.add_argument("--drive-ways", required=True,
                    help="the drive-class extract the carve is cut from")
    ap.add_argument("--boundary", choices=("inside", "free"), default="inside",
                    help="which side of the region to publish: the node one"
                         " segment inside it, or the free node just outside")
    ap.add_argument("--wide-ways", required=True,
                    help="the second, wider carve, cut around the booths the"
                         " first one cannot bound")
    ap.add_argument("--wide-cell-deg", type=float, default=WIDE_CELL_DEG,
                    metavar="D",
                    help=f"cell size for that second carve, 0 to disable it"
                         f" (default {WIDE_CELL_DEG})")
    ap.add_argument("--cell-deg", type=float, default=CELL_DEG, metavar="D",
                    help=f"carve cell size in degrees; the extract reaches at"
                         f" least this far beyond every booth"
                         f" (default {CELL_DEG})")
    ap.add_argument("--profile", required=True,
                    help="the routing profile, read for what a car may drive")
    ap.add_argument("--blacklist", required=True, help="nodes_blacklist.yaml")
    ap.add_argument("--overrides", required=True, help="hand-maintained booth overrides")
    ap.add_argument("--max-region", type=int, default=MAX_REGION, metavar="N",
                    help=f"report a booth whose region passes N nodes"
                         f" (default {MAX_REGION})")
    ap.add_argument("--report-km", type=float, default=REPORT_KM, metavar="KM",
                    help=f"name every extent this far from the barrier"
                         f" (default {REPORT_KM})")
    ap.add_argument("--dry-run", action="store_true",
                    help="enumerate the work and exit without reading the extract")
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
