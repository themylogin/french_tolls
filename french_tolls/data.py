# -*- coding=utf-8 -*-
"""The booth facts the accounting needs, loaded from what the pipeline publishes.

Four artefacts under `data/` answer four different questions, and this module is
where they become one set of lookups:

- `osm_toll_booths.yaml` — which OSM nodes are booths, and which nodes are lanes
  of another booth.
- `vinci_price.yaml` — each booth's type, and its tariffs.
- `vinci_toll_booth.yaml` — each booth's gare code and the operator's name.
- `bidirectional_booth_sides.yaml` — which neighbours of a two-way booth lie
  inside the toll network.

Nothing here carries a snapshot of its own. The application this replaces did,
and the snapshot was taken before the `gantry` type existed, so 52 priced
gantries charged nothing and no part of the answer said so.
"""
from dataclasses import dataclass, field
import logging
import os

import yaml

logger = logging.getLogger(__name__)

__all__ = ["BoothData", "MissingArtefact", "load", "load_or_exit"]

DATA_DIR = os.environ.get("DATA_DIR", "/data")

ARTEFACTS = (
    "osm_toll_booths.yaml",
    "vinci_price.yaml",
    "vinci_toll_booth.yaml",
    "bidirectional_booth_sides.yaml",
)


class MissingArtefact(Exception):
    """An artefact is absent or unreadable.

    Raised at start-up rather than at the first request. A service that starts
    without its tariffs answers every journey at 0 EUR, and nothing in the
    answer distinguishes that from a journey that really is free.
    """


@dataclass(frozen=True)
class Booth:
    """One booth, with everything four artefacts say about it."""

    node_id: int
    latlon: tuple[float, float]
    # From vinci_price.yaml: enter, exit, bidirectional, passthrough, gantry.
    # None when the price file does not carry this booth at all -- 20 of 1295.
    type: str | None = None
    # Entrance tariffs, keyed by the *exit's* gare code. Empty for a booth that
    # is not an entrance.
    prices: dict[str, float] = field(default_factory=dict)
    # The single amount a passthrough or a gantry charges for itself.
    price: float | None = None
    # From vinci_toll_booth.yaml. None for the 12 booths that map to no gare.
    gare: str | None = None
    operator_name: str | None = None
    # From osm_toll_booths.yaml: the OSM `name` tag. 1 499 of the 1 557 booths
    # carry one, including every booth the operator does not name.
    osm_name: str | None = None
    # From bidirectional_booth_sides.yaml, and only for a bidirectional booth.
    inside_nodes: frozenset[int] = frozenset()
    outside_nodes: frozenset[int] = frozenset()

    @property
    def name(self) -> str | None:
        """The best name this booth has, or None if it has none."""
        return self.operator_name or self.osm_name

    @property
    def label(self) -> str:
        """What a passage through this booth is called.

        The operator's name first: it is what is painted on the barrier a driver
        stops at, so where OSM disagrees the operator wins.

        Then the OSM name. `Péage de Vienne` tells a reader where they are;
        `OSM node 12288199204` tells them a fact about a database.

        The node id last, so a booth named nowhere is still identifiable. No
        booth needs it today -- every one of the 1 295 has a name from one source
        or the other -- and that is what a last resort is for.
        """
        return self.name or f"OSM node {self.node_id}"


@dataclass(frozen=True)
class BoothData:
    """Every booth, and the map from any node id to the booth it belongs to."""

    booths: dict[int, Booth]
    # Every booth node id and every alias node id, mapped to the booth node id
    # that owns it. A plaza is one node per lane and a route drives exactly one
    # of them, so a lookup that only knew the representative would miss the
    # passage whenever the router picked a neighbouring lane.
    booth_of_node: dict[int, int]

    def at(self, node_id: int) -> Booth | None:
        """The booth a route node belongs to, resolving a lane to its plaza."""
        owner = self.booth_of_node.get(node_id)
        return self.booths[owner] if owner is not None else None


