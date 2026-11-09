#!/usr/bin/env python3
"""Patch the routing profile: blacklisted nodes, and gates off the through-roads.

A blacklisted node is one the map is wrong about: a connection that is not
there on the ground. Every consumer of the router used to discard routes that
crossed one, which answers the wrong question. A filter establishes that the
*fastest* route is undrivable; it never asks what the fastest drivable route
is. So a booth whose only approach in the graph crossed a defect became
unreachable rather than reached another way.

Making the node impassable in the profile asks the question that was meant. The
router routes around it, every step downstream trusts what it gets back, and
three separate filters disappear.

The mechanism is the one the profile already uses for a `barrier=*` node it does
not whitelist -- `obstacle_map:add(node, Obstacle.new(obstacle_type.barrier))`
-- applied before any tag is read. Impassable rather than merely expensive: a
penalty would make the node a last resort, and "not there on the ground" is not
a last resort.

The second rule is about gates. The stock profile lets any vehicle through a
`barrier=gate` or `barrier=lift_gate` node for a fixed penalty, wherever that
gate stands. On a service road, a driveway or a track it is locked, so the
router leaves a toll road by an access track and returns a route nobody can
drive. A gate keeps the penalty only where an allowed highway class carries it;
everywhere else it becomes the same impassable barrier the profile already
makes of every barrier value it does not whitelist.

The profile cannot decide that on its own: `process_node` sees a node and no
way, `way:get_nodes()` yields node references without tags, and osrm-extract
holds one Lua state per thread, so nothing learned in the node pass survives
into the way pass. So the answer is scanned out of the same extract the graph
is built from and handed to the profile as a table of ids.

The open gates are listed rather than the closed ones. A gate the scan does not
reach stays shut, which is the safe direction for a rule that says these gates
are locked -- and it is the smaller table by a factor of seventeen.

A gate the class rule leaves open can still carry `locked=yes`. That gate is a
last resort, not a barrier. A route that starts or ends behind it crosses it.
A route that only passes by goes around. The profile already treats a way
tagged `access=private` like this, but it has no such flag for a node. So the
node pass adds a second obstacle to the gate, with no duration and the
maximum turn weight. The turn pass reads that weight in the profile's own
obstacle loop and raises the turn weight to it. The travel time keeps the
stock penalty.

The pristine profile is left beside the patched one so the two can be compared,
and the image itself is never touched.

Outputs:
    <--out>  the patched profile
"""

import argparse
import os
import re
import sys
import time

import osmium
import yaml

# The anchor the injected check goes after. Matched rather than assumed so a
# profile that has moved on announces itself instead of being patched wrongly.
NODE_HOOK = "function process_node(profile, node, result, relations)\n"

BEGIN = "-- >>> nodes_blacklist, injected by builder/patch_car_profile.py"
END = "-- <<< nodes_blacklist"

# The gate rule's anchor, matched for the same reason. The check goes after it,
# on the penalty rather than on the barrier: everything below is stock, so a
# closed gate falls through the profile's own `not barrier_penalty` arm and the
# `Obstacle.new(obstacle_type.gate, ...)` line below is skipped along with it.
PENALTY_HOOK = "      local barrier_penalty = profile.barrier_penalties[barrier]\n"

GATE_BEGIN = "-- >>> gates_on_through_roads, injected by builder/patch_car_profile.py"
GATE_END = "-- <<< gates_on_through_roads"

# The locked gate's two anchors in process_turn. The obstacle weight is read in
# the stock loop because a second `obstacle_map:get` on every turn costs
# osrm-extract 23% more peak memory, and France then no longer fits. The weight
# is applied before the routability block, because the line above that block
# sets the turn weight from the duration and would erase a weight raised earlier.
OBSTACLE_HOOK = "  for _, obs in pairs(obstacle_map:get(turn.from, turn.via)) do\n"
TURN_HOOK = "  if profile.properties.weight_name == 'routability' then\n"

# The classes that keep a gate open. A gate carried by one of them is on a road
# the public drives; a gate on anything else -- service, track, driveway, path
# -- is locked, whatever the map says about the way beyond it.
ALLOWED_HIGHWAY = frozenset({
    "motorway", "motorway_link",
    "trunk", "trunk_link",
    "primary", "primary_link",
    "secondary", "secondary_link",
    "tertiary", "tertiary_link",
    "unclassified",
    "residential",
    "living_street",
})

# What a sorted PBF says in its header. The scan is one pass, which is only
# complete because every node precedes every way; an unsorted file would yield
# a short open set, and short means gates closed -- the direction that does not
# announce itself.
SORTED = "Type_then_ID"


class Abort(Exception):
    """A profile that does not look like the one this patch was written for."""


