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

Reach is measured in metres along the road.

Grouping decisions are purely topological. Distance is used in exactly one
place, and it decides nothing: a grid of cells around booths bounds how much of
the road network is loaded into memory. Whether two booths group is settled by
the (P, S) rule alone.
"""

import collections
import heapq
import json
import math
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

# highway values the car profile will drive.
ROUTABLE = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "service", "road", "track",
}
# Values that are one-way by default even without an explicit oneway tag.
IMPLICIT_ONEWAY = {"motorway", "motorway_link", "trunk_link"}


def carve_neighbourhoods(source_pbf, booth_coords, out_pbf, workdir):
    """Extract just the road network around booths.

    Cells are snapped to a shared grid and de-duplicated, so any two cells are
    either identical or edge-adjacent -- never partially overlapping. That keeps
    the multipolygon well-formed, which per-booth boxes would not.
    """
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
    """Directed adjacency over routable ways, weighted by length in metres."""

    def __init__(self):
        super().__init__()
        self.fwd = collections.defaultdict(dict)
        self.rev = collections.defaultdict(dict)

    def way(self, w):
        hv = w.tags.get("highway")
        if hv not in ROUTABLE:
            return
        oneway = w.tags.get("oneway")
        if oneway in ("yes", "true", "1"):
            fwd_ok, rev_ok = True, False
        elif oneway in ("-1", "reverse"):
            fwd_ok, rev_ok = False, True
        elif oneway == "no":
            fwd_ok, rev_ok = True, True
        elif w.tags.get("junction") in ("roundabout", "circular") or hv in IMPLICIT_ONEWAY:
            # Motorways and links are one-way by default; without this every
            # plaza lane looks bidirectional and P/S stop meaning anything.
            fwd_ok, rev_ok = True, False
        else:
            fwd_ok, rev_ok = True, True

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


def group_booths(booth_ids, plaza_pbf, max_m=MAX_REACH_M):
    """Return ({representative: [members]}, {member: representative}).

    Purely topological: a group is the largest set of booths sharing one common
    predecessor and one common successor.
    """
    print("    building local road graph")
    g = GraphBuilder()
    # locations=True resolves each way node's coordinate so segments can be
    # measured; without it every length would be zero.
    g.apply_file(plaza_pbf, locations=True, idx="flex_mem")
    booths = set(booth_ids)
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

    # A node shared by an implausible number of booths is a distant part of the
    # network rather than a plaza's split point.
    for members in by_pred.values():
        if not 2 <= len(members) <= MAX_GROUP:
            continue
        ordered = sorted(members)
        for i, x in enumerate(ordered):
            for y in ordered[i + 1:]:
                if find(x) != find(y) and succs[x] & succs[y]:
                    union(x, y)

    groups = collections.defaultdict(list)
    for b in booth_ids:
        groups[find(b)].append(b)
    groups = {rep: sorted(members) for rep, members in groups.items()}
    assigned = {b: rep for rep, members in groups.items() for b in members}

    return groups, assigned
