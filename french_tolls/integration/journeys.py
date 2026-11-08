# -*- coding=utf-8 -*-
"""The pinned journeys: one per way a journey can resolve.

Named by the outcome, not by the place. The places are incidental — they are
simply real journeys through France that produce each outcome today, found by
driving candidates to their end and keeping the ones that landed where nothing
else had.

Every one was recorded at `TRAFFIC_AWARE_OPTIMAL`. Under the cheaper search four
of these resolved differently: Cogolin to Saint-Gaudens, which is not here
because it stopped being interesting, split into three parts and eight paid
requests and is now accepted on the first ask.
"""
from dataclasses import dataclass

__all__ = ["JOURNEYS", "Journey", "UNPINNED", "by_key"]


@dataclass(frozen=True)
class Journey:
    """One journey, and what driving it to the end is expected to cost."""

    key: str
    outcome: str
    origin: tuple
    destination: tuple
    origin_name: str
    destination_name: str
    # How many paid Google requests the whole drive would have made, across
    # every press. Asserted, because it is the operator's bill and nothing else
    # in the suite would notice it changing.
    asks: int
    # How many links the driver ends up with.
    parts: int
    # The route pressed where the answer offers a choice: "Optimal" or
    # "Superoptimal". None where the answer offers no choice.
    choice: str | None = None


JOURNEYS = (
    Journey(
        key="toll-free",
        outcome="the optimal route pays no tolls, so nothing is asked",
        origin=(-1.1844303, 47.3682464), origin_name="Ancenis-Saint-Géréon",
        destination=(-2.39808, 47.9323786), destination_name="Ploërmel",
        asks=0, parts=1,
    ),
    Journey(
        key="routes-agree",
        outcome="it pays a toll, but our fastest route crosses the booths our "
                "optimal one does, so nothing is asked",
        origin=(4.3601, 43.8367), origin_name="Nîmes",
        destination=(3.8767, 43.6108), destination_name="Montpellier",
        asks=0, parts=1,
    ),
    Journey(
        key="accepted-first-ask",
        outcome="Google's first route pays exactly our tolls",
        origin=(6.53659, 43.25), origin_name="Cogolin",
        destination=(5.3970648, 43.8757936), destination_name="Apt",
        asks=1, parts=1,
    ),
    Journey(
        key="corrected-then-accepted",
        outcome="the first route strays, waypoints are added, the second is accepted",
        origin=(-1.1844303, 47.3682464), origin_name="Ancenis-Saint-Géréon",
        destination=(6.4946806, 47.6863376), destination_name="Lure",
        asks=2, parts=1,
    ),
    Journey(
        key="split-with-a-free-part",
        outcome="it splits in two, and the first part pays no tolls",
        origin=(3.31892, 43.73106), origin_name="Lodève",
        destination=(6.5804218, 46.0603171), destination_name="Cluses",
        asks=4, parts=2, choice="Optimal",
    ),
    Journey(
        key="split-all-tolled",
        outcome="it splits in two, and neither part is free",
        origin=(6.4946806, 47.6863376), origin_name="Lure",
        destination=(7.5029213, 43.7753495), destination_name="Menton",
        asks=6, parts=2,
    ),
    Journey(
        key="superoptimal",
        outcome="it offers a superoptimal route with a stop at AGDE-PEZENAS, and "
                "the driver chooses it and drives it through the stop",
        origin=(2.8333, 42.5236), origin_name="Le Boulou",
        destination=(4.3601, 43.8367), destination_name="Nîmes",
        asks=2, parts=1, choice="Superoptimal",
    ),
)

# Outcomes with no real journey. Named rather than invented: a synthetic one
# would pin behaviour the application does not produce.
UNPINNED = {
    "split into three parts":
        "needs the near half to fail twice as well. Rare at "
        "TRAFFIC_AWARE_OPTIMAL: the better search corrects on the second ask.",
    "accepted on the first ask above the fit share":
        "would be accepted by the geometric test alone. The first ask is the "
        "one made with the fewest waypoints, so it is the one traffic moves "
        "most; both first-ask acceptances found sit below the share and are "
        "accepted on their tolls.",
}


def by_key(key) -> Journey:
    for journey in JOURNEYS:
        if journey.key == key:
            return journey
    raise KeyError(key)
