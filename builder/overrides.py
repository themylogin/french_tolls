#!/usr/bin/env python3
"""Hand-maintained decisions about individual booths.

Some booths cannot be settled from the data. A lane whose only approach is
tagged `service` is invisible to a graph built from through roads. A gare whose
operator places it 45 m from the lane a route drives cannot be matched by
position. Each such case is stated here by hand rather than by a heuristic that
would misfire elsewhere.

Every entry is checked against the extract by the step that consumes it. An
override is a claim about a node in OpenStreetMap, and the pipeline is rebuilt
from a fresh extract every time -- a node can be retagged, deleted, or
renumbered upstream. An override that no longer matches anything is worse than
none at all, because it looks like the exception is handled when it is not.

    toll_booths:
      14061571392:
        # toll booth in vinci is displaced
        vinci:
          id: 12010
          name: SEES
      14061571393:
        # a real route will never go through this booth
        type: ignore
      13719126553:
        # exit through the service roads, not currently supported by scripts
        parent_id: 635884768
"""

import os

import yaml

# `ignore` removes a booth from the pipeline entirely: it is not a booth we care
# about at all.
#
# The `absent_*` family says the opposite -- the booth is real and a route does
# drive through it, but the operator's placemark layer does not carry it. Such a
# booth stays in the inventory and in the route set; only the requirement that
# the gare mapping find a gare for it is waived. The suffix records how a route
# meets it, which nothing consumes yet.
#
# The bare `enter`/`exit`/`passthrough` classify a border crossing and are inert.
#
# Every value is enumerated rather than waved through, so that `type: igore`
# fails instead of silently doing nothing.
IGNORE = "ignore"
ABSENT = ("absent_enter", "absent_exit", "absent_passthrough")
BORDER = ("enter", "exit", "passthrough")
TYPES = (IGNORE, *ABSENT, *BORDER)

# `price` states what a booth charges when the operator does not report it. Only
# a passthrough has a single price to state: an enter or an exit is one half of a
# journey whose charge depends on where the other half was.
PRICED_TYPES = ("absent_passthrough",)

KEYS = ("type", "parent_id", "vinci", "price")


class OverrideError(Exception):
    """A stale or malformed override. Never applied approximately."""


class Overrides:
    """ignored booths, forced group parents, and gares stated by hand."""

    def __init__(self, ignored=None, forced=None, vinci=None, absent=None,
                 price=None):
        self.ignored = ignored or set()
        self.forced = forced or {}
        self.vinci = vinci or {}
        self.absent = absent or {}   # booth -> which absent_* type
        self.price = price or {}     # booth -> stated charge

    def __bool__(self):
        return bool(self.ignored or self.forced or self.vinci or self.absent)

    def summary(self):
        return (f"{len(self.ignored)} ignored, {len(self.absent)} absent from the"
                f" operator, {len(self.forced)} forced into a group,"
                f" {len(self.vinci)} gare(s) stated by hand")


def load(path):
    """Parse and structurally validate the override file. Missing file is empty."""
    if not os.path.exists(path):
        return Overrides()
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    entries = doc.get("toll_booths") or {}

    ignored, forced, vinci, absent, price = set(), {}, {}, {}, {}
    for node_id, entry in sorted(entries.items()):
        entry = entry or {}
        where = f"override for booth {node_id}"
        unknown = sorted(set(entry) - set(KEYS))
        if unknown:
            raise OverrideError(
                f"{where}: unknown key(s) {', '.join(unknown)};"
                f" expected one of {', '.join(KEYS)}")
        if not entry:
            raise OverrideError(
                f"{where}: carries none of {', '.join(KEYS)}")

        if "type" in entry:
            value = entry["type"]
            if value not in TYPES:
                raise OverrideError(
                    f"{where}: unknown type {value!r};"
                    f" expected one of {', '.join(TYPES)}")
            if value == IGNORE:
                # An ignored booth does not exist, so it can neither join a group
                # nor carry a gare.
                if "parent_id" in entry or "vinci" in entry:
                    raise OverrideError(
                        f"{where}: type: {IGNORE} cannot be combined with"
                        f" parent_id or vinci")
                ignored.add(node_id)
            if value in ABSENT:
                # The booth is real; only the operator's record of it is missing.
                if "vinci" in entry:
                    raise OverrideError(
                        f"{where}: type: {value} says the operator does not"
                        f" carry this booth, so it cannot also state a vinci gare")
                absent[node_id] = value

        if "price" in entry:
            if entry.get("type") not in PRICED_TYPES:
                raise OverrideError(
                    f"{where}: price is only meaningful with"
                    f" {', '.join(PRICED_TYPES)}, not {entry.get('type')!r}")
            value = entry["price"]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise OverrideError(
                    f"{where}: price must be a number, got {value!r}")
            price[node_id] = float(value)

        if "parent_id" in entry:
            forced[node_id] = entry["parent_id"]

        if "vinci" in entry:
            gare = entry["vinci"] or {}
            missing = sorted({"id", "name"} - set(gare))
            if missing:
                raise OverrideError(
                    f"{where}: vinci is missing {', '.join(missing)}")
            extra = sorted(set(gare) - {"id", "name"})
            if extra:
                raise OverrideError(
                    f"{where}: vinci carries unknown key(s) {', '.join(extra)}")
            # Operator numbers are digit strings with leading zeros that YAML
            # would otherwise read as integers, so they are normalised here and
            # compared as strings everywhere.
            vinci[node_id] = {"id": str(gare["id"]), "name": str(gare["name"])}

    return Overrides(ignored, forced, vinci, absent, price)


def check_against_extract(ov, booths):
    """Every overridden node must be a toll booth in the source extract."""
    for node_id in sorted(set(ov.ignored) | set(ov.forced) | set(ov.vinci)
                          | set(ov.absent)):
        if node_id not in booths:
            raise OverrideError(
                f"override for booth {node_id}: the extract does not carry that"
                f" node as a toll booth")
