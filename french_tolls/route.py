# -*- coding=utf-8 -*-
"""The names the rest of the package and the bot import.

`bot.py` imports `distance_to_road_network` from here and is not changed by this
work, so that name and signature are fixed. Everything behind it is new: the
waypoint search is in `search`, the accounting in `tolls`, the routing client in
`osrm`, and the answer assembly in `service`.
"""
import logging

from . import osrm
from .osrm import NoRoute, RouterUnavailable, TooFarFromNetwork
from .search import Divergence, WaypointPlan, plan_waypoints
from .tolls import Journey, Passage, account

logger = logging.getLogger(__name__)

__all__ = [
    "Divergence",
    "Journey",
    "NoRoute",
    "Passage",
    "RouterUnavailable",
    "TooFarFromNetwork",
    "WaypointPlan",
    "account",
    "distance_to_road_network",
    "plan_waypoints",
]


async def distance_to_road_network(location):
    """How far a `(longitude, latitude)` is from the nearest road, in metres.

    Kept with the name and the signature `bot.py` already calls it by. The bot
    uses it to refuse a location before it starts a journey, and compares the
    result against a kilometre in its own reply text.
    """
    async with osrm.session() as session:
        return await osrm.Routers(session).distance_to_network(location)
