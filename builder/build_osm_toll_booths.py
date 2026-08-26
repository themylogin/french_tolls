#!/usr/bin/env python3
"""Step 3 -- extract the toll booth inventory from the France PBF extract.

Two stages. `osmium tags-filter` (C++) reduces the ~4.7 GB extract to a few MB
in one streaming pass; pyosmium then reads that. Running the filter first keeps
the Python callback layer off the full extract, where it would spend minutes to
find a few thousand nodes.

The filtered extract is *kept*. It holds every booth and every endpoint
candidate from a single parse, so it doubles as the hand-off to step 4 -- the
booth inventory and the endpoint catalogue cannot drift apart, and the tag rules
live in exactly one place.

Toll booths that are parallel lanes of one plaza are grouped, since a route can
only ever pass through one lane. Each group is named by its smallest node id;
the rest become aliases. Grouping is topological, never distance-based -- see
booth_groups.py.

Outputs:
    <--out>       the published inventory: toll_booths + aliases
    <--filtered>  the internal hand-off to step 4
    <--plazas>    carved road network around booths, used for grouping
"""

import argparse
import collections
import json
import os
import subprocess
import sys

import osmium
import yaml

import booth_groups
import overrides

# A node is a toll booth iff it carries one of these tags. Nodes only: ways and
# relations carrying them are not toll booths.
BOOTH_TAGS = (("barrier", "toll_booth"), ("highway", "toll_gantry"))

# A node is an eligible route endpoint iff place is one of these.
#
# Beyond the obvious settlements: whole valleys and motorway interchange
# catchments have no city, town, or village in them, and a booth serving such an
# area then has no endpoint to anchor a route on. Measured on France: the Frejus
# ramp toll is crossed by 0 of 159,600 routes between city/town/village pairs,
# and by 250 once localities count.
PLACE_VALUES = ("city", "town", "village", "hamlet", "isolated_dwelling", "locality")

# Road classes a car cannot join from the land beside them. A place node that
# snaps onto one of these is not a place a trip can start: the route the engine
# returns begins in motorway traffic, leaves at the next interchange and comes
# back on the opposite carriageway, paying both sides of the first plaza it
# meets. Step 4 needs the *class* of the segment a candidate snapped to, and
# /nearest reports the segment's name and node ids but never its class -- so the
# ways are carried across the step boundary and the node ids matched against
# them there.
#
# `trunk` is deliberately absent: in France it covers ordinary two-way roads
# with property access as well as motorway-grade routes.
NO_ACCESS_CLASSES = ("motorway", "motorway_link", "trunk_link")


class LatLon(list):
    """A [lat, lon] pair, dumped inline rather than as two block items."""


yaml.SafeDumper.add_representer(
    LatLon,
    lambda dumper, data: dumper.represent_sequence(
        "tag:yaml.org,2002:seq", data, flow_style=True),
)


