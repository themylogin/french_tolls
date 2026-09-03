# -*- coding=utf-8 -*-
from dataclasses import dataclass, field
import logging
import os

import yaml

logger = logging.getLogger(__name__)

__all__ = ["Booth", "BoothData", "load"]

DATA_DIR = "/data"


@dataclass(frozen=True)
class Booth:
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
        return self.operator_name or self.osm_name

    @property
    def label(self) -> str:
        return self.name or f"OSM node {self.node_id}"


@dataclass(frozen=True)
class BoothData:
    booths: dict[int, Booth]
    # Every booth node id and every alias node id, mapped to the booth node id
    # that owns it.
    booth_of_node: dict[int, int]

    def at(self, node_id: int) -> Booth | None:
        owner = self.booth_of_node.get(node_id)
        return self.booths[owner] if owner is not None else None

    def __post_init__(self):
        # This is only used by `tolls.fare`, and only for ticketless entry gantries.
        merged: dict[str, dict[str, float]] = {}
        for booth in self.booths.values():
            if booth.gare is not None and booth.prices:
                merged.setdefault(booth.gare, {}).update(booth.prices)
        object.__setattr__(self, "_tariffs_by_gare", merged)

    def tariffs_of(self, gare: str | None) -> dict[str, float]:
        """Every tariff any booth of this gare records, keyed by exit gare."""
        if gare is None:
            return {}
        return self._tariffs_by_gare.get(gare, {})


LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)  # 5x load time decrease (if available)


def load_file(name: str) -> dict:
    # The open file rather than its bytes, so a YAML error names the path it is
    # in. Read at import by `route`, so either failure stops the service.
    with open(os.path.join(DATA_DIR, name), "rb") as f:
        return yaml.load(f, Loader=LOADER)


def load() -> BoothData:
    inventory = load_file("osm_toll_booths.yaml")
    prices = load_file("vinci_price.yaml")["toll_booths"] or {}
    gares = load_file("vinci_toll_booth.yaml")["toll_booths"] or {}
    sides = load_file("bidirectional_booth_sides.yaml")["toll_booths"] or {}

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
            prices=priced.get("prices") or {},
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
            logger.warning("alias %s names parent %s, which is not a booth", node_id, parent)

    return BoothData(booths=booths, booth_of_node=booth_of_node)
