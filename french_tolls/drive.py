# -*- coding=utf-8 -*-
"""What to send a driver who asks to drive a journey, and why.

The order of the rules, and why it is that order:

    pressed
       |
       +- pays no tolls -----------> link + "enable Avoid tolls"     no request
       |
       +- fastest route pays ------> link, no waypoints              no request
       |  the same tolls as optimal
       |
       +- month's budget spent ----> link + "not checked"            no request
       |
       +- ask Google through our waypoints                           one request
              +- acceptable ------> link
              +- not --> correct the waypoints, ask again            one request
                     +- acceptable > link
                     +- not ------> split, and answer offering the next part

A route is acceptable when every toll booth it crosses is one ours crosses too.
If those booths could not be established, it is acceptable when it ran along our
road for the configured share of its length.
"""
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from .overlap import lengths_m

__all__ = [
    "AskGoogle", "AskRoute", "Basis", "Message", "Opinion", "Outcome", "Part",
    "AVOID_TOLLS", "COMPLEX", "MAX_DEPTH", "UNVERIFIED",
    "accepts", "drive", "midpoint",
]

# How many times a journey may be halved
MAX_DEPTH = 2

AVOID_TOLLS = "<b>⚠️ Please enable Avoid tolls before driving.</b>"
UNVERIFIED = ("<b>⚠️ We were unable to check if the Google Maps route matches the proposed "
              "route.</b> Please check manually if it has any unnecessary loops.")
COMPLEX = "This route is long and complex. Here is the next part of the route."


class Basis(StrEnum):
    """Why a link was accepted.
    """

    # Every booth Google's route crosses, our route crosses too, so it costs no more.
    TOLLS = "the tolls it pays"

    # The booths could not be established for one of the two routes, so the route is
    # accepted just because it's geometrically similar.
    ROAD = "the road it drives"

    # Fastest and optimal routes cross the same booths, so no need for waypoints.
    AGREED = "our own two routes agreeing"


@dataclass(frozen=True)
class Part:
    """A stretch to be driven, and what this project knows about it.
    """

    origin: tuple
    destination: tuple
    # the toll on *this* stretch
    cost: float
    waypoints: tuple = ()
    # The optimal route's coordinates, `[longitude, latitude]` per node.
    nodes: tuple = ()
    depth: int = 0
    # The booths the optimal route for this stretch crosses. None where the
    # caller could not establish them.
    booths: frozenset | None = None
    # The booths the *fastest* route for this stretch crosses. None where nobody
    # established them.
    fast_booths: frozenset | None = None


@dataclass(frozen=True)
class AskRoute:
    """Give me this project's route between two points, as a `Part`."""

    origin: tuple
    destination: tuple
    depth: int


@dataclass(frozen=True)
class AskGoogle:
    """Ask Google to drive these waypoints, and tell me what it would drive.

    The answer is an `Opinion`, or None where the request could not be made.
    """

    origin: tuple
    destination: tuple
    waypoints: tuple


@dataclass(frozen=True)
class Opinion:
    """What one Google request returned.
    """

    # The proportion of Google's route running within the corridor of ours
    share: float
    # The ones we sent, with a point added in each of the stretches Google strayed over
    waypoints: tuple = ()
    # What Google's route pays, or None where that could not be established
    booths: frozenset | None = None


@dataclass(frozen=True)
class Message:
    """One thing to send: some text and a link to drive.
    """

    text: str
    link: str
    basis: Basis | None = None


@dataclass
class Outcome:
    """What to send now, what is left to drive, and what it cost.
    """

    # messages to send now
    messages: list = field(default_factory=list)
    # remaining route parts
    pending: list = field(default_factory=list)
    # how many Google requests were made
    spent: int = 0


def midpoint(nodes):
    """The node halfway along a route by distance.
    """
    if len(nodes) < 3:
        return None

    # The routers speak (longitude, latitude); `lengths_m` reads (latitude,
    # longitude), so the pairs are turned round on the way in.
    latlon = np.asarray(nodes, dtype=float)[:, ::-1]
    along = np.concatenate([[0.0], np.cumsum(lengths_m(latlon))])

    best = int(np.argmin(np.abs(along - along[-1] / 2)))
    # A split at either end is not a split.
    if best == 0 or best == len(nodes) - 1:
        return None
    return tuple(nodes[best])


