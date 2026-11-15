# -*- coding=utf-8 -*-
import asyncio
import bisect
from collections import defaultdict
from dataclasses import dataclass
import math
import re
import urllib.parse

from . import gas_stations
from .config import config
from .models import GasStation
from .osrm import NoRoute, Route

__all__ = ["Candidate", "CheaperQuery", "Start", "UnneededStation", "Via", "candidates", "cheaper_stations",
           "consumption_at",
           "detour_vias", "detours", "fuel_walk", "plan", "range_walk", "reserve_fuel", "route_stations",
           "segment_speed", "station_badge", "station_link", "stop_cost", "through_chosen"]

RADIUS_KM = 50
KM_PER_DEGREE = 111.2


class UnneededStation(Exception):
    """A chosen station comes after the fuel already lasts to the destination."""


@dataclass(frozen=True)
class Start:
    """Where a walk starts on the route, with exactly one of the fuel in liters and the range in km."""
    index: int
    fuel: float | None = None
    range_km: float | None = None


@dataclass(frozen=True)
class Via:
    # [longitude, latitude], as the router was sent it.
    location: tuple[float, float]
    index: int
    chosen: bool
    # The exit booth and the entrance booth of a split stop. Empty for a chosen station.
    booths: tuple = ()


@dataclass(frozen=True)
class CheaperQuery:
    """What `cheaper_stations` takes from a listed answer, so that it routes no planned route again."""

    # A `route.PlannedRoute`. Importing `route` would load the booths.
    planned: object
    # The route through the chosen stations, and its vias.
    route: Route
    vias: tuple
    walk_start: int
    search_index: int
    liters: float
    # The lowest price of the list.
    reference: float


def consumption_at(parameters, speed_kmh):
    if speed_kmh < 80:
        return parameters.consume_80

    growth = (speed_kmh ** 2 - 80 ** 2) / (130 ** 2 - 80 ** 2)
    return parameters.consume_80 + (parameters.consume_130 - parameters.consume_80) * growth


def segment_speed(distance_m, duration_s):
    return distance_m / (duration_s * config.time_multiplier) * 3.6


def fuel_walk(route, parameters, fuel, start=0):
    """The index of the first node from `start` where the fuel left is the reserve fuel there or less, and that fuel.

    The index is None when the fuel left at the destination is more than the reserve fuel there.
    """
    along, burn = _cumulative(route, parameters)
    for index in range(start, len(along)):
        left = fuel - (burn[index] - burn[start])
        if left <= _reserve_fuel(parameters, along, burn, index):
            return index, left
    return None, fuel - (burn[-1] - burn[start])


def reserve_fuel(route, parameters, index):
    """The fuel that the next `reserve_km` of the route use from the node `index`.

    The km past the destination use `consume_130`.
    """
    along, burn = _cumulative(route, parameters)
    return _reserve_fuel(parameters, along, burn, index)


def _cumulative(route, parameters):
    """The distance in m and the fuel in L from the first node to each node."""
    along, burn = [0.0], [0.0]
    for distance, duration in zip(route.segment_distance, route.segment_duration):
        along.append(along[-1] + distance)
        burn.append(burn[-1] + distance / 1000 * _segment_consumption(parameters, distance, duration) / 100)
    return along, burn


def _reserve_fuel(parameters, along, burn, index):
    target = along[index] + parameters.reserve_km * 1000
    if target >= along[-1]:
        return burn[-1] - burn[index] + (target - along[-1]) / 1000 * parameters.consume_130 / 100

    segment = bisect.bisect_right(along, target) - 1
    share = (target - along[segment]) / (along[segment + 1] - along[segment])
    return burn[segment] - burn[index] + share * (burn[segment + 1] - burn[segment])


def range_walk(route, range_km, reserve_km, start=0):
    """The index of the first node from `start` with `reserve_km` or less of range, and the range left there.

    The index is None when the range left at the destination is more than `reserve_km`.
    """
    for index in range(start, len(route.segment_distance)):
        if range_km <= reserve_km:
            return index, range_km
        range_km -= route.segment_distance[index] / 1000

    if range_km <= reserve_km:
        return len(route.segment_distance), range_km
    return None, range_km


