# -*- coding=utf-8 -*-
import asyncio
from dataclasses import dataclass
import math
import re
import urllib.parse

from . import car, gas_stations
from .config import config
from .models import GasStation
from .osrm import NoRoute

__all__ = ["Candidate", "UnneededStation", "Via", "candidates", "consumption_at", "detour_vias", "detours",
           "fuel_walk", "plan", "segment_speed", "station_badge", "station_link", "stop_cost"]

RADIUS_KM = 50


class UnneededStation(Exception):
    """A chosen station comes after the fuel already lasts to the destination."""


@dataclass(frozen=True)
class Via:
    # [longitude, latitude], as the router was sent it.
    location: tuple[float, float]
    index: int
    chosen: bool


def consumption_at(parameters, speed_kmh):
    if speed_kmh < 80:
        return parameters.consume_80

    growth = (speed_kmh ** 2 - 80 ** 2) / (130 ** 2 - 80 ** 2)
    return parameters.consume_80 + (parameters.consume_130 - parameters.consume_80) * growth


def segment_speed(distance_m, duration_s):
    return distance_m / (duration_s * config.time_multiplier) * 3.6


def fuel_walk(route, parameters, fuel, start=0):
    """The index of the first node from `start` with 5 L or less, and the fuel left there.

    The index is None when the fuel left at the destination is more than 5 L.
    """
    for index in range(start, len(route.segment_distance)):
        if fuel <= 5:
            return index, fuel
        distance, duration = route.segment_distance[index], route.segment_duration[index]
        fuel -= distance / 1000 * _segment_consumption(parameters, distance, duration) / 100

    if fuel <= 5:
        return len(route.segment_distance), fuel
    return None, fuel


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
    half_height = RADIUS_KM / 111.2
    half_width = RADIUS_KM / (111.2 * math.cos(math.radians(latitude)))
    stations = await gas_stations.stations_in_area(latitude - half_height, longitude - half_width,
                                                   latitude + half_height, longitude + half_width)

    fuels = car.station_fuels(fuel_type)
    found = []
    for station in stations:
        offers = [(float(price), fuel) for fuel, _date, price in station.prices if fuel in fuels]
        if not offers:
            continue

        distance_km = _great_circle_km(latitude, longitude, station.latitude, station.longitude)
        if distance_km <= RADIUS_KM:
            price, fuel = min(offers)
            found.append(Candidate(station=station, fuel=fuel, price=price, distance_km=distance_km))

    found.sort(key=lambda candidate: (candidate.distance_km, candidate.station.id))
    return found[:30]


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


async def detours(routers, planned, vias, search_index, found):
    """One detour route for each candidate, in the same order, None where the router finds none."""
    requests = asyncio.Semaphore(4)

    async def detour(candidate):
        station = candidate.station
        locations = detour_vias(vias, search_index, (station.longitude, station.latitude))
        async with requests:
            try:
                return await routers.route_via(config.osrm_optimal_url, planned.start, locations, planned.end)
            except NoRoute:
                return None

    return await asyncio.gather(*[detour(candidate) for candidate in found])


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


async def plan(routers, planned, parameters, fuel, toll_cost, chosen=(), link_through=None):
    """The answer of `POST /api/refuel` for a route that `route.planned_route` gave.

    `chosen` holds the `(latitude, longitude)` of each station chosen so far, in
    order. `link_through(route, vias)` gives the Maps link of a finished plan. A
    `RouterUnavailable` or a `NoRoute` of a router request goes out unchanged.
    """
    route, vias, start, start_fuel = await _through_chosen(routers, planned, parameters, fuel, chosen)
    search_index, fuel_left = fuel_walk(route, parameters, start_fuel, start)
    if search_index is None:
        answer = {"stop_needed": False, "fuel_left": round(fuel_left, 2)}
        if chosen:
            answer["route"] = {
                "nodes": [list(coordinate) for coordinate in route.coordinates],
                "google_url": await link_through(route, vias),
            }
        return answer

    liters = parameters.tank_volume - fuel_left
    found = await candidates(route.coordinates[search_index], parameters.fuel_type)
    routes = await detours(routers, planned, vias, search_index, found)

    route_tolls = toll_cost(route)
    station_leg = sum(1 for via in vias if via.index < search_index)
    after_chosen = max((position + 1 for position, via in enumerate(vias[:station_leg]) if via.chosen), default=0)
    priced = []
    for candidate, detour in zip(found, routes):
        if detour is None:
            continue

        toll_difference = toll_cost(detour) - route_tolls
        detour_s = (detour.duration - route.duration) * config.time_multiplier
        cost = stop_cost(liters, candidate.price, toll_difference, detour_s)
        distance = sum(detour.leg_distance[:station_leg + 1])
        distance_from_previous = sum(detour.leg_distance[after_chosen:station_leg + 1])
        priced.append(((cost, candidate.station.id),
                       _station_entry(candidate, liters, cost, toll_difference, detour_s, distance,
                                      distance_from_previous)))

    priced.sort(key=lambda entry: entry[0])
    return {
        "stop_needed": True,
        "liters": round(liters, 2),
        "stations": [entry for _order, entry in priced[:10]],
    }


async def _through_chosen(routers, planned, parameters, fuel, chosen):
    """The route through the chosen stations, its vias, and where the walk goes on from.

    Each station is placed and routed as `detours` placed and routed it when it
    was listed, so the route is the detour route of the answer that listed it.
    """
    route = planned.route
    vias = [Via(location=stop.location, index=stop.index, chosen=False) for stop in planned.stops]
    start, start_fuel = 0, fuel

    for latitude, longitude in chosen:
        search_index, _fuel_left = fuel_walk(route, parameters, start_fuel, start)
        if search_index is None:
            raise UnneededStation(f"the fuel lasts before the station at {latitude:.6f},{longitude:.6f}")

        place = sum(1 for via in vias if via.index < search_index)
        locations = detour_vias(vias, search_index, (longitude, latitude))
        kinds = [via.chosen for via in vias]
        kinds.insert(place, True)
        route = await routers.route_via(config.osrm_optimal_url, planned.start, locations, planned.end)
        vias = [Via(location=location, index=route.leg_start[k + 1], chosen=kind)
                for k, (location, kind) in enumerate(zip(locations, kinds))]
        start, start_fuel = vias[place].index, parameters.tank_volume

    return route, vias, start, start_fuel


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
