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
      26024647:
        # the topology says this lane is an alternative to 25315120, and it is --
        # but the operator charges the two as different gares, so they cannot be
        # one coverage target. A null parent keeps the booth in its own group.
        parent_id: null

    duplicate_gares:
      # the road that would let a driver go straight on is not built yet, so the
      # fastest route really does come back through this gare and pay it twice
      - "04210"
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
# The bare `enter`/`exit`/`passthrough` say the booth is a plain one-way lane of
# that role, whatever the extract's tags say. They exist for the booths at a
# border, where every trip across ends outside France: no pair of French place
# nodes produces a route through one, so the route set cannot reach it and
# nothing would otherwise settle its role or find its gare.
#
# Two consequences follow, and the second is why most of these entries exist at
# all. A booth on a way tagged `oneway=no` that is not two-way on the ground
# stops being typed `bidirectional`, which would make it two coverage targets
# instead of one, keep it out of every plaza group, and leave the reverse
# direction permanently uncovered because no car can drive it. And every stated
# booth, whatever its tags already say, carries a `passage` in the inventory --
# the node before it and the node after it -- from which the gare mapping builds
# a leg through the booth and asks the operator what gare it is.
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

# Top-level sections. Enumerated for the same reason the type values are: a
# mistyped section name would otherwise be read as an empty one and every entry
# under it would vanish without a word.
SECTIONS = ("toll_booths", "duplicate_gares", "prohibited_gare_pairs")


class OverrideError(Exception):
    """A stale or malformed override. Never applied approximately."""


class Overrides:
    """ignored booths, forced group parents, and gares stated by hand."""

    def __init__(self, ignored=None, forced=None, vinci=None, absent=None,
                 price=None, isolated=None, duplicate_gares=None,
                 prohibited_gare_pairs=None, one_way=None):
        self.ignored = ignored or set()
        self.forced = forced or {}
        self.vinci = vinci or {}
        self.absent = absent or {}   # booth -> which absent_* type
        self.price = price or {}     # booth -> stated charge
        self.isolated = isolated or set()  # booths kept out of every group
        # Gares a single route may legitimately pay twice. Normally that means a
        # route turned around, which no car does -- but where the road that would
        # let a driver go straight on is missing or unbuilt, the detour back
        # through the same gare is the real fastest route and is charged twice.
        self.duplicate_gares = duplicate_gares or set()
        # Ordered (entrance gare, exit gare) pairs that are not a journey. The
        # direct pricing step drops them before routing: asking the operator
        # would spend a request to be told what this file already says.
        self.prohibited_gare_pairs = prohibited_gare_pairs or set()
        # booth -> the role stated for a booth no route reaches. Consumed by the
        # inventory step, which publishes a `passage` for it and drops any
        # `bidirectional` typing a two-way tag would otherwise produce, and by
        # the gare mapping, which submits a leg along that passage.
        self.one_way = one_way or {}

    def __bool__(self):
        return bool(self.ignored or self.forced or self.vinci or self.absent
                    or self.isolated or self.duplicate_gares
                    or self.prohibited_gare_pairs or self.one_way)

    def summary(self):
        return (f"{len(self.ignored)} ignored, {len(self.absent)} absent from the"
                f" operator, {len(self.forced)} forced into a group,"
                f" {len(self.isolated)} kept out of every group,"
                f" {len(self.vinci)} gare(s) stated by hand,"
                f" {len(self.duplicate_gares)} gare(s) payable twice,"
                f" {len(self.prohibited_gare_pairs)} gare pair(s) prohibited,"
                f" {len(self.one_way)} stated one-way")


def load(path):
    """Parse and structurally validate the override file. Missing file is empty."""
    if not os.path.exists(path):
        return Overrides()
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    unknown_sections = sorted(set(doc) - set(SECTIONS))
    if unknown_sections:
        raise OverrideError(
            f"unknown top-level section(s) {', '.join(unknown_sections)};"
            f" expected one of {', '.join(SECTIONS)}")
    entries = doc.get("toll_booths") or {}

    # Operator numbers carry leading zeros. Unquoted, YAML reads 04210 as an
    # integer and drops the zero, so they are normalised to strings here and
    # compared as strings everywhere.
    duplicate_gares = set()
    listed = doc.get("duplicate_gares")
    if listed is not None:
        if not isinstance(listed, list):
            raise OverrideError(
                f"duplicate_gares must be a list, got {type(listed).__name__}")
        for value in listed:
            if isinstance(value, (dict, list)) or value is None:
                raise OverrideError(
                    f"duplicate_gares: {value!r} is not an operator number")
            duplicate_gares.add(str(value))

    # An ordered pair of gares that is not a journey anyone can be sold, however
    # the road network reads. Two ramps of one interchange under two codes are
    # the case it exists for: a router asked to drive between them produces a
    # loop out and back, which crosses no booth and so looks like a ticket.
    # Direction is part of the statement -- prohibiting A -> B says nothing
    # about B -> A, and both are listed when both are meant.
    prohibited_gare_pairs = set()
    listed = doc.get("prohibited_gare_pairs")
    if listed is not None:
        if not isinstance(listed, list):
            raise OverrideError(
                f"prohibited_gare_pairs must be a list, got"
                f" {type(listed).__name__}")
        for value in listed:
            if not isinstance(value, list) or len(value) != 2:
                raise OverrideError(
                    f"prohibited_gare_pairs: {value!r} is not a pair of"
                    f" operator numbers")
            a, b = (str(v) for v in value)
            if a == b:
                raise OverrideError(
                    f"prohibited_gare_pairs: {value!r} names one gare twice;"
                    f" a pair of a gare with itself is never asked about anyway")
            prohibited_gare_pairs.add((a, b))


    ignored, forced, vinci, absent, price, isolated = set(), {}, {}, {}, {}, set()
    one_way = {}
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
            if value in BORDER:
                one_way[node_id] = value

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
            # A null parent is the opposite of a forced one: it says the booth
            # belongs in no group but its own. The topological rule is right
            # about such a lane being an alternative and still wrong about the
            # consequence, because the operator charges the two lanes as
            # different gares -- so they cannot be one coverage target.
            if entry["parent_id"] is None:
                isolated.add(node_id)
            else:
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

    # A booth cannot be kept out of every group and pulled into one at the same
    # time, whichever end of the relation states it. Both spellings are checked
    # here rather than left to whichever rule happens to run last.
    for child, target in sorted(forced.items()):
        if target in isolated:
            raise OverrideError(
                f"override for booth {child}: parent_id names {target}, which"
                f" states parent_id: null and so has no group to join")
    return Overrides(ignored, forced, vinci, absent, price, isolated,
                     duplicate_gares, prohibited_gare_pairs, one_way)


def check_against_extract(ov, booths):
    """Every overridden node must be a toll booth in the source extract."""
    for node_id in sorted(set(ov.ignored) | set(ov.forced) | set(ov.vinci)
                          | set(ov.absent) | set(ov.isolated) | set(ov.one_way)):
        if node_id not in booths:
            raise OverrideError(
                f"override for booth {node_id}: the extract does not carry that"
                f" node as a toll booth")
