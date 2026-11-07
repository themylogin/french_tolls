# -*- coding=utf-8 -*-
import asyncio
from dataclasses import replace
import json
import sqlite3
from types import SimpleNamespace

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .. import db, refuel
from ..car import CarParameters
from ..config import config
from ..osrm import NoRoute, Route, RouterUnavailable

SEARCH_POINT = (2.0, 47.0)
DIESEL = [["Gazole (B7)", "2026-11-06", "1.800"]]


@pytest.fixture
def store(tmp_path, monkeypatch):
    db_path = tmp_path / "database.db"
    alembic_config = Config(__file__.rsplit("/", 3)[0] + "/alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(alembic_config, "head")

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db, "Session", async_sessionmaker(engine, expire_on_commit=False))
    yield db_path
    asyncio.run(engine.dispose())


@pytest.fixture
def fixed_rates(monkeypatch):
    monkeypatch.setattr(refuel, "config", replace(config, time_multiplier=1.0, eur_per_hour=20.0))


def insert_station(db_path, station_id, latitude, longitude, prices, name="Leclerc", services=(),
                   address=("Rue de quimper", "29520 Chateauneuf du faou")):
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO gas_station"
            " (id, latitude, longitude, name, address, services, prices, last_updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, '2026-11-07 10:00:00')",
            (station_id, latitude, longitude, name, json.dumps(list(address)), json.dumps(list(services)),
             json.dumps(prices)),
        )


def candidate_ids(position, fuel_type):
    return [candidate.station.id for candidate in asyncio.run(refuel.candidates(position, fuel_type))]


def a_car(consume_80, consume_130, tank_volume=50, fuel_type="diesel"):
    return CarParameters(fuel_type=fuel_type, tank_volume=tank_volume, consume_80=consume_80,
                         consume_130=consume_130)


def a_route(segment_m, segment_s, segments, start=(2.0, 47.0)):
    node_ids = tuple(range(1, segments + 2))
    return Route(
        node_ids=node_ids,
        coordinates=tuple((start[0], start[1] + 0.09 * i) for i in range(segments + 1)),
        segment_distance=(segment_m,) * segments,
        segment_duration=(segment_s,) * segments,
        distance=segment_m * segments,
        duration=segment_s * segments,
        weight=segment_s * segments,
    )


@pytest.mark.parametrize("speed_kmh,expected", [
    (105, 6.881),
    (80, 6.0),
    (130, 8.0),
    (50, 6.0),
    (150, 9.067),
])
def test_the_consumption_follows_the_curve_from_80_km_h(speed_kmh, expected):
    assert round(refuel.consumption_at(a_car(6, 8), speed_kmh), 3) == expected


def test_the_speed_of_a_segment_uses_the_time_multiplier(monkeypatch):
    monkeypatch.setattr(refuel, "config", replace(config, time_multiplier=0.9))

    assert refuel.segment_speed(1000, 40) == pytest.approx(100)


def test_the_search_point_is_where_the_tank_first_holds_5_l():
    route = a_route(10_000, 10_000 / (130 / 3.6), 10)

    index, fuel_left = refuel.fuel_walk(route, a_car(10, 10), 10)

    assert index == 5
    assert fuel_left == pytest.approx(5)


@pytest.mark.parametrize("fuel", [4, 5])
def test_5_l_or_less_at_the_origin_makes_the_origin_the_search_point(fuel):
    route = a_route(10_000, 10_000 / (130 / 3.6), 10)

    assert refuel.fuel_walk(route, a_car(10, 10), fuel) == (0, fuel)


def test_no_search_point_when_the_fuel_lasts():
    route = a_route(10_000, 10_000 / (130 / 3.6), 10)

    index, fuel_left = refuel.fuel_walk(route, a_car(6, 6), 40)

    assert index is None
    assert fuel_left == pytest.approx(34)


def test_a_segment_of_0_s_uses_no_fuel():
    route = a_route(0, 0, 3)

    assert refuel.fuel_walk(route, a_car(6, 8), 20) == (None, 20)


def test_a_station_60_km_away_is_not_a_candidate(store):
    insert_station(store, 1, 47.0 + 60 / 111.195, 2.0, DIESEL)

    assert candidate_ids(SEARCH_POINT, "diesel") == []


def test_a_station_in_the_corner_of_the_box_is_not_a_candidate(store):
    insert_station(store, 1, 47.0 + 45 / 111.195, 2.0 + 45 / 75.835, DIESEL)

    assert candidate_ids(SEARCH_POINT, "diesel") == []


@pytest.mark.parametrize("fuel_type", ["diesel", "95", "98"])
def test_a_station_without_the_fuel_is_not_a_candidate(store, fuel_type):
    insert_station(store, 1, 47.018, 2.0, [["E85 (E85)", "2026-11-06", "0.799"]])

    assert candidate_ids(SEARCH_POINT, fuel_type) == []