def _read(name: str) -> bytes:
    path = os.path.join(DATA_DIR, name)
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise MissingArtefact(
            f"{path} could not be read ({e.strerror}). It is published by the "
            f"build pipeline; run `make all`, and check that ./data is mounted."
        ) from e


def _parse(name: str, raw: bytes) -> dict:
    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as e:
        raise MissingArtefact(f"{os.path.join(DATA_DIR, name)} is not valid YAML: {e}") from e

    if not isinstance(parsed, dict) or "toll_booths" not in parsed:
        raise MissingArtefact(
            f"{os.path.join(DATA_DIR, name)} has no `toll_booths` mapping, so it is "
            f"not the artefact this expects."
        )

    return parsed


def load() -> BoothData:
    """Read the four artefacts. Raises MissingArtefact if any is unusable."""
    inventory = _parse("osm_toll_booths.yaml", _read("osm_toll_booths.yaml"))
    prices = _parse("vinci_price.yaml", _read("vinci_price.yaml"))["toll_booths"] or {}
    gares = _parse("vinci_toll_booth.yaml", _read("vinci_toll_booth.yaml"))["toll_booths"] or {}
    sides = _parse(
        "bidirectional_booth_sides.yaml", _read("bidirectional_booth_sides.yaml")
    )["toll_booths"] or {}

    booths = {}
    for node_id, booth in (inventory["toll_booths"] or {}).items():
        node_id = int(node_id)
        priced = prices.get(node_id) or {}
        gare = gares.get(node_id) or {}
        side = sides.get(node_id) or {}

        booths[node_id] = Booth(
            node_id=node_id,
            latlon=tuple(booth["latlon"]),
            type=priced.get("type") or booth.get("type"),
            # The gare codes are strings, but a code of all digits and no leading
            # zero parses as an int. Normalising here keeps every later lookup
            # from having to know that.
            prices={str(k): float(v) for k, v in (priced.get("prices") or {}).items()},
            price=None if priced.get("price") is None else float(priced["price"]),
            gare=None if gare.get("id") is None else str(gare["id"]),
            operator_name=gare.get("name"),
            osm_name=booth.get("name"),
            inside_nodes=frozenset(int(n) for n in (side.get("inside_nodes") or [])),
            outside_nodes=frozenset(int(n) for n in (side.get("outside_nodes") or [])),
        )

    booth_of_node = {node_id: node_id for node_id in booths}
    for node_id, alias in (inventory.get("aliases") or {}).items():
        parent = int(alias["parent_id"])
        if parent in booths:
            booth_of_node[int(node_id)] = parent
        else:
            # A lane whose plaza is not in the inventory cannot be charged
            # against anything. Reported rather than silently dropped.
            logger.warning("alias %s names parent %s, which is not a booth", node_id, parent)

    data = BoothData(booths=booths, booth_of_node=booth_of_node)

    logger.info(
        "loaded %d booths, %d lanes, %d gares, %d priced, %d with sides",
        len(booths),
        len(booth_of_node) - len(booths),
        sum(1 for b in booths.values() if b.gare),
        sum(1 for b in booths.values() if b.type),
        sum(1 for b in booths.values() if b.inside_nodes or b.outside_nodes),
    )

    return data


def load_or_exit() -> BoothData:
    """`load`, but a bad artefact exits with the message instead of a traceback.

    This is what the application calls at import. Both entry points reach it --
    the web service through `api`, the bot through `service` -- so putting the
    guard here is what lets either of them fail with one readable line without
    the bot having to grow a handler of its own.
    """
    try:
        return load()
    except MissingArtefact as e:
        # SystemExit with a string prints it to stderr and exits 1. Raised rather
        # than logged so that no caller can carry on with no booths loaded.
        raise SystemExit(f"french_tolls: cannot start: {e}") from None