def load_blacklist(path):
    """The node ids, or an empty list when the file is absent.

    Absent is not an error: a tree with nothing to blacklist is a tree that
    wants the stock profile, and saying so with a missing file is clearer than
    an empty one.
    """
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    if not isinstance(doc, dict):
        raise Abort(f"{path}: expected a mapping, got {type(doc).__name__}")
    unknown = sorted(set(doc) - {"nodes_blacklist"})
    if unknown:
        raise Abort(f"{path}: unknown top-level key(s) {', '.join(unknown)};"
                    f" expected nodes_blacklist")
    listed = doc.get("nodes_blacklist")
    if listed is None:
        return []
    if not isinstance(listed, list):
        raise Abort(f"{path}: nodes_blacklist must be a list, got"
                    f" {type(listed).__name__}")
    out = []
    for value in listed:
        if not isinstance(value, int) or isinstance(value, bool):
            raise Abort(f"{path}: {value!r} is not an OSM node id")
        out.append(value)
    return sorted(set(out))


def penalised_barriers(source):
    """The `barrier=*` values the profile lets a vehicle through for a penalty.

    Read out of the profile rather than restated here. An image that penalises
    a third value has that value governed by the rule; one that penalises none
    has no rule to inject, and says so instead of being patched into silence.
    """
    match = re.search(r"barrier_penalties\s*=\s*\{(.*?)\}", source, re.S)
    if match is None:
        raise Abort("no barrier_penalties table in the profile;"
                    " the gate rule has nothing to govern")
    values = re.findall(r"^\s*(?:\[\s*['\"]([^'\"]+)['\"]\s*\]|([A-Za-z_][\w]*))\s*=",
                        match.group(1), re.M)
    values = sorted({bracketed or bare for bracketed, bare in values})
    if not values:
        raise Abort("the profile's barrier_penalties table is empty;"
                    " the gate rule has nothing to govern")
    return values


class GateScan(osmium.SimpleHandler):
    """Which of the extract's gate nodes an allowed highway class carries.

    One pass. Every node precedes every way in a sorted file, so the set of
    gates is complete before the first way arrives -- which the caller checks
    the header for rather than trusting.

    Any allowed way is enough, rather than every way. A gate tagged on the node
    where a driveway meets a residential street would otherwise cut the street,
    which is a worse error than leaving the driveway open -- and the driveway
    is already discouraged by its class and usually closed by its access tag.
    """

    def __init__(self, barriers):
        super().__init__()
        self.barriers = frozenset(barriers)
        self.gates = set()
        self.open = set()

    def node(self, n):
        if n.tags.get("barrier") in self.barriers:
            self.gates.add(n.id)

    def way(self, w):
        if w.tags.get("highway") not in ALLOWED_HIGHWAY:
            return
        gates, opened = self.gates, self.open
        for ref in w.nodes:
            if ref.ref in gates:
                opened.add(ref.ref)


def scan_gates(path, barriers):
    """(every gate node in the extract, the ones an allowed class carries)."""
    reader = osmium.io.Reader(path)
    try:
        sorting = reader.header().get("sorting")
    finally:
        reader.close()
    if sorting != SORTED:
        raise Abort(f"{path}: header says sorting={sorting!r}, expected"
                    f" {SORTED!r}\n"
                    f"       The scan is one pass and needs every node before"
                    f" every way. An unsorted file would leave gates out of the"
                    f" open set, which closes roads.")
    scan = GateScan(barriers)
    scan.apply_file(path)
    return scan.gates, scan.open


def render_gates(gates, opened):
    """The Lua the gate rule injects, or nothing when the extract has no gate.

    An extract with no gate at all wants the stock profile. An extract with
    gates and none of them open does not: that is a real answer, and the empty
    table that says so closes every one of them.
    """
    if not gates:
        return "", "", "", ""
    table = "\n".join(f"  [{n}] = true," for n in sorted(opened))
    preamble = (
        f"{GATE_BEGIN}\n"
        f"-- The gate and lift_gate nodes an allowed highway class carries, out\n"
        f"-- of {len(gates)} in the extract. Every other one is locked on the\n"
        f"-- ground, so the profile below drops its penalty and it becomes an\n"
        f"-- impassable barrier like any other barrier value.\n"
        f"local open_gate_nodes = {{\n{table}\n}}\n"
        f"{GATE_END}\n\n")
    check = (
        f"      {GATE_BEGIN}\n"
        f"      if barrier_penalty and not open_gate_nodes[node:id()] then\n"
        f"        barrier_penalty = nil\n"
        f"      end\n"
        f"      if barrier_penalty and node:get_value_by_key('locked') == 'yes' then\n"
        f"        obstacle_map:add(node, Obstacle.new(obstacle_type.gate,\n"
        f"                                            obstacle_direction.both, 0,\n"
        f"                                            constants.max_turn_weight))\n"
        f"      end\n"
        f"      {GATE_END}\n")
    obstacle_loop = (
        f"  {GATE_BEGIN}\n"
        f"  local obstacle_weight = 0\n"
        f"{OBSTACLE_HOOK}"
        f"    obstacle_weight = math.max(obstacle_weight, obs.weight)\n"
        f"  {GATE_END}\n")
    turn_check = (
        f"  {GATE_BEGIN}\n"
        f"  turn.weight = math.max(turn.weight, obstacle_weight)\n"
        f"  {GATE_END}\n")
    return preamble, check, obstacle_loop, turn_check


