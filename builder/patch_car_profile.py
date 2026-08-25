#!/usr/bin/env python3
"""Patch the routing profile so blacklisted nodes are impassable.

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

The pristine profile is left beside the patched one so the two can be compared,
and the image itself is never touched.

Outputs:
    <--out>  the patched profile
"""

import argparse
import os
import re
import sys

import yaml

# The anchor the injected check goes after. Matched rather than assumed so a
# profile that has moved on announces itself instead of being patched wrongly.
NODE_HOOK = "function process_node(profile, node, result, relations)\n"

BEGIN = "-- >>> nodes_blacklist, injected by builder/patch_car_profile.py"
END = "-- <<< nodes_blacklist"


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


def patch(source, nodes):
    if BEGIN in source:
        raise Abort("the profile is already patched")
    if source.count(NODE_HOOK) != 1:
        raise Abort(
            f"expected exactly one {NODE_HOOK.strip()!r} in the profile,"
            f" found {source.count(NODE_HOOK)}\n"
            f"       The profile has changed shape; re-read it before patching.")
    preamble, check = render(nodes)
    if not preamble:
        return source
    # After the requires and before the first function, so the table is in
    # scope everywhere and nothing above it has run yet.
    anchor = re.search(r"^(?=function |local function )", source, re.M)
    if anchor is None:
        raise Abort("no top-level function to place the blacklist table before")
    at = anchor.start()
    source = source[:at] + preamble + source[at:]
    return source.replace(NODE_HOOK, NODE_HOOK + check, 1)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", required=True, help="the pristine car.lua")
    ap.add_argument("--blacklist", required=True, help="nodes blacklist YAML")
    ap.add_argument("--out", required=True, help="where to write the patched profile")
    args = ap.parse_args()

    try:
        nodes = load_blacklist(args.blacklist)
        with open(args.profile, encoding="utf-8") as fh:
            source = fh.read()
        patched = patch(source, nodes)
    except Abort as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    tmp = args.out + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(patched)
    os.replace(tmp, args.out)

    if nodes:
        print(f"    {len(nodes)} node(s) made impassable: "
              + ", ".join(str(n) for n in nodes))
        print(f"    each one prints as osrm-extract meets it; one that never"
              f" prints is no longer in the extract")
    else:
        print("    no nodes blacklisted; the profile is unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
