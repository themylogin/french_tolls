#!/usr/bin/env python3
"""Group toll booths that are parallel lanes of the same plaza.

A plaza splits the mainline into parallel lanes and rejoins it:

                     ┌──[booth a]──┐
    ─────────── P ───┼──[booth b]──┼─── S ───────────
                     └──[booth c]──┘

Booths are alternatives when they share a common predecessor P *and* a common
successor S within a tight radius, where the path P -> booth -> S passes through
no other toll booth. A group is the transitive closure of that relation, so the
outer lanes of a wide plaza join through the lanes between them.

The radius has to be tight, or two booths eventually "reconverge" by looping
round an interchange, which merges a mainline barrier with a slip-road barrier
-- booths one route drives straight through, one after the other.

Reach is measured in metres along the road, over the *through* road classes
only -- the graph a route between two place nodes actually sees. See
GraphBuilder for why service roads have to stay out of it.

A booth on a two-way through road is never grouped. The (P, S) rule separates
opposite directions by way of one-way restrictions, and a bidirectional slip
road has none.

Grouping is otherwise purely topological, with one exception: a hand-maintained
override may force a booth into a named group. Some booths cannot be grouped
from the data at all -- a lane whose only approach is tagged `service` is
invisible to a graph built from through roads.

Distance is used in exactly one
place, and it decides nothing: a grid of cells around booths bounds how much of
the road network is loaded into memory. Whether two booths group is settled by
the (P, S) rule alone.
"""

import collections
import heapq
import json
import math
import os
import subprocess

import osmium

# How far back/forward to look for the shared predecessor and successor, along
# the road. Deliberately tight: parallel lanes diverge and reconverge within a
# plaza's own length, while a generous radius lets two booths "reconverge" by
# looping right round an interchange, merging a mainline barrier with a
# slip-road barrier -- booths a single route drives through one after the other.
MAX_REACH_M = 1000.0
CELL_DEG = 0.02         # ~2.2 km grid; loading bound only, never a grouping input

# Largest plausible number of lanes at one plaza. Used only to skip nodes that
# an implausible number of booths share -- those are distant parts of the
# network, and every real plaza is still witnessed by its own tight (P, S).
MAX_GROUP = 128

# Road classes a through route between two towns actually uses. Booths outside
# these classes are excluded from the inventory: a car route from one place node
# to another will never traverse a car park barrier on a `service` road, a
# `footway`, or a way tagged `proposed`, so counting them as coverage targets
# only manufactures permanent misses.
THROUGH_CLASSES = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link",
}

# Values that are one-way by default even without an explicit oneway tag.
IMPLICIT_ONEWAY = {"motorway", "motorway_link", "trunk_link"}


def two_way(highway, oneway, junction=None):
    """Whether the car profile can drive this way in both directions.

    The single place that decides direction, so the graph edges and the
    `bidirectional` flag in the inventory can never disagree.
    """
    if oneway in ("yes", "true", "1", "-1", "reverse"):
        return False
    if oneway == "no":
        return True
    if junction in ("roundabout", "circular") or highway in IMPLICIT_ONEWAY:
        return False
    return True


def carve_neighbourhoods(source_pbf, booth_coords, out_pbf, workdir):
    """Extract just the road network around booths.

    Cells are snapped to a shared grid and de-duplicated, so any two cells are
    either identical or edge-adjacent -- never partially overlapping. That keeps
    the multipolygon well-formed, which per-booth boxes would not.
    """
    if os.path.exists(out_pbf):
        # Depends on the source extract and the booth positions in it, neither of
        # which an override can change. See run_tags_filter for why this is safe.
        print(f"    reusing {out_pbf} ({os.path.getsize(out_pbf) / 1e6:.1f} MB)")
        return out_pbf

    cells = set()
    for lat, lon in booth_coords.values():
        cx, cy = int(math.floor(lat / CELL_DEG)), int(math.floor(lon / CELL_DEG))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cells.add((cx + dx, cy + dy))

    polys = []
    for cx, cy in sorted(cells):
        lat0, lon0 = cx * CELL_DEG, cy * CELL_DEG
        lat1, lon1 = lat0 + CELL_DEG, lon0 + CELL_DEG
        polys.append([[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]])

    geojson = {"type": "Feature", "properties": {},
               "geometry": {"type": "MultiPolygon", "coordinates": polys}}
    poly_path = f"{workdir}/plaza_cells.geojson"
    with open(poly_path, "w", encoding="utf-8") as fh:
        json.dump(geojson, fh)

    print(f"    carving {len(cells)} grid cells around {len(booth_coords)} booths")
    subprocess.run(
        ["osmium", "extract", "--overwrite", "-p", poly_path,
         "-s", "smart", "-f", "pbf", "-o", out_pbf, source_pbf],
        check=True,
    )
    return out_pbf