def _walk(route, parameters, start):
    if start.fuel is None:
        return range_walk(route, start.range_km, parameters.reserve_km, start.index)
    return fuel_walk(route, parameters, start.fuel, start.index)


def _segment_consumption(parameters, distance, duration):
    if duration > 0:
        return consumption_at(parameters, segment_speed(distance, duration))
    return parameters.consume_80


@dataclass(frozen=True)
class Candidate:
    station: GasStation
    fuel: str
    price: float
    distance_km: float


async def candidates(position, fuel_type):
    """The 30 stations nearest to a `[longitude, latitude]` position that sell a fuel of the type."""
    longitude, latitude = position
    half_height = RADIUS_KM / KM_PER_DEGREE
    half_width = RADIUS_KM / (KM_PER_DEGREE * math.cos(math.radians(latitude)))
    stations = await gas_stations.stations_in_area(latitude - half_height, longitude - half_width,
                                                   latitude + half_height, longitude + half_width)

    found = []
    for station in stations:
        offer = gas_stations.fuel_price(station.prices, fuel_type)
        if offer is None:
            continue

        distance_km = _great_circle_km(latitude, longitude, station.latitude, station.longitude)
        if distance_km <= RADIUS_KM:
            price, fuel = offer
            found.append(Candidate(station=station, fuel=fuel, price=price, distance_km=distance_km))

    found.sort(key=lambda candidate: (candidate.distance_km, candidate.station.id))
    return found[:30]


async def route_stations(route, walk_start, search_index, fuel_type):
    """`(Candidate, route index)` for each station that sells a fuel of the type within 5 km of a route point of
    the walk, up to `search_index`.

    The route index is the nearest of these points, and `Candidate.distance_km` is the distance to it.
    """
    first = walk_start
    if walk_start > 0:
        # The walk starts at the last chosen station. `detour_vias` would place
        # a station at that same point before it.
        first += 1
    points = list(enumerate(route.coordinates[first:search_index + 1], start=first))
    if not points:
        return []

    grid = defaultdict(list)
    for index, (longitude, latitude) in points:
        grid[_grid_cell(latitude, longitude)].append((latitude, longitude, index))

    margin = 5 / KM_PER_DEGREE
    south = min(latitude for _index, (_longitude, latitude) in points) - margin
    north = max(latitude for _index, (_longitude, latitude) in points) + margin
    half_width = margin / math.cos(math.radians(north))
    west = min(longitude for _index, (longitude, _latitude) in points) - half_width
    east = max(longitude for _index, (longitude, _latitude) in points) + half_width

    found = []
    for station in await gas_stations.stations_in_area(south, west, north, east):
        offer = gas_stations.fuel_price(station.prices, fuel_type)
        if offer is None:
            continue

        nearest = _nearest_point(grid, station.latitude, station.longitude)
        if nearest is None:
            continue

        distance_km, index = nearest
        price, fuel = offer
        found.append((Candidate(station=station, fuel=fuel, price=price, distance_km=distance_km), index))
    return found


# A cell is 0.1° high and wide, so at least 6.9 km wide up to 51.1° N, the
# north end of France. The 3 × 3 cells around a station hold every point within 5 km.
def _grid_cell(latitude, longitude):
    return math.floor(latitude * 10), math.floor(longitude * 10)


def _nearest_point(grid, latitude, longitude):
    """`(distance in km, route index)` of the nearest grid point within 5 km, or None."""
    row, column = _grid_cell(latitude, longitude)
    nearest = None
    for cell_row in (row - 1, row, row + 1):
        for cell_column in (column - 1, column, column + 1):
            for point_latitude, point_longitude, index in grid.get((cell_row, cell_column), ()):
                distance_km = _great_circle_km(latitude, longitude, point_latitude, point_longitude)
                if distance_km <= 5 and (nearest is None or (distance_km, index) < nearest):
                    nearest = (distance_km, index)
    return nearest


def _great_circle_km(latitude_a, longitude_a, latitude_b, longitude_b):
    phi_a, phi_b = math.radians(latitude_a), math.radians(latitude_b)
    half_dphi = (phi_b - phi_a) / 2
    half_dlambda = math.radians(longitude_b - longitude_a) / 2
    a = math.sin(half_dphi) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(half_dlambda) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def detour_vias(vias, search_index, station_location):
    before = [via.location for via in vias if via.index < search_index]
    after = [via.location for via in vias if via.index >= search_index]
    return [*before, station_location, *after]


