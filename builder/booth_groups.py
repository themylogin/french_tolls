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

# Every class the car profile gives a speed to. Used for one question only:
# what lies immediately beyond a booth. The through-road filter above is there
# to keep a car park barrier out of the inventory and to stop a plaza forecourt
# manufacturing a shared predecessor, and neither reason bears on a vehicle
# that has already reached the barrier and is about to leave it. Measured, the
# wider set names three more arcs over the whole inventory, all `service`.
DRIVE_CLASSES = THROUGH_CLASSES | {
    "unclassified", "residential", "living_street", "service",
    "winter_road", "ice_road",
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
        # booth node -> {neighbour: is the way reaching it two-way}. The sides
        # of a two-way booth, for the step that tells its entrance from its
        # exit. Collected here because this pass already reads every way the
        # question is about; a booth reached by both a one-way and a two-way
        # way keeps the two-way answer, since the restriction is what a role
        # claim rests on.
        self.adjacent = collections.defaultdict(dict)
        # Position of every node lying next to a booth on a through-class way.
        # `fwd` and `rev` carry the topology but not the geometry, and the
        # passage published for a booth no route reaches is two coordinates.
        # Kept only for the neighbours, since the whole node set of the carved
        # extract is millions of entries to answer a question about hundreds.
        self.side_coords = {}
        # booth node -> {node reached after passing it: its position}. One entry
        # per direction the booth can be left by, over DRIVE_CLASSES rather than
        # the through classes, and with the position because a consumer that has
        # to route across the arc cannot look a node id up anywhere.
        self.onward = collections.defaultdict(dict)

    def way(self, w):
        hv = w.tags.get("highway")
        if hv not in DRIVE_CLASSES:
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

        refs = [n.ref for n in w.nodes]
        located = {n.ref: (n.location.lat, n.location.lon)
                   for n in w.nodes if n.location.valid()}

        # What lies ahead of a booth. Collected before the through-road filter
        # below, and direction is taken from the tags as they stand: an override
        # that calls a two-way-tagged booth one-way corrects this step's
        # grouping, not the road, and the routing graph is built from the same
        # tags, so a vehicle can still leave by either side.
        for i, ref in enumerate(refs):
            if ref not in self.booths:
                continue
            for head in ((refs[i + 1] if fwd_ok and i + 1 < len(refs) else None),
                         (refs[i - 1] if rev_ok and i else None)):
                if head is None or head == ref:
                    continue
                # A node the first way to name it left unlocated must still take
                # a position from the next way that carries one.
                position = located.get(head)
                if position is not None or head not in self.onward[ref]:
                    self.onward[ref][head] = position

        if hv not in THROUGH_CLASSES:
            return

        if fwd_ok and rev_ok:
            for ref in refs:
                if ref in self.booths:
                    self.two_way.add(ref)

        for i, ref in enumerate(refs):
            if ref not in self.booths:
                continue
            for side in (refs[i - 1] if i else None,
                         refs[i + 1] if i + 1 < len(refs) else None):
                if side is None or side == ref:
                    continue
                # `or` and not `=`: two-way wins over one-way for this edge.
                self.adjacent[ref][side] = (
                    self.adjacent[ref].get(side, False) or (fwd_ok and rev_ok))
                if side in located:
                    self.side_coords[side] = located[side]

        nodes = [(ref, located[ref]) for ref in refs if ref in located]
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


def passages(graph, booths):
    """{booth: ((lat, lon), (lat, lon))} -- the node before it and the node after.

    For a booth that no route reaches. The pair is a leg through the booth,
    which is the only way left to ask the operator what gare it is.

    Direction is read off the uncontracted graph rather than off `adjacent`,
    which merges the two senses: `rev` holds the nodes the booth is reachable
    from and `fwd` the nodes reachable from it. On a way tagged `oneway=no`
    both hold both, and either ordering is a lawful passage.

    Where there is more than one candidate the smallest node id wins, so that
    regenerating an unchanged extract produces an unchanged inventory. The
    successor is the smallest id that is not already the predecessor: on a
    two-way way the same node stands in both lists, and taking it twice would
    build a leg that goes out and back rather than through.

    A booth missing either end has no way through it and is named rather than
    written with half a passage.
    """
    out = {}
    for booth in sorted(booths):
        ends = []
        for adj, role in ((graph.rev, "predecessor"), (graph.fwd, "successor")):
            candidates = [n for n in sorted(adj.get(booth, ()))
                          if n != booth and n in graph.side_coords
                          and n not in ends]
            if not candidates:
                raise ValueError(
                    f"booth {booth} is stated one-way by override but has no"
                    f" {role} distinct from its other side on a through-class"
                    f" way, so no leg can be built through it")
            ends.append(candidates[0])
        out[booth] = tuple(graph.side_coords[n] for n in ends)
    return out


class Locate(osmium.SimpleHandler):
    """Positions of named nodes, taken from the drivable ways carrying them."""

    def __init__(self, wanted):
        super().__init__()
        self.wanted = wanted
        self.found = {}

    def way(self, w):
        if w.tags.get("highway") not in DRIVE_CLASSES:
            return
        for n in w.nodes:
            if n.ref in self.wanted and n.ref not in self.found:
                if n.location.valid():
                    self.found[n.ref] = (n.location.lat, n.location.lon)


def locate(plaza_pbf, node_ids):
    """{node: (lat, lon)} for the named nodes the carved extract carries.

    A node is looked for on drivable ways only. A node the extract holds but no
    car can reach is not a lane of a plaza, and reporting a position for it
    would let a booth be stated somewhere no vehicle passes.
    """
    handler = Locate(set(node_ids))
    handler.apply_file(plaza_pbf, locations=True, idx="flex_mem")
    return handler.found


def onward_nodes(graph, booth_ids):
    """{booth: {node reached after passing it: its position}}, in key order.

    Written for every booth, whatever its type and whatever it charges. This
    step reads no price file, so it has no basis for answering the question for
    some booths and not others.

    A booth with nothing leading on from it is refused rather than written with
    an empty field. A booth is in the inventory because it lies on a through
    road, so a booth no vehicle can leave contradicts the rule that admitted it.

    A neighbour without a position is refused for the same reason the field
    carries positions at all: a consumer routing across the arc has nowhere to
    look a node id up.
    """
    out = {b: {n: p for n, p in sorted(graph.onward.get(b, {}).items())}
           for b in sorted(booth_ids)}
    blank = [b for b, heads in out.items() if not heads]
    if blank:
        raise ValueError(
            f"{len(blank)} booth(s) have no node a vehicle can reach from them:"
            f" {blank[:5]}.\n"
            f"       A booth is in the inventory because it lies on a through"
            f" road, so a booth with nothing leading on from it contradicts the"
            f" rule that admitted it.")
    unlocated = sorted((b, n) for b, heads in out.items()
                       for n, p in heads.items() if p is None)
    if unlocated:
        raise ValueError(
            f"{len(unlocated)} node(s) beyond a booth have no position in the"
            f" carved extract: {unlocated[:5]}.\n"
            f"       The field carries positions because a consumer routing"
            f" across the arc cannot look a node id up anywhere.")
    return out


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
                 isolated=None, one_way=None):
    """Return ({representative: [members]}, {member: representative}, {two-way},
    {two-way booth: {neighbour: is it reached by a one-way way}},
    {one-way-stated booth: (position before, position after)},
    {booth: {node reached after passing it: its position}}).

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

    # A way tagged `oneway=no` that is not two-way on the ground would otherwise
    # make its booth two coverage targets and keep it out of every group. The
    # override states the truth until the extract carries the fix.
    if one_way:
        stated = g.two_way & set(one_way)
        if stated:
            print(f"    {len(stated)} booth(s) stated one-way by override,"
                  f" against a two-way tag in the extract")
        g.two_way -= set(one_way)
        for booth in one_way:
            g.adjacent.pop(booth, None)

    # The passage is read before contraction, so it names the node genuinely
    # next to the booth rather than the next junction along. Every stated booth
    # is asked about, including one the through-road filter excluded: such a
    # booth has no leg to build and no inventory entry to carry one, and saying
    # so here is what tells the difference between a stale override and a booth
    # the operator simply does not report.
    passage = passages(g, set(one_way or ()))
    if passage:
        print(f"    {len(passage)} booth(s) carry a passage for the mapping step")

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

    two_way_booths = g.two_way & booths
    # Only a two-way booth has sides to tell apart, so only it carries them.
    sides = {b: {n: not tw for n, tw in sorted(g.adjacent[b].items())}
             for b in sorted(two_way_booths)}

    onward = onward_nodes(g, booth_ids)
    print(f"    {sum(len(h) for h in onward.values())} arc(s) leaving"
          f" {len(onward)} booth(s)")

    return groups, assigned, two_way_booths, sides, passage, onward
