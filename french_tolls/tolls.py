# -*- coding=utf-8 -*-
"""What a driven route costs in tolls.

Walks a route's node ids in order, resolves each to the booth it belongs to, and
runs the ticket state machine over them. Nothing here raises on a barrier
sequence it did not expect: an unresolvable state becomes one passage carrying a
reason and no cost, and the rest of the journey is still accounted. Raising
instead fails a whole journey over one barrier, and of 1 295 booths, 12 carry no
gare code and 20 are absent from the price file.
"""
from dataclasses import dataclass, field
import logging

from .data import Booth, BoothData

logger = logging.getLogger(__name__)

__all__ = ["Journey", "Passage", "account"]

# Why a passage could not be priced. Distinguished because they mean different
# things: a route that began inside the network is ordinary, a gare the entrance
# does not price is a gap in the tariff data.
EXIT_WITHOUT_ENTRANCE = "exit without an entrance"
ENTRANCE_NOT_CLOSED = "entrance never closed by an exit"
TARIFF_MISSING = "the entrance does not price this exit"
BOOTH_NOT_PRICED = "the booth carries no tariff"
BOOTH_UNTYPED = "the booth is absent from the price file"
GARE_UNKNOWN = "the booth maps to no gare"
SIDE_UNKNOWN = "neither neighbour is a recorded side of this barrier"


@dataclass
class Passage:
    """One toll a route pays, or one it should have and could not be priced."""

    name: str
    cost: float | None = None
    # The route position at which the barrier was crossed, so a caller can put
    # the passages in driven order against the geometry.
    index: int = 0
    reason: str | None = None

    @property
    def priced(self) -> bool:
        return self.cost is not None

    def as_dict(self):
        # `cost` stays in the mapping even when unpriced, because the front end
        # and the bot read it. It is None rather than 0.0: a toll that could not
        # be priced is not a free toll, and 0.0 would say it was.
        d = {"name": self.name, "cost": self.cost}
        if self.reason:
            d["reason"] = self.reason
        return d


@dataclass
class Journey:
    """Every passage a route makes, and what they come to."""

    passages: list[Passage] = field(default_factory=list)

    @property
    def cost(self) -> float:
        """The sum of the priced passages, in euros."""
        return round(sum(p.cost for p in self.passages if p.priced), 2)

    @property
    def unpriced(self) -> int:
        return sum(1 for p in self.passages if not p.priced)


def _crossings(data: BoothData, node_ids) -> list[tuple[int, Booth, int | None, int | None]]:
    """The booths a node sequence crosses, in order.

    Yields `(index, booth, previous node id, next node id)`. Every node is
    resolved through the inventory's aliases, so a plaza is charged by whichever
    of its lanes the router picked. Consecutive nodes resolving to one booth
    count once -- a route drives one plaza once, however many of its nodes it
    touches.
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

    The node the route arrived from decides. A vehicle at an inside node is
    holding a ticket it will have to pay, so crossing closes that ticket. A
    vehicle at an outside node circulates freely, so crossing takes a ticket.

    Neither the direction of travel nor the ticket state decides it. Treating a
    two-way barrier as an entrance whenever no ticket happens to be open -- which
    is what the application this replaces did -- books an exit as an entrance
    every time a journey leaves the network through one.
    """
    if previous_node in booth.inside_nodes:
        return "exit"
    if previous_node in booth.outside_nodes:
        return "enter"

    # The preceding node is neither side. Fall back to the following node with
    # the sense reversed: a following node that is inside means the vehicle is
    # on its way in.
    if next_node in booth.inside_nodes:
        return "enter"
    if next_node in booth.outside_nodes:
        return "exit"

    return None


def account(data: BoothData, node_ids) -> Journey:
    """Every toll a route pays, in the order it pays them."""
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
            journey.passages.append(Passage(name=name, index=index, reason=GARE_UNKNOWN))
        elif exit_booth.gare not in open_entrance.prices:
            journey.passages.append(Passage(name=name, index=index, reason=TARIFF_MISSING))
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
                    name=booth.label, index=index, reason=SIDE_UNKNOWN
                ))
                continue

        if kind == "enter":
            if open_entrance is not None:
                # Two entrances with no exit between them. The earlier ticket is
                # unresolvable; record it and start the new one.
                close_unpriced(ENTRANCE_NOT_CLOSED)
            open_entrance, open_index = booth, index

        elif kind == "exit":
            if open_entrance is None:
                # The journey began inside the toll network, or an entrance was
                # missed. Either way there is no ticket to close.
                journey.passages.append(Passage(
                    name=booth.label, index=index, reason=EXIT_WITHOUT_ENTRANCE
                ))
            else:
                price_ticket(index, booth)

        elif kind in ("passthrough", "gantry"):
            # A flat charge for itself. It closes no ticket and opens none: a
            # gantry charges for a section travelled, and a passthrough barrier
            # is paid where it stands.
            if booth.price is None:
                journey.passages.append(Passage(
                    name=booth.label, index=index, reason=BOOTH_NOT_PRICED
                ))
            else:
                journey.passages.append(Passage(name=booth.label, cost=booth.price, index=index))

        else:
            # No type at all: the booth is in the inventory but not in the price
            # file. It was crossed, so it is reported; it cannot be charged.
            journey.passages.append(Passage(
                name=booth.label, index=index, reason=BOOTH_UNTYPED
            ))

    if open_entrance is not None:
        # The route ends with a ticket still open, which is what happens when the
        # destination is inside the toll network.
        close_unpriced(ENTRANCE_NOT_CLOSED)

    return journey