async def detours(routers, planned, vias, placed):
    """One detour route for each `(candidate, index)`, in the same order, None where the router finds none.

    `index` is the route point that places the station among the vias.
    """
    requests = asyncio.Semaphore(4)

    async def detour(candidate, index):
        station = candidate.station
        locations = detour_vias(vias, index, (station.longitude, station.latitude))
        async with requests:
            try:
                return await routers.route_via(planned.router_url, planned.start, locations, planned.end)
            except NoRoute:
                return None

    return await asyncio.gather(*[detour(candidate, index) for candidate, index in placed])


async def _priced(routers, planned, route, vias, placed, liters, toll_cost):
    """`((cost, station id), index, entry)` for each `(candidate, index)` that the router reaches, in order."""
    routes = await detours(routers, planned, vias, placed)
    route_tolls = toll_cost(route)
    priced = []
    for (candidate, index), detour in zip(placed, routes):
        if detour is None:
            continue

        station_leg = sum(1 for via in vias if via.index < index)
        after_chosen = max((position + 1 for position, via in enumerate(vias[:station_leg]) if via.chosen),
                           default=0)
        toll_difference = toll_cost(detour) - route_tolls
        detour_s = (detour.duration - route.duration) * config.time_multiplier
        cost = stop_cost(liters, candidate.price, toll_difference, detour_s)
        distance = sum(detour.leg_distance[:station_leg + 1])
        distance_from_previous = sum(detour.leg_distance[after_chosen:station_leg + 1])
        priced.append(((cost, candidate.station.id), index,
                       _station_entry(candidate, liters, cost, toll_difference, detour_s, distance,
                                      distance_from_previous)))
    return priced


def stop_cost(liters, price, toll_difference, detour_s):
    return liters * price + toll_difference + detour_s / 3600 * config.eur_per_hour


def station_badge(services, address):
    if "Automate CB 24/24" in services:
        return "24"
    if any("autoroute" in line.lower() for line in address):
        return "Autoroute"
    # `[^\W\d_]` is a letter. `Saint hilaire de` is no service area, but
    # `A71aire de` is one: the source dropped the space after the motorway number.
    if any(re.search(r"(?<![^\W\d_])aire\s+(?:de|des|du)\b|(?<![^\W\d_])aire\s+d['’]", line, re.IGNORECASE)
           for line in address):
        return "Aire"
    return None


def station_link(latitude, longitude):
    query = urllib.parse.urlencode({"api": "1", "query": f"{latitude:.6f},{longitude:.6f}"})
    return f"https://www.google.com/maps/search/?{query}"


async def plan(routers, planned, parameters, toll_cost, *, fuel=None, range_km=None, chosen=(), link_through=None,
               for_bot=False):
    """The answer of `POST /api/refuel` for a route that `route.planned_route` gave.

    The walk starts from `fuel` in liters or from `range_km`, never both.
    `chosen` holds each station chosen so far, in order, as `through_chosen`
    takes it. `link_through(route, vias)` gives the Maps link of a finished plan;
    without it, a finished plan carries no route. A `RouterUnavailable` or a
    `NoRoute` of a router request goes out unchanged.

    With `for_bot`, an answer without chosen stations whose fuel lasts also lists
    the stations at the destination, each with its `route_index`. Each answer
    with stations then also carries `cheaper_share`, the percentage of stored
    stations below the lowest price of the list, rounded up, and the
    `cheaper_query` that `cheaper_stations` takes.
    """
    if (fuel is None) == (range_km is None):
        raise ValueError("a plan takes either fuel or range_km")

    route, vias, start = await through_chosen(routers, planned, parameters, Start(0, fuel, range_km), chosen)
    search_index, left = _walk(route, parameters, start)
    at_destination = search_index is None
    if at_destination:
        answer = {"stop_needed": False}
        if start.fuel is None:
            answer["range_left"] = round(left, 2)
        else:
            answer["fuel_left"] = round(left, 2)
        if chosen and link_through is not None:
            answer["route"] = {
                "nodes": [list(coordinate) for coordinate in route.coordinates],
                "google_url": await link_through(route, vias),
            }
        if chosen or not for_bot:
            return answer
        search_index = len(route.segment_distance)
    else:
        answer = {"stop_needed": True}

    # After a walk by the range, the fuel at the search point is not known. A
    # reserve longer than a full tank would make the purchase negative.
    liters = max(0.0, parameters.tank_volume - reserve_fuel(route, parameters, search_index))
    if start.fuel is not None:
        liters = parameters.tank_volume - left
    found = await candidates(route.coordinates[search_index], parameters.fuel_type)
    priced = await _priced(routers, planned, route, vias, [(candidate, search_index) for candidate in found],
                           liters, toll_cost)
    priced.sort(key=lambda entry: entry[0])
    stations = [entry for _order, _index, entry in priced[:10]]
    if at_destination:
        stations = [{**entry, "route_index": search_index} for entry in stations]
    answer["liters"] = round(liters, 2)
    answer["stations"] = stations
    if for_bot and stations:
        reference = min(entry["price"] for entry in stations)
        below, total = await gas_stations.count_below(parameters.fuel_type, reference)
        answer["cheaper_share"] = (100 * below + total - 1) // total
        answer["cheaper_query"] = CheaperQuery(planned=planned, route=route, vias=tuple(vias), walk_start=start.index,
                                               search_index=search_index, liters=liters, reference=reference)
    return answer