def test_the_30_nearest_stations_are_the_candidates(store):
    for station_id in range(1, 41):
        insert_station(store, station_id, 47.0 + 0.01 * station_id, 2.0, DIESEL)

    assert candidate_ids(SEARCH_POINT, "diesel") == list(range(1, 31))


def test_the_price_of_a_station_is_its_lowest_price_for_the_fuel(store):
    insert_station(store, 1, 47.01, 2.0, [["SP95-E10 (E10)", "2026-11-06", "1.799"],
                                          ["SP95 (E5)", "2026-11-06", "1.859"]])

    [candidate] = asyncio.run(refuel.candidates(SEARCH_POINT, "95"))

    assert candidate.price == 1.799
    assert candidate.fuel == "SP95-E10 (E10)"


def test_the_station_goes_between_the_stops_before_and_after_the_search_point():
    stops = (SimpleNamespace(location=(4.1, 44.1), index=10), SimpleNamespace(location=(4.3, 43.9), index=50))

    assert refuel.detour_vias(stops, 30, (4.2, 44.0)) == [(4.1, 44.1), (4.2, 44.0), (4.3, 43.9)]


def test_on_the_optimal_route_the_station_is_the_only_via():
    assert refuel.detour_vias((), 30, (4.2, 44.0)) == [(4.2, 44.0)]


PLANNED_ROUTE = a_route(10_000, 10_000 / (130 / 3.6), 10, start=(2.0, 46.55))
PLANNED = SimpleNamespace(start="start", end="end", route=PLANNED_ROUTE, stops=())
TOLLS = {PLANNED_ROUTE.node_ids: 10.0}


def a_detour(extra_s, node_id, tolls=10.0, leg_distance=(52_000.0, 48_000.0)):
    route = Route(node_ids=(node_id,), coordinates=((0.0, 0.0),), segment_distance=(), segment_duration=(),
                  distance=sum(leg_distance), duration=PLANNED_ROUTE.duration + extra_s, weight=0.0,
                  leg_distance=leg_distance)
    TOLLS[route.node_ids] = tolls
    return route


def toll_cost(route):
    return TOLLS[route.node_ids]


class DetourRouters:
    def __init__(self, answers=None, default=None):
        self.answers = answers or {}
        self.default = default
        self.requests = 0
        self.open = 0
        self.most_open = 0

    async def route_via(self, base, start, vias, end):
        self.requests += 1
        self.open += 1
        self.most_open = max(self.most_open, self.open)
        await asyncio.sleep(0.01)
        self.open -= 1

        answer = self.answers.get(tuple(vias[-1]), self.default)
        if isinstance(answer, Exception):
            raise answer
        return answer


def plan(routers, fuel=10, parameters=None):
    return asyncio.run(refuel.plan(routers, PLANNED, parameters or a_car(10, 10), fuel, toll_cost))


def test_no_more_than_4_detour_requests_are_open_at_once():
    found = [refuel.Candidate(station=SimpleNamespace(id=k, latitude=47.0 + 0.01 * k, longitude=2.0),
                              fuel="Gazole (B7)", price=1.8, distance_km=k)
             for k in range(1, 11)]
    routers = DetourRouters(default=a_detour(600, 900))

    asyncio.run(refuel.detours(routers, PLANNED, 5, found))

    assert routers.requests == 10
    assert routers.most_open == 4


def test_a_station_without_a_detour_route_is_left_out(store, fixed_rates):
    insert_station(store, 1, 47.01, 2.0, DIESEL)
    insert_station(store, 2, 47.02, 2.0, DIESEL)
    routers = DetourRouters({(2.0, 47.01): NoRoute("no road")}, default=a_detour(600, 901))

    answer = plan(routers)

    assert [station["latitude"] for station in answer["stations"]] == [47.02]


def test_a_router_failure_fails_the_plan(store, fixed_rates):
    insert_station(store, 1, 47.01, 2.0, DIESEL)
    routers = DetourRouters(default=RouterUnavailable("the router is down"))

    with pytest.raises(RouterUnavailable):
        plan(routers)


def test_the_cost_adds_the_fuel_the_toll_change_and_the_time(fixed_rates):
    assert round(refuel.stop_cost(45, 1.800, 2.10, 600), 2) == 86.43


def test_a_detour_that_avoids_a_toll_lowers_the_cost(store, fixed_rates):
    insert_station(store, 1, 47.01, 2.0, DIESEL)
    routers = DetourRouters(default=a_detour(600, 902, tolls=7.0))

    [station] = plan(routers)["stations"]

    assert station["toll_difference"] == -3.0
    assert station["cost"] == 81.33


