# -*- coding=utf-8 -*-
"""Tolls of the driven route.
"""
from dataclasses import dataclass, field
import logging

from .data import Booth, BoothData

logger = logging.getLogger(__name__)

__all__ = ["Journey", "Passage", "account", "booths_crossed"]


@dataclass
class Passage:
    """A toll on the route."""

    name: str
    cost: float | None = None
    # The route position at which the barrier was crossed.
    index: int = 0
    reason: str | None = None

    @property
    def priced(self) -> bool:
        return self.cost is not None

    def as_dict(self):
        d = {"name": self.name, "cost": self.cost}
        if self.reason:
            d["reason"] = self.reason
        return d


@dataclass
class Journey:
    """Every passage a route makes.
    """

    passages: list[Passage] = field(default_factory=list)
    # A passthrough or gantry with no tariff is not included in `passages`.
    silent_unpriced: int = 0

    @property
    def cost(self) -> float:
        """The sum of the priced passages, in euros."""
        return round(sum(p.cost for p in self.passages if p.priced), 2)

    @property
    def unpriced(self) -> int:
        """The number of crossings that are unpriced."""
        return sum(1 for p in self.passages if not p.priced) + self.silent_unpriced


def _crossings(data: BoothData, node_ids) -> list[tuple[int, Booth, int | None, int | None]]:
    """The booths a node sequence crosses, in order.

    Each entry is `(index, booth, previous node id, next node id)`.
    """
    out = []
    previous_booth = None

    for i, node_id in enumerate(node_ids):
        booth = data.at(node_id)
        if booth is None:
            previous_booth = None
            continue

        if booth is previous_booth:
            continue

        out.append((
            i,
            booth,
            node_ids[i - 1] if i > 0 else None,
            node_ids[i + 1] if i + 1 < len(node_ids) else None,
        ))
        previous_booth = booth

    return out


def _sense_of_bidirectional(booth: Booth, previous_node, next_node) -> str | None:
    """Whether a two-way barrier is being entered or left.
    """
    if previous_node in booth.inside_nodes:
        return "exit"
    if previous_node in booth.outside_nodes:
        return "enter"

    # The preceding node is neither side. Fall back to the following node.
    if next_node in booth.inside_nodes:
        return "enter"
    if next_node in booth.outside_nodes:
        return "exit"

    return None


def booths_crossed(data: BoothData, node_ids) -> frozenset[int]:
    """Which booths a node sequence crosses.
    """
    return frozenset(booth.node_id for _index, booth, _prev, _next in _crossings(data, node_ids))


def account(data: BoothData, node_ids) -> Journey:
    """The tolls a route pays, in the order it pays them."""
    journey = Journey()
    open_entrance = None
    open_index = 0

    def close_unpriced(reason):
        nonlocal open_entrance
        journey.passages.append(Passage(
            name=open_entrance.label, index=open_index, reason=reason
        ))
        open_entrance = None

    def price_ticket(index, exit_booth):
        """Close the open ticket at `exit_booth`."""
        nonlocal open_entrance
        name = f"{open_entrance.label} → {exit_booth.label}"

        if exit_booth.gare is None:
            journey.passages.append(Passage(
                name=name, index=index, reason="the booth maps to no gare"))
        elif exit_booth.gare not in open_entrance.prices:
            journey.passages.append(Passage(
                name=name, index=index,
                reason="the entrance does not price this exit"))
        else:
            journey.passages.append(Passage(
                name=name, cost=open_entrance.prices[exit_booth.gare], index=index
            ))

        open_entrance = None

    for index, booth, previous_node, next_node in _crossings(data, node_ids):
        kind = booth.type

        if kind == "bidirectional":
            kind = _sense_of_bidirectional(booth, previous_node, next_node)
            if kind is None:
                journey.passages.append(Passage(
                    name=booth.label, index=index,
                    reason="neither neighbour is a recorded side of this barrier"
                ))
                continue

        if kind == "enter":
            if open_entrance is not None:
                # Two entrances with no exit between them. The earlier ticket is
                # unresolvable; record it and start the new one.
                close_unpriced("entrance never closed by an exit")
            open_entrance, open_index = booth, index

        elif kind == "exit":
            if open_entrance is None:
                # The journey began inside the toll network, or an entrance was
                # missed. Either way there is no ticket to close.
                journey.passages.append(Passage(
                    name=booth.label, index=index, reason="exit without an entrance"
                ))
            else:
                price_ticket(index, booth)

        elif kind in ("passthrough", "gantry"):
            if booth.price is None:
                journey.silent_unpriced += 1
            else:
                journey.passages.append(Passage(name=booth.label, cost=booth.price, index=index))

        else:
            journey.passages.append(Passage(
                name=booth.label, index=index, reason="the booth is absent from the price file"
            ))

    if open_entrance is not None:
        close_unpriced("entrance never closed by an exit")

    return journey