async def cheaper_stations(routers, query, parameters, toll_cost):
    """The 10 latest route stations below the reference price of `query`, by cost, each with its `route_index`.

    A `RouterUnavailable` of a detour request goes out unchanged.
    """
    below = [(candidate, index)
             for candidate, index in await route_stations(query.route, query.walk_start, query.search_index,
                                                          parameters.fuel_type)
             if candidate.price < query.reference]
    below.sort(key=lambda pair: (-pair[1], pair[0].price, pair[0].station.id))
    priced = await _priced(routers, query.planned, query.route, query.vias, below[:10], query.liters, toll_cost)
    priced.sort(key=lambda entry: entry[0])
    return [{**entry, "route_index": index} for _order, index, entry in priced]


async def through_chosen(routers, planned, parameters, start, chosen):
    """The route through the chosen stations, its vias, and the `Start` of the walk after the last one.

    Each station is placed and routed as `detours` placed and routed it when it
    was listed, so the route is the detour route of the answer that listed it.
    The tank is full after a chosen station, so the walk after it is by the fuel.

    A chosen station is `(latitude, longitude)`, placed at the search point of
    the walk, or `(latitude, longitude, route_index)` from a destination list or
    a cheaper list, placed at that route point with no walk.
    """
    route = planned.route
    vias = [Via(location=stop.location, index=stop.index, chosen=False, booths=stop.booths) for stop in planned.stops]

    for latitude, longitude, *listed_at in chosen:
        if listed_at:
            [index] = listed_at
        else:
            index, _left = _walk(route, parameters, start)
            if index is None:
                raise UnneededStation(f"the tank lasts before the station at {latitude:.6f},{longitude:.6f}")

        place = sum(1 for via in vias if via.index < index)
        locations = detour_vias(vias, index, (longitude, latitude))
        kinds = [(via.chosen, via.booths) for via in vias]
        kinds.insert(place, (True, ()))
        route = await routers.route_via(planned.router_url, planned.start, locations, planned.end)
        vias = [Via(location=location, index=route.leg_start[k + 1], chosen=is_chosen, booths=booths)
                for k, (location, (is_chosen, booths)) in enumerate(zip(locations, kinds))]
        start = Start(vias[place].index, fuel=parameters.tank_volume)

    return route, vias, start


def _station_entry(candidate, liters, cost, toll_difference, detour_s, distance, distance_from_previous):
    station = candidate.station
    return {
        "name": station.name,
        "address": station.address,
        "latitude": station.latitude,
        "longitude": station.longitude,
        "google_url": station_link(station.latitude, station.longitude),
        "distance": distance,
        "distance_from_previous": distance_from_previous,
        "badge": station_badge(station.services, station.address),
        "fuel": candidate.fuel,
        "price": candidate.price,
        "detour_duration": detour_s,
        "toll_difference": round(toll_difference, 2),
        "fuel_cost": round(liters * candidate.price, 2),
        "cost": round(cost, 2),
    }