def test_the_cost_decides_the_order_not_the_price(store, fixed_rates):
    insert_station(store, 1, 47.01, 2.0, [["Gazole (B7)", "2026-11-06", "1.800"]], name="A")
    insert_station(store, 2, 47.02, 2.0, [["Gazole (B7)", "2026-11-06", "1.750"]], name="B")
    routers = DetourRouters({(2.0, 47.01): a_detour(600, 903), (2.0, 47.02): a_detour(1800, 904)})

    answer = plan(routers)

    assert answer["liters"] == 45.0
    assert [(station["name"], station["cost"]) for station in answer["stations"]] == [("A", 84.33), ("B", 88.75)]


def test_the_fuel_lasts_to_the_destination():
    routers = DetourRouters()

    assert plan(routers, fuel=40, parameters=a_car(6, 6)) == {"stop_needed": False, "fuel_left": 34.0}
    assert routers.requests == 0


def test_the_answer_lists_the_10_cheapest_stops(store, fixed_rates):
    for station_id in range(1, 31):
        insert_station(store, station_id, 47.0 + 0.001 * station_id, 2.0,
                       [["Gazole (B7)", "2026-11-06", f"{2.000 - 0.001 * station_id:.3f}"]], name=str(station_id))
    routers = DetourRouters(default=a_detour(600, 905))

    stations = plan(routers)["stations"]

    assert [station["name"] for station in stations] == [str(k) for k in range(30, 20, -1)]
    assert [station["cost"] for station in stations] == sorted(station["cost"] for station in stations)


def test_each_listed_station_carries_its_keys(store, fixed_rates):
    insert_station(store, 1, 47.01, 2.0, DIESEL)
    routers = DetourRouters(default=a_detour(600, 906, tolls=12.10))

    [station] = plan(routers)["stations"]

    assert station == {
        "name": "Leclerc",
        "address": ["Rue de quimper", "29520 Chateauneuf du faou"],
        "latitude": 47.01,
        "longitude": 2.0,
        "google_url": "https://www.google.com/maps/search/?api=1&query=47.010000%2C2.000000",
        "distance": 52_000.0,
        "badge": None,
        "fuel": "Gazole (B7)",
        "price": 1.8,
        "detour_duration": pytest.approx(600),
        "toll_difference": 2.1,
        "fuel_cost": 81.0,
        "cost": 86.43,
    }


def test_on_a_split_route_the_distance_runs_through_the_stops_before_the_station(store, fixed_rates):
    insert_station(store, 1, 47.01, 2.0, DIESEL)
    stops = (SimpleNamespace(location=(2.0, 46.70), index=2), SimpleNamespace(location=(2.0, 47.30), index=8))
    planned = SimpleNamespace(start="start", end="end", route=PLANNED_ROUTE, stops=stops)
    routers = DetourRouters(default=a_detour(600, 907, leg_distance=(30_000.0, 25_000.0, 45_000.0, 10_000.0)))

    answer = asyncio.run(refuel.plan(routers, planned, a_car(10, 10), 10, toll_cost))

    assert answer["stations"][0]["distance"] == 55_000.0


def test_the_station_link_opens_its_position():
    assert refuel.station_link(48.209, -3.818) == (
        "https://www.google.com/maps/search/?api=1&query=48.209000%2C-3.818000")


def test_no_candidate_gives_an_empty_list(store, fixed_rates):
    routers = DetourRouters()

    assert plan(routers) == {"stop_needed": True, "liters": 45.0, "stations": []}
    assert routers.requests == 0


@pytest.mark.parametrize("services,address,badge", [
    (["Automate CB 24/24", "Lavage automatique"], ["Rue de quimper"], "24"),
    (["Automate CB 24/24"], ["Autoroute A7"], "24"),
    ([], ["Autoroute A7"], "Autoroute"),
    ([], ["aire de l'autoroute"], "Autoroute"),
    ([], ["Aire de Beaune"], "Aire"),
    ([], ["aire des Volcans"], "Aire"),
    ([], ["aire du Poitou"], "Aire"),
    ([], ["aire d'Orange"], "Aire"),
    ([], ["aire d’Orange"], "Aire"),
    ([], ["A71aire de ste thorette"], "Aire"),
    ([], ["38460 Saint hilaire de brens"], None),
    ([], ["Zi portuaire des mielles"], None),
    ([], ["Rue de quimper", "29520 Chateauneuf du faou"], None),
])
def test_the_badge_of_a_station(services, address, badge):
    assert refuel.station_badge(services, address) == badge


def test_a_listed_station_carries_its_badge(store, fixed_rates):
    insert_station(store, 1, 47.01, 2.0, DIESEL, services=["Automate CB 24/24"])
    routers = DetourRouters(default=a_detour(600, 908))

    [station] = plan(routers)["stations"]

    assert station["badge"] == "24"