def link_from_here(part, waypoints, maps_link):
    """A directions link starting where the driver is. In the Telegram bot, we assume their
    current location is the origin that was requested.
    """
    points = ["Current Location"]
    points += [f"{lat:.6f},{lon:.6f}" for lon, lat in waypoints]
    points.append(f"{part.destination[1]:.6f},{part.destination[0]:.6f}")
    return maps_link(points)


def accepts(part, opinion, fits):
    """Which test accepts Google's route for this part, or None if neither.
    """
    if opinion.booths is not None and part.booths is not None:
        return Basis.TOLLS if opinion.booths <= part.booths else None
    return Basis.ROAD if fits(opinion.share) else None


def drive(part, budget, fits, maps_link):
    """Decide what to send for `part`. Yields requests, returns an `Outcome`.

    `fits` is the caller's judgement of a share.

    `budget` is how many Google requests may still be made this month.

    `maps_link` builds a directions URL from a list of points.
    """
    outcome = Outcome()
    yield from _part(part, budget, fits, maps_link, outcome, first=True)
    return outcome


def _part(part, budget, fits, maps_link, outcome, first):
    """One stretch, by the rules in the module docstring."""
    prefix = "" if first else COMPLEX + "\n"

    # Just avoiding tolls is the optimal route.
    if part.cost <= 0:
        outcome.messages.append(Message(
            text=(prefix + AVOID_TOLLS).strip(),
            link=link_from_here(part, part.waypoints, maps_link)))
        return

    # The fastest route pays the same tolls, so the plain link is the optimal route.
    if (part.booths is not None and part.fast_booths is not None
            and part.fast_booths == part.booths):
        outcome.messages.append(Message(
            text=prefix.strip(),
            link=link_from_here(part, (), maps_link),
            basis=Basis.AGREED))
        return

    # Unable to verify the Google route.
    if budget - outcome.spent < 1:
        outcome.messages.append(Message(
            text=(prefix + UNVERIFIED).strip(),
            link=link_from_here(part, part.waypoints, maps_link)))
        return

    answer = yield AskGoogle(part.origin, part.destination, part.waypoints)
    outcome.spent += 1
    if answer is None:
        outcome.messages.append(Message(
            text=(prefix + UNVERIFIED).strip(),
            link=link_from_here(part, part.waypoints, maps_link)))
        return

    # Google follows our waypoints well enough.
    waypoints = answer.waypoints
    if basis := accepts(part, answer, fits):
        outcome.messages.append(Message(
            text=prefix.strip(),
            link=link_from_here(part, waypoints, maps_link),
            basis=basis))
        return

    # Added more waypoints to Google route, and it became ok.
    if budget - outcome.spent >= 1:
        corrected = yield AskGoogle(part.origin, part.destination, waypoints)
        outcome.spent += 1
        if corrected is not None:
            waypoints = corrected.waypoints
            if basis := accepts(part, corrected, fits):
                outcome.messages.append(Message(
                    text=prefix.strip(),
                    link=link_from_here(part, waypoints, maps_link),
                    basis=basis))
                return

    # Halve the route
    at = midpoint(part.nodes) if part.depth < MAX_DEPTH else None
    if at is None or budget - outcome.spent < 1:
        # Nothing left to try: send the best link there is and say no more than
        # that. A part at the bound is still a part someone has to drive.
        outcome.messages.append(Message(
            text=prefix.strip(),
            link=link_from_here(part, waypoints, maps_link)))
        return

    near = yield AskRoute(part.origin, at, part.depth + 1)
    far = yield AskRoute(at, part.destination, part.depth + 1)
    if near is None or far is None:
        outcome.messages.append(Message(
            text=prefix.strip(),
            link=link_from_here(part, waypoints, maps_link)))
        return

    # Send the other half
    yield from _part(near, budget, fits, maps_link, outcome, first=False)
    outcome.pending.append(far)
