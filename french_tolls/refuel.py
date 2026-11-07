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

__all__ = ["Candidate", "candidates", "consumption_at", "detour_vias", "detours", "fuel_walk", "plan",
           "segment_speed", "station_badge", "station_link", "stop_cost"]

RADIUS_KM = 50


def consumption_at(parameters, speed_kmh):
    if speed_kmh < 80:
        return parameters.consume_80

    growth = (speed_kmh ** 2 - 80 ** 2) / (130 ** 2 - 80 ** 2)
    return parameters.consume_80 + (parameters.consume_130 - parameters.consume_80) * growth


def segment_speed(distance_m, duration_s):
    return distance_m / (duration_s * config.time_multiplier) * 3.6


def fuel_walk(route, parameters, fuel):
    """The index of the first node with 5 L or less and the fuel left there.

    The index is None when the fuel left at the destination is more than 5 L.
    """
    for index, (distance, duration) in enumerate(zip(route.segment_distance, route.segment_duration)):
        if fuel <= 5:
            return index, fuel
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


def detour_vias(stops, search_index, station_location):
    before = [stop.location for stop in stops if stop.index < search_index]
    after = [stop.location for stop in stops if stop.index >= search_index]
    return [*before, station_location, *after]


async def detours(routers, planned, search_index, found):
    """One detour route for each candidate, in the same order, None where the router finds none."""
    requests = asyncio.Semaphore(4)

    async def detour(candidate):
        station = candidate.station
        vias = detour_vias(planned.stops, search_index, (station.longitude, station.latitude))
        async with requests:
            try:
                return await routers.route_via(config.osrm_optimal_url, planned.start, vias, planned.end)
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


async def plan(routers, planned, parameters, fuel, toll_cost):
    """The answer of `POST /api/refuel` for a route that `route.planned_route` gave.

    A `RouterUnavailable` of a detour goes out unchanged.
    """
    search_index, fuel_left = fuel_walk(planned.route, parameters, fuel)
    if search_index is None:
        return {"stop_needed": False, "fuel_left": round(fuel_left, 2)}

    liters = parameters.tank_volume - fuel_left
    found = await candidates(planned.route.coordinates[search_index], parameters.fuel_type)
    routes = await detours(routers, planned, search_index, found)

    route_tolls = toll_cost(planned.route)
    station_leg = sum(1 for stop in planned.stops if stop.index < search_index)
    priced = []
    for candidate, detour in zip(found, routes):
        if detour is None:
            continue

        toll_difference = toll_cost(detour) - route_tolls
        detour_s = (detour.duration - planned.route.duration) * config.time_multiplier
        cost = stop_cost(liters, candidate.price, toll_difference, detour_s)
        distance = sum(detour.leg_distance[:station_leg + 1])
        priced.append(((cost, candidate.station.id),
                       _station_entry(candidate, liters, cost, toll_difference, detour_s, distance)))

    priced.sort(key=lambda entry: entry[0])
    return {
        "stop_needed": True,
        "liters": round(liters, 2),
        "stations": [entry for _order, entry in priced[:10]],
    }


def _station_entry(candidate, liters, cost, toll_difference, detour_s, distance):
    station = candidate.station
    return {
        "name": station.name,
        "address": station.address,
        "latitude": station.latitude,
        "longitude": station.longitude,
        "google_url": station_link(station.latitude, station.longitude),
        "distance": distance,
        "badge": station_badge(station.services, station.address),
        "fuel": candidate.fuel,
        "price": candidate.price,
        "detour_duration": detour_s,
        "toll_difference": round(toll_difference, 2),
        "fuel_cost": round(liters * candidate.price, 2),
        "cost": round(cost, 2),
    }