def run_tags_filter(pbf: str, filtered: str) -> None:
    """Reduce the full extract to booths + endpoint candidates.

    The `n/` prefix restricts matching to nodes, which is exactly the
    eligibility rule, so the filter doubles as the tag test.
    """
    if os.path.exists(filtered):
        # Derived from the source extract and the tag rules alone, so it cannot
        # go stale while the source is unchanged -- and the source is governed by
        # the same existence rule. Reusing it is what makes re-running this step
        # after an override edit cost a minute instead of repeating a pass over
        # 4.7 GB.
        print(f"==> reusing {filtered} ({os.path.getsize(filtered) / 1e6:.1f} MB)")
        return
    expressions = [f"n/{k}={v}" for k, v in BOOTH_TAGS]
    expressions.append("n/place=" + ",".join(PLACE_VALUES))

    tmp = filtered + ".part"
    # -f pbf is required: osmium infers the format from the file extension, and
    # the .part suffix used for the atomic rename hides it.
    cmd = ["osmium", "tags-filter", "--overwrite", "-f", "pbf",
           "-o", tmp, pbf, *expressions]
    print("==> " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    # Rename only on success: a partial filter output must never be mistaken
    # for a usable hand-off by step 4.
    os.replace(tmp, filtered)
    print(f"    filtered extract: {os.path.getsize(filtered) / 1e6:.1f} MB")


def run_no_access_filter(pbf: str, out: str) -> None:
    """Extract the ways of the classes a car cannot join from beside them.

    Filtered to three classes rather than every highway way: the question step 4
    asks is one yes/no test per candidate, and a node-to-class map for all of
    France would be a hundred million entries to answer it.
    """
    if os.path.exists(out):
        # Same reasoning as run_tags_filter: derived from the source extract and
        # a fixed class list, so it cannot go stale while the source is unchanged.
        print(f"==> reusing {out} ({os.path.getsize(out) / 1e6:.1f} MB)")
        return
    tmp = out + ".part"
    cmd = ["osmium", "tags-filter", "--overwrite", "-f", "pbf",
           "-o", tmp, pbf, "w/highway=" + ",".join(NO_ACCESS_CLASSES)]
    print("==> " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    os.replace(tmp, out)
    print(f"    no-access ways: {os.path.getsize(out) / 1e6:.1f} MB")


class Collector(osmium.SimpleHandler):
    """Single pass over the filtered extract."""

    def __init__(self):
        super().__init__()
        self.booths = {}  # node id -> (lat, lon)
        self.gantry = set()  # node ids tagged highway=toll_gantry
        self.places = {}  # node id -> (lat, lon, name or None)

    def node(self, n):
        tags = n.tags
        is_booth = any(tags.get(k) == v for k, v in BOOTH_TAGS)
        is_place = tags.get("place") in PLACE_VALUES
        if not (is_booth or is_place):
            return
        # A node with no usable location still counts as a booth for the
        # inventory, but cannot take part in the geometry below.
        loc = (n.location.lat, n.location.lon) if n.location.valid() else None
        if is_booth:
            # A node carrying both booth tags is still one booth.
            self.booths[n.id] = loc
            if tags.get("highway") == "toll_gantry":
                self.gantry.add(n.id)
        if is_place and loc is not None:
            self.places[n.id] = (loc[0], loc[1], tags.get("name"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pbf", required=True, help="source France extract")
    ap.add_argument("--filtered", required=True, help="filtered extract to keep")
    ap.add_argument("--out", required=True, help="booth inventory YAML")
    ap.add_argument("--plazas", required=True, help="carved plaza-neighbourhood extract")
    ap.add_argument("--excluded", required=True, help="booths dropped as off the through-road network")
    ap.add_argument("--overrides", required=True, help="hand-maintained booth overrides YAML")
    ap.add_argument("--no-access", required=True,
                    help="extract of ways a car cannot join, kept for step 4")
    args = ap.parse_args()

    if not os.path.exists(args.pbf):
        print(f"ERROR: extract not found: {args.pbf}", file=sys.stderr)
        return 1

    run_tags_filter(args.pbf, args.filtered)
    run_no_access_filter(args.pbf, args.no_access)

    print("==> reading filtered extract")
    collector = Collector()
    collector.apply_file(args.filtered)

    booth_ids = sorted(collector.booths)
    named = sum(1 for _, _, name in collector.places.values() if name)
    unlocated = [i for i, loc in collector.booths.items() if loc is None]
    print(f"    toll booths:         {len(booth_ids)}")
    print(f"    endpoint candidates: {len(collector.places)} ({named} named)")
    if unlocated:
        print(f"    booths with no usable location: {len(unlocated)}")

    print("==> grouping plaza lanes")
    located = {i: loc for i, loc in collector.booths.items() if loc is not None}
    booth_groups.carve_neighbourhoods(args.pbf, located, args.plazas, os.path.dirname(args.out))

    print("==> reading overrides")
    try:
        ov = overrides.load(args.overrides)
        overrides.check_against_extract(ov, set(booth_ids))
    except overrides.OverrideError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    ignored, forced = ov.ignored, ov.forced
    print(f"    {ov.summary()}")

    kept, dropped, _ = booth_groups.classify(booth_ids, args.plazas)
    # An ignored booth is treated as absent from the network, so it leaves before
    # grouping. It is still recorded as excluded: the inventory and the exclusion
    # report together account for every booth in the extract, and a booth that
    # vanished from both would hide the removal.
    kept = [b for b in kept if b not in ignored]
    for b in ignored:
        dropped.setdefault(b, []).insert(0, "<ignored by override>")
    print(f"    on a through road: {len(kept)}   excluded: {len(dropped)}")
    reasons = collections.Counter("|".join(v) for v in dropped.values())
    for reason, count in reasons.most_common():
        print(f"      {count:4d}  {reason}")
    with open(args.excluded, "w", encoding="utf-8") as fh:
        json.dump({str(k): v for k, v in sorted(dropped.items())}, fh, indent=2)
        fh.write("\n")

    try:
        groups, aliases, bidirectional, sides, passage = booth_groups.group_booths(
            kept, args.plazas, forced=forced, isolated=ov.isolated,
            one_way=ov.one_way)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # A gare stated by hand is consumed by step 5, but its target has to be a
    # group representative and only this step knows the grouping.
    misplaced = {b: assigned for b, assigned in
                 ((b, aliases.get(b)) for b in sorted(ov.vinci))
                 if assigned is not None and assigned != b}
    absent = [b for b in sorted(ov.vinci) if b not in groups and b not in aliases]
    if misplaced or absent:
        for b, assigned in misplaced.items():
            print(f"ERROR: override for booth {b}: vinci names a booth that the"
                  f" grouping rules made a member of group {assigned}, so it is"
                  f" not a group to attach a gare to", file=sys.stderr)
        for b in absent:
            print(f"ERROR: override for booth {b}: vinci names a booth that is"
                  f" not in the inventory", file=sys.stderr)
        return 1

    representatives = sorted(groups)
    alias_map = {b: rep for b, rep in sorted(aliases.items()) if b != rep}

    # Each entry carries the node's *own* position, aliases included. Downstream
    # matching runs against individual lanes: the representative is only the
    # smallest id in its group, and group members lie a median 15 m and up to
    # several hundred metres apart, so an alias that echoed its representative's
    # position would be worse than useless.
    missing = [i for i in [*representatives, *alias_map] if i not in located]
    if missing:
        print(f"ERROR: {len(missing)} retained booth(s) have no location and"
              f" cannot be published: {missing[:5]}", file=sys.stderr)
        return 1

    # `type` records what makes a booth charge differently from a plain one-way
    # lane. A lane a route drives one way only carries no type at all.
    #
    # `bidirectional` is a booth a route can drive through either way, which
    # makes it two tolls rather than one. Position alone cannot show that, and a
    # consumer needs it to know the booth is two coverage targets.
    #
    # `gantry` is a free-flow point -- a portal over the carriageway rather than
    # a lane a car stops in. It charges per section travelled, so one gantry
    # starts a section when another follows on the same journey and is a charge
    # of its own when none does. Nothing but the OSM tag says which booths work
    # that way, and a consumer cannot tell from the charge alone.
    both = sorted(collector.gantry & bidirectional)
    if both:
        print(f"ERROR: {len(both)} booth(s) are a gantry and two-way at once,"
              f" and `type` holds one value: {both[:5]}", file=sys.stderr)
        return 1

    # `adjacent_nodes` gives the nodes either side of a two-way booth, each
    # mapped to whether the way reaching it is one-way. Only step 4 can say
    # which side is the entrance, by driving it; this says which nodes are
    # candidates and which of them a one-way restriction already settles.
    #
    # Step 4 consumes it in memory and never writes back here, so what remains
    # unconsumed is read off by subtracting the sides it classified from this.
    # `passage` gives the node before a booth and the node after it, as
    # positions rather than ids. It is written only for a booth the override
    # file types `enter`, `exit`, or `passthrough` -- the booths at a border,
    # which no route between two French places reaches. Step 5 forms a leg from
    # the two positions with the booth's own between them and asks the operator
    # what gare it is. The booth's position is not repeated here: the entry
    # already carries it as `latlon`, and two copies could disagree.
    def entry(node_id):
        lat, lon = located[node_id]
        out = {"latlon": LatLon([round(lat, 7), round(lon, 7)])}
        if node_id in collector.gantry:
            out["type"] = "gantry"
        elif node_id in bidirectional:
            out["type"] = "bidirectional"
            out["adjacent_nodes"] = dict(sides.get(node_id) or {})
        if node_id in passage:
            out["passage"] = [LatLon([round(a, 7), round(b, 7)])
                              for a, b in passage[node_id]]
        return out

    booths_out = {i: entry(i) for i in representatives}
    aliases_out = {}
    for alias, rep in alias_map.items():
        aliases_out[alias] = {"parent_id": rep, **entry(alias)}

    tmp = args.out + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(
            {"toll_booths": booths_out, "aliases": aliases_out},
            fh, default_flow_style=False, sort_keys=False, width=100,
        )
    os.replace(tmp, args.out)

    named = collections.Counter()
    for b in representatives:
        if b not in bidirectional:
            continue
        kinds = collections.Counter((sides.get(b) or {}).values())
        named[(kinds[True], kinds[False])] += 1
    print(f"    {sum(named.values())} two-way booth(s), by (one-way, two-way)"
          f" neighbour count: "
          + ", ".join(f"{k}: {n}" for k, n in sorted(named.items())))

    sizes = collections.Counter(len(m) for m in groups.values())
    print("    group size distribution")
    for size in sorted(sizes):
        print(f"      {size:3d} booth(s): {sizes[size]:5d} group(s)"
              f"  [{size * sizes[size]} booths]")
    accounted = sum(size * count for size, count in sizes.items())
    print(f"    {len(representatives)} groups covering {accounted} booths"
          f" ({len(alias_map)} aliases)")
    if accounted != len(kept):
        print("ERROR: grouping does not account for every booth", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
