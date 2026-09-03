# -*- coding=utf-8 -*-
"""Where leaving the tolled road and rejoining it costs less than driving on."""
from dataclasses import dataclass
import logging
import os

import yaml

from . import booths
from .config import config

logger = logging.getLogger(__name__)

__all__ = ["Advice", "Stop", "load"]

DATA_DIR = "/data"
FILE = "cost-cutting.yaml"



@dataclass(frozen=True)
class Stop:
    """One junction a split journey leaves the tolled road at and rejoins."""

    exit_node: int
    enter_node: int


@dataclass(frozen=True)
class Candidate:
    """One way of splitting one sold ticket."""

    stops: tuple[Stop, ...]
    extra_time: int          # seconds, driving plus booth time

    @property
    def node_ids(self) -> tuple[int, ...]:
        out = []
        for stop in self.stops:
            out += [stop.exit_node, stop.enter_node]
        return tuple(out)


@dataclass(frozen=True)
class Advice:
    """Every split the pipeline found, keyed by the ticket it replaces."""

    by_pair: dict[tuple[str, str], tuple[Candidate, ...]]

    def best(self, gare_in: str, gare_out: str, direct_eur: float,
             fare_of, threshold: float) -> tuple[Candidate, float] | None:
        """The candidate earning the most per hour, with what it saves.

        Returns None when nothing clears `threshold`, which is the ordinary case.
        """
        best_pair, best_ratio = None, threshold
        for candidate in self.by_pair.get((gare_in, gare_out), ()):
            if candidate.extra_time <= 0:
                continue
            split_eur = fare_of(candidate)
            if split_eur is None:
                continue
            saving = round(direct_eur - split_eur, 2)
            if saving <= 0:
                continue
            ratio = saving / (candidate.extra_time / 3600.0)
            if ratio >= best_ratio:
                best_pair, best_ratio = (candidate, saving), ratio
        return best_pair


def threshold() -> float:
    """What an hour of extra driving has to be worth before a split is offered."""
    return config.eur_per_hour


def load(path: str = None) -> Advice:
    path = path or os.path.join(DATA_DIR, FILE)
    with open(path, "rb") as f:
        document = yaml.load(f, Loader=booths.LOADER) or {}

    by_pair = {}
    for gare_in, by_exit in (document.get("toll_booths") or {}).items():
        for gare_out, candidates in (by_exit or {}).items():
            parsed = []
            for candidate in candidates or ():
                nodes = [int(n) for n in candidate["nodes"]]
                if len(nodes) % 2:
                    logger.warning("%s -> %s: %d node(s), expected two per stop",
                                   gare_in, gare_out, len(nodes))
                    continue
                parsed.append(Candidate(
                    stops=tuple(Stop(exit_node=nodes[i], enter_node=nodes[i + 1])
                                for i in range(0, len(nodes), 2)),
                    extra_time=int(candidate["extra_time"]),
                ))
            if parsed:
                by_pair[(str(gare_in), str(gare_out))] = tuple(parsed)

    logger.info("%d sold ticket(s) can be split", len(by_pair))
    return Advice(by_pair=by_pair)