def render(nodes):
    """The Lua the patch injects.

    The count is printed as each node is met rather than tallied at the end:
    osrm-extract has no hook that runs after the node pass, and a line per node
    is what makes a stale entry visible -- one that never prints is one the
    extract no longer contains.
    """
    if not nodes:
        return "", ""
    table = "\n".join(f"  [{n}] = true," for n in nodes)
    preamble = (
        f"{BEGIN}\n"
        f"-- Nodes the map is wrong about: a connection that is not there on the\n"
        f"-- ground. Impassable here, so no route can use one -- rather than\n"
        f"-- filtered out of routes afterwards, which only ever established that\n"
        f"-- the fastest route was undrivable.\n"
        f"local blacklisted_nodes = {{\n{table}\n}}\n"
        f"{END}\n\n")
    check = (
        f"  {BEGIN}\n"
        f"  if blacklisted_nodes[node:id()] then\n"
        f"    print('nodes_blacklist: node ' .. node:id() .. ' is impassable')\n"
        f"    obstacle_map:add(node, Obstacle.new(obstacle_type.barrier))\n"
        f"    return\n"
        f"  end\n"
        f"  {END}\n")
    return preamble, check


def patch(source, nodes, gates=(), opened=()):
    if BEGIN in source or GATE_BEGIN in source:
        raise Abort("the profile is already patched")
    for hook in (NODE_HOOK, PENALTY_HOOK, OBSTACLE_HOOK, TURN_HOOK):
        if source.count(hook) != 1:
            raise Abort(
                f"expected exactly one {hook.strip()!r} in the profile,"
                f" found {source.count(hook)}\n"
                f"       The profile has changed shape; re-read it before patching.")

    preamble, check = render(nodes)
    gate_preamble, gate_check, obstacle_loop, turn_check = render_gates(gates, opened)
    if not preamble and not gate_preamble:
        return source

    # After the requires and before the first function, so the tables are in
    # scope everywhere and nothing above them has run yet.
    anchor = re.search(r"^(?=function |local function )", source, re.M)
    if anchor is None:
        raise Abort("no top-level function to place the injected tables before")
    at = anchor.start()
    source = source[:at] + preamble + gate_preamble + source[at:]
    if check:
        source = source.replace(NODE_HOOK, NODE_HOOK + check, 1)
    if gate_check:
        source = source.replace(PENALTY_HOOK, PENALTY_HOOK + gate_check, 1)
        source = source.replace(OBSTACLE_HOOK, obstacle_loop, 1)
        source = source.replace(TURN_HOOK, turn_check + TURN_HOOK, 1)
    return source


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True, help="the pristine car.lua")
    ap.add_argument("--blacklist", required=True, help="nodes blacklist YAML")
    ap.add_argument("--pbf", required=True,
                    help="the extract the graph is built from, scanned for the"
                         " gate nodes an allowed highway class carries")
    ap.add_argument("--out", required=True, help="where to write the patched profile")
    args = ap.parse_args()

    try:
        nodes = load_blacklist(args.blacklist)
        with open(args.profile, encoding="utf-8") as fh:
            source = fh.read()
        barriers = penalised_barriers(source)
        print(f"    scanning {args.pbf} for {', '.join(barriers)} nodes")
        started = time.monotonic()
        gates, opened = scan_gates(args.pbf, barriers)
        elapsed = time.monotonic() - started
        patched = patch(source, nodes, gates, opened)
    except Abort as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    tmp = args.out + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(patched)
    os.replace(tmp, args.out)

    print(f"    {len(gates)} gate node(s) in the extract, {len(opened)} carried"
          f" by an allowed class and left open ({elapsed / 60:.1f} min)")
    print(f"    the other {len(gates) - len(opened)} are impassable: they are"
          f" locked on the ground")
    if nodes:
        print(f"    {len(nodes)} node(s) made impassable: "
              + ", ".join(str(n) for n in nodes))
        print(f"    each one prints as osrm-extract meets it; one that never"
              f" prints is no longer in the extract")
    else:
        print("    no nodes blacklisted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