class BoothClasses(osmium.SimpleHandler):
    """highway values of every way each booth node belongs to."""

    def __init__(self, booths):
        super().__init__()
        self.booths = booths
        self.classes = collections.defaultdict(set)

    def way(self, w):
        hv = w.tags.get("highway")
        if not hv:
            return
        for n in w.nodes:
            if n.ref in self.booths:
                self.classes[n.ref].add(hv)


def classify(booth_ids, plaza_pbf):
    """Split booths into those on a through road and those not, with reasons."""
    handler = BoothClasses(set(booth_ids))
    handler.apply_file(plaza_pbf)
    kept, dropped = [], {}
    for b in booth_ids:
        values = handler.classes.get(b, set())
        if values & THROUGH_CLASSES:
            kept.append(b)
        else:
            dropped[b] = sorted(values) or ["<no highway way>"]
    return kept, dropped, handler.classes


def segment_m(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(math.sqrt(h))


class GraphBuilder(osmium.SimpleHandler):
    """Directed adjacency over through roads, weighted by length in metres.

    Only the classes a route between two place nodes can traverse -- the same
    set the through-road filter keeps booths for. Admitting `service` and
    `track` would put a toll plaza's own maintenance roads in the graph, and
    those connect every lane to every other lane and to the adjoining slip
    roads. At Saint-Michel-de-Maurienne that manufactured a shared predecessor
    between the ramp gare and the mainline barrier, reachable only by twenty
    three-metre hops across the forecourt through an `access=private` way.
    Access tags are not read at all, so the class filter is the only defence.
    """

    def __init__(self, booths=frozenset()):
        super().__init__()
        self.fwd = collections.defaultdict(dict)
        self.rev = collections.defaultdict(dict)
        self.booths = booths
        self.two_way = set()  # booth nodes lying on a two-way through road

    def way(self, w):
        hv = w.tags.get("highway")
        if hv not in THROUGH_CLASSES:
            return
        oneway = w.tags.get("oneway")
        if oneway in ("-1", "reverse"):
            fwd_ok, rev_ok = False, True
        elif two_way(hv, oneway, w.tags.get("junction")):
            fwd_ok, rev_ok = True, True
        else:
            # Motorways and links are one-way by default; without this every
            # plaza lane looks bidirectional and P/S stop meaning anything.
            fwd_ok, rev_ok = True, False

        if fwd_ok and rev_ok:
            for n in w.nodes:
                if n.ref in self.booths:
                    self.two_way.add(n.ref)

        nodes = [(n.ref, (n.location.lat, n.location.lon))
                 for n in w.nodes if n.location.valid()]
        for (a, pa), (b, pb) in zip(nodes, nodes[1:]):
            if a == b:
                continue
            length = segment_m(pa, pb)
            if fwd_ok:
                self._link(self.fwd, a, b, length); self._link(self.rev, b, a, length)
            if rev_ok:
                self._link(self.fwd, b, a, length); self._link(self.rev, a, b, length)

    @staticmethod
    def _link(adj, a, b, length):
        # Parallel ways between the same nodes: keep the shorter.
        if length < adj[a].get(b, math.inf):
            adj[a][b] = length


def significant_nodes(graph, booths):
    """Booths plus true junctions. Degree-2 geometry nodes are contracted away.

    Degree is counted over *distinct neighbours*, ignoring direction: on a
    two-way road every interior node has both its neighbours in fwd and in rev,
    so testing len(fwd) == 1 would collapse nothing.
    """
    keep = set(booths)
    for n in set(graph.fwd) | set(graph.rev):
        neighbours = set(graph.fwd.get(n, ())) | set(graph.rev.get(n, ()))
        if len(neighbours) != 2:
            keep.add(n)
    return keep


def contract(adj, keep):
    """Collapse chains of unkept nodes, summing their length in metres."""
    out = collections.defaultdict(dict)
    for start in keep:
        for first, first_len in adj.get(start, {}).items():
            prev, cur, total, guard = start, first, first_len, 0
            while cur not in keep and guard < 10000:
                # Carry on through the chain, ignoring the way we came from --
                # on a two-way road adj[cur] holds both neighbours.
                onward = {n: w for n, w in adj.get(cur, {}).items() if n != prev}
                if len(onward) != 1:
                    break
                nxt, step = next(iter(onward.items()))
                prev, cur, total = cur, nxt, total + step
                guard += 1
            if cur in keep and cur != start and total < out[start].get(cur, math.inf):
                out[start][cur] = total
    return out


def reachable(adj, start, booths, max_m):
    """Nodes within `max_m` metres along the road, never passing through
    another booth."""
    best = {start: 0.0}
    heap = [(0.0, start)]
    seen = set()
    while heap:
        dist, node = heapq.heappop(heap)
        if dist > best.get(node, math.inf):
            continue
        for other, length in adj.get(node, {}).items():
            step = dist + length
            if step > max_m or step >= best.get(other, math.inf):
                continue
            best[other] = step
            seen.add(other)
            # Stop at another booth: the path P -> booth -> S must contain
            # exactly one booth.
            if other not in booths:
                heapq.heappush(heap, (step, other))
    seen.discard(start)
    return seen


def group_booths(booth_ids, plaza_pbf, max_m=MAX_REACH_M, forced=None,
                 isolated=None):
    """Return ({representative: [members]}, {member: representative}, {two-way}).

    Topological, with two exceptions.

    `forced` maps a booth to a booth whose group it must join whatever the
    topology says. Some booths cannot be grouped from the data -- a lane whose
    only approach is tagged `service` is invisible to a graph built from through
    roads -- and the alternative to stating those by hand is a heuristic that
    misfires elsewhere.

    `isolated` is the opposite: booths that stay in a group of their own. The
    topological rule can be right that two lanes are alternatives and still be
    wrong about the consequence, because the operator sometimes charges two
    lanes of one plaza as different gares. Grouping them makes one coverage
    target out of two tolls, and no route can then pay both without the mapping
    step reporting one gare twice.
    """
    print("    building local road graph")
    booths = set(booth_ids)
    g = GraphBuilder(booths)
    # locations=True resolves each way node's coordinate so segments can be
    # measured; without it every length would be zero.
    g.apply_file(plaza_pbf, locations=True, idx="flex_mem")
    keep = significant_nodes(g, booths)
    fwd = contract(g.fwd, keep)
    rev = contract(g.rev, keep)
    print(f"    graph: {len(keep)} significant nodes after contraction")

    preds = {b: reachable(rev, b, booths, max_m) for b in booth_ids}
    succs = {b: reachable(fwd, b, booths, max_m) for b in booth_ids}

    # Two booths are alternatives when they share a predecessor *and* a
    # successor within the tight radius. Grouping is the transitive closure of
    # that relation: a wide plaza fans out and merges in stages, so its outer
    # lanes are only related through the ones between them, but every link in
    # that chain is a genuine parallel pair.
    #
    # Transitivity is safe precisely because the radius is tight -- two distinct
    # plazas never form a link to chain through.
    by_pred = collections.defaultdict(set)
    for b in booth_ids:
        for p in preds[b]:
            by_pred[p].add(b)

    parent = {b: b for b in booth_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[max(rx, ry)] = min(rx, ry)

    # A booth on a two-way road is never anyone's alternative. The (P, S) rule
    # keeps opposite directions apart by way of one-way restrictions, and a
    # bidirectional slip road has none -- so the entry gare and the exit gare of
    # one interchange would otherwise merge into a single coverage target.
    print(f"    {len(g.two_way)} booth(s) on a two-way through road, never grouped")

    # A node shared by an implausible number of booths is a distant part of the
    # network rather than a plaza's split point.
    # A booth held out by hand takes no part in the relation at all, in either
    # position. Excluding it here rather than unpicking a group afterwards is
    # what keeps it out: grouping is a transitive closure, so a booth left in
    # the relation would still chain two of its neighbours together.
    isolated = set(isolated or ())
    if isolated:
        print(f"    {len(isolated)} booth(s) kept out of every group by override")

    for members in by_pred.values():
        if not 2 <= len(members) <= MAX_GROUP:
            continue
        ordered = sorted(members)
        for i, x in enumerate(ordered):
            if x in g.two_way or x in isolated:
                continue
            for y in ordered[i + 1:]:
                if y in g.two_way or y in isolated:
                    continue
                if find(x) != find(y) and succs[x] & succs[y]:
                    union(x, y)

    # Forced membership is applied last, against the grouping the rules produced.
    # The target must be a representative in that grouping: if the rules made it
    # an alias of some other group, the group the override points at does not
    # exist and the entry has gone stale.
    for child, target in sorted((forced or {}).items()):
        if child in isolated:
            raise ValueError(
                f"override parent_id: booth {child} states parent_id: null and"
                f" cannot also be forced into the group of {target}")
        if child not in parent:
            raise ValueError(
                f"override parent_id: booth {child} is not in the inventory")
        if target not in parent:
            raise ValueError(
                f"override parent_id: booth {child} names parent {target}, "
                f"which is not in the inventory")
        if find(target) != target:
            raise ValueError(
                f"override parent_id: booth {child} names parent {target}, "
                f"which the grouping rules made a member of group {find(target)}, "
                f"so there is no group {target} to join")
        # A group cannot be split by decree, so the child brings its own group.
        union(child, target)

    groups = collections.defaultdict(list)
    for b in booth_ids:
        groups[find(b)].append(b)
    groups = {rep: sorted(members) for rep, members in groups.items()}
    assigned = {b: rep for rep, members in groups.items() for b in members}

    return groups, assigned, g.two_way & booths
