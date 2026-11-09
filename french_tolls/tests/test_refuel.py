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


def a_car(consume_80, consume_130, tank_volume=50, fuel_type="diesel", reserve=5, reserve_km=50):
    return CarParameters(fuel_type=fuel_type, tank_volume=tank_volume, consume_80=consume_80,
                         consume_130=consume_130, reserve=reserve, reserve_km=reserve_km)


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


def test_a_larger_reserve_moves_the_search_point_nearer_to_the_origin():
    route = a_route(10_000, 10_000 / (130 / 3.6), 10)

    index, fuel_left = refuel.fuel_walk(route, a_car(10, 10, reserve=8), 10)

    assert index == 2
    assert fuel_left == pytest.approx(8)


@pytest.mark.parametrize("fuel", [4, 5])
def test_5_l_or_less_at_the_origin_makes_the_origin_the_search_point(fuel):
    route = a_route(10_000, 10_000 / (130 / 3.6), 10)

    assert refuel.fuel_walk(route, a_car(10, 10), fuel) == (0, fuel)


def test_no_search_point_when_the_fuel_lasts():
    route = a_route(10_000, 10_000 / (130 / 3.6), 10)

    index, fuel_left = refuel.fuel_walk(route, a_car(6, 6), 40)

    assert index is None
    assert fuel_left == pytest.approx(34)


def test_a_reserve_above_the_fuel_left_at_the_destination_gives_a_search_point():
    route = a_route(10_000, 10_000 / (130 / 3.6), 10)

    index, fuel_left = refuel.fuel_walk(route, a_car(6, 6, reserve=35), 40)

    assert index == 9
    assert fuel_left == pytest.approx(34.6)


def test_a_segment_of_0_s_uses_no_fuel():
    route = a_route(0, 0, 3)

    assert refuel.fuel_walk(route, a_car(6, 8), 20) == (None, 20)


def test_a_walk_from_a_chosen_station_starts_with_its_fuel():
    route = a_route(10_000, 10_000 / (130 / 3.6), 60)

    index, fuel_left = refuel.fuel_walk(route, a_car(10, 10), 50, start=3)

    assert index == 48
    assert fuel_left == pytest.approx(5)


def test_a_walk_from_a_late_station_can_reach_the_destination():
    route = a_route(10_000, 10_000 / (130 / 3.6), 60)

    index, fuel_left = refuel.fuel_walk(route, a_car(10, 10), 50, start=55)

    assert index is None
    assert fuel_left == pytest.approx(45)


def test_the_range_search_point_is_where_the_range_first_reaches_the_range_reserve():
    route = a_route(10_000, 10_000 / (130 / 3.6), 10)

    index, range_left = refuel.range_walk(route, 80, 50)

    assert index == 3
    assert range_left == pytest.approx(50)


@pytest.mark.parametrize("range_km", [50, 40])
def test_a_range_at_or_below_the_range_reserve_makes_the_origin_the_search_point(range_km):
    route = a_route(10_000, 10_000 / (130 / 3.6), 10)

    assert refuel.range_walk(route, range_km, 50) == (0, range_km)


def test_no_range_search_point_when_the_range_lasts():
    route = a_route(10_000, 10_000 / (130 / 3.6), 10)

    index, range_left = refuel.range_walk(route, 183.4, 50)

    assert index is None
    assert range_left == pytest.approx(83.4)


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
    stops = (SimpleNamespace(location=(4.1, 44.1), index=10, booths=(11, 12)),
             SimpleNamespace(location=(4.3, 43.9), index=50, booths=(13, 14)))

    assert refuel.detour_vias(stops, 30, (4.2, 44.0)) == [(4.1, 44.1), (4.2, 44.0), (4.3, 43.9)]


def test_on_the_optimal_route_the_station_is_the_only_via():
    assert refuel.detour_vias((), 30, (4.2, 44.0)) == [(4.2, 44.0)]


PLANNED_ROUTE = a_route(10_000, 10_000 / (130 / 3.6), 10, start=(2.0, 46.55))
OPTIMAL_GRAPH = "http://optimal-graph"
PLANNED = SimpleNamespace(start="start", end="end", route=PLANNED_ROUTE, stops=(), router_url=OPTIMAL_GRAPH)
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
        self.bases = set()

    async def route_via(self, base, start, vias, end):
        self.bases.add(base)
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
    return asyncio.run(refuel.plan(routers, PLANNED, parameters or a_car(10, 10), toll_cost, fuel=fuel))


def test_no_more_than_4_detour_requests_are_open_at_once():
    found = [refuel.Candidate(station=SimpleNamespace(id=k, latitude=47.0 + 0.01 * k, longitude=2.0),
                              fuel="Gazole (B7)", price=1.8, distance_km=k)
             for k in range(1, 11)]
    routers = DetourRouters(default=a_detour(600, 900))

    asyncio.run(refuel.detours(routers, PLANNED, (), 5, found))

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
        "distance_from_previous": 52_000.0,
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
    stops = (SimpleNamespace(location=(2.0, 46.70), index=2, booths=(11, 12)),
             SimpleNamespace(location=(2.0, 47.30), index=8, booths=(13, 14)))
    planned = SimpleNamespace(start="start", end="end", route=PLANNED_ROUTE, stops=stops, router_url=OPTIMAL_GRAPH)
    routers = DetourRouters(default=a_detour(600, 907, leg_distance=(30_000.0, 25_000.0, 45_000.0, 10_000.0)))

    answer = asyncio.run(refuel.plan(routers, planned, a_car(10, 10), toll_cost, fuel=10))

    assert answer["stations"][0]["distance"] == 55_000.0
    assert answer["stations"][0]["distance_from_previous"] == 55_000.0


def test_the_station_link_opens_its_position():
    assert refuel.station_link(48.209, -3.818) == (
        "https://www.google.com/maps/search/?api=1&query=48.209000%2C-3.818000")


def test_a_lasting_range_gives_the_range_left():
    routers = DetourRouters()

    answer = asyncio.run(refuel.plan(routers, PLANNED, a_car(6, 6), toll_cost, range_km=183.4))

    assert answer == {"stop_needed": False, "range_left": 83.4}
    assert routers.requests == 0


def test_a_stop_after_a_range_buys_the_tank_volume_less_the_reserve(store, fixed_rates):
    routers = DetourRouters()

    answer = asyncio.run(refuel.plan(routers, PLANNED, a_car(10, 10, reserve=8), toll_cost, range_km=80))

    assert answer == {"stop_needed": True, "liters": 42.0, "stations": []}


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


A = (47.0, 2.0)
B = (51.06, 2.0)


def a_leg_route(segments, leg_start, base):
    """Segments of 10 km at 130 km/h from 46.55 N, one node every 0.09 degree, with the given legs."""
    node_ids = tuple(range(base, base + segments + 1))
    ends = (*leg_start[1:], segments)
    route = Route(
        node_ids=node_ids,
        coordinates=tuple((2.0, 46.55 + 0.09 * i) for i in range(segments + 1)),
        segment_distance=(10_000.0,) * segments,
        segment_duration=(10_000 / (130 / 3.6),) * segments,
        distance=10_000.0 * segments,
        duration=10_000 / (130 / 3.6) * segments,
        weight=0.0,
        leg_distance=tuple(10_000.0 * (end - begin) for begin, end in zip(leg_start, ends)),
        leg_start=leg_start,
    )
    TOLLS[route.node_ids] = 10.0
    return route


class ViaRouters:
    """Answers `route_via` from the via list, and records each list it was asked."""

    def __init__(self, answers, detour=None):
        self.answers = answers
        self.detour = detour
        self.asked = []
        self.bases = set()

    async def route_via(self, base, start, vias, end):
        self.bases.add(base)
        vias = tuple(tuple(via) for via in vias)
        self.asked.append(vias)
        return self.answers.get(vias, self.detour)


def at(latitude, longitude):
    return (longitude, latitude)


def plan_chosen(routers, chosen, planned=PLANNED, link_through=None):
    return asyncio.run(refuel.plan(routers, planned, a_car(10, 10), toll_cost, fuel=10, chosen=chosen,
                                   link_through=link_through))


def test_a_chosen_station_before_the_search_point_comes_before_the_station():
    vias = [refuel.Via(location=(4.1, 44.1), index=3, chosen=True), refuel.Via(location=(4.3, 43.9), index=50,
                                                                               chosen=False)]

    assert refuel.detour_vias(vias, 30, (4.2, 44.0)) == [(4.1, 44.1), (4.2, 44.0), (4.3, 43.9)]


def test_the_distance_after_a_chosen_station_runs_through_it(store, fixed_rates):
    insert_station(store, 1, 46.55 + 0.09 * 67 + 0.01, 2.0, DIESEL)
    detour = a_detour(600, 909, leg_distance=(220_000.0, 310_000.0, 100_000.0))
    routers = ViaRouters({(at(*A),): a_leg_route(80, (0, 22), base=2000)}, detour=detour)

    [station] = plan_chosen(routers, [A])["stations"]

    assert station["distance"] == 530_000.0
    assert station["distance_from_previous"] == 310_000.0


def test_a_chosen_station_restarts_the_walk_with_a_full_tank(store, fixed_rates):
    insert_station(store, 1, B[0], B[1], DIESEL)
    through_a = a_leg_route(60, (0, 5), base=3000)
    detour = Route(node_ids=(910,), coordinates=((0.0, 0.0),), segment_distance=(), segment_duration=(),
                   distance=0.0, duration=through_a.duration + 600, weight=0.0,
                   leg_distance=(50_000.0, 450_000.0, 100_000.0))
    TOLLS[detour.node_ids] = 10.0
    routers = ViaRouters({(at(*A),): through_a}, detour=detour)

    [station] = plan_chosen(routers, [A])["stations"]

    assert routers.asked == [(at(*A),), (at(*A), at(*B))]
    assert station["detour_duration"] == pytest.approx(600)


def test_after_a_chosen_station_a_range_plan_walks_by_the_fuel(store, fixed_rates):
    insert_station(store, 1, B[0], B[1], DIESEL)
    through_a = a_leg_route(60, (0, 5), base=3100)
    detour = Route(node_ids=(913,), coordinates=((0.0, 0.0),), segment_distance=(), segment_duration=(),
                   distance=0.0, duration=through_a.duration + 600, weight=0.0,
                   leg_distance=(50_000.0, 450_000.0, 100_000.0))
    TOLLS[detour.node_ids] = 10.0
    routers = ViaRouters({(at(*A),): through_a}, detour=detour)

    answer = asyncio.run(refuel.plan(routers, PLANNED, a_car(10, 10), toll_cost, range_km=30, chosen=[A]))

    assert routers.asked == [(at(*A),), (at(*A), at(*B))]
    assert answer["liters"] == 45.0


def test_a_station_after_a_lasting_range_is_refused():
    routers = ViaRouters({})

    with pytest.raises(refuel.UnneededStation):
        asyncio.run(refuel.plan(routers, PLANNED, a_car(10, 10), toll_cost, range_km=300, chosen=[A]))

    assert routers.asked == []


def test_the_chosen_stations_and_the_detours_are_routed_on_the_graph_of_the_planned_route(store, fixed_rates):
    insert_station(store, 1, B[0], B[1], DIESEL)
    planned = SimpleNamespace(start="start", end="end", route=PLANNED_ROUTE, stops=(), router_url="http://fast-graph")
    routers = ViaRouters({(at(*A),): a_leg_route(60, (0, 5), base=3200)}, detour=a_detour(600, 914))

    plan_chosen(routers, [A], planned=planned)

    assert routers.bases == {"http://fast-graph"}


def test_two_chosen_stations_are_routed_one_at_a_time(store, fixed_rates):
    third = (46.55 + 0.09 * 95 + 0.01, 2.0)
    insert_station(store, 1, third[0], third[1], DIESEL)
    routers = ViaRouters({
        (at(*A),): a_leg_route(60, (0, 5), base=4000),
        (at(*A), at(*B)): a_leg_route(100, (0, 5, 50), base=5000),
    }, detour=a_detour(600, 911))

    [station] = plan_chosen(routers, [A, B])["stations"]

    assert routers.asked == [(at(*A),), (at(*A), at(*B)), (at(*A), at(*B), at(*third))]
    assert station["latitude"] == third[0]


def test_a_station_that_the_plan_does_not_need_is_refused():
    routers = ViaRouters({(at(*A),): a_leg_route(20, (0, 5), base=6000)})

    with pytest.raises(refuel.UnneededStation):
        plan_chosen(routers, [A, B])


class LinkRecorder:
    def __init__(self):
        self.calls = []

    async def __call__(self, route, vias):
        self.calls.append((route, vias))
        return "https://www.google.com/maps/dir/?api=1"


def test_a_finished_plan_carries_its_route_and_link():
    through_a = a_leg_route(20, (0, 5), base=7000)
    link = LinkRecorder()

    answer = plan_chosen(ViaRouters({(at(*A),): through_a}), [A], link_through=link)

    assert answer == {
        "stop_needed": False,
        "fuel_left": 35.0,
        "route": {"nodes": [list(c) for c in through_a.coordinates],
                  "google_url": "https://www.google.com/maps/dir/?api=1"},
    }
    assert link.calls == [(through_a, [refuel.Via(location=at(*A), index=5, chosen=True)])]


def test_a_finished_plan_without_a_link_builder_carries_no_route():
    through_a = a_leg_route(20, (0, 5), base=7100)

    answer = plan_chosen(ViaRouters({(at(*A),): through_a}), [A])

    assert answer == {"stop_needed": False, "fuel_left": 35.0}


def test_the_link_gets_the_split_stops_and_the_chosen_stations():
    split_stop = (2.0, 47.3)
    planned = SimpleNamespace(start="start", end="end", route=PLANNED_ROUTE, router_url=OPTIMAL_GRAPH,
                              stops=(SimpleNamespace(location=split_stop, index=8, booths=(31, 32)),))
    through_both = a_leg_route(20, (0, 5, 12), base=8000)
    link = LinkRecorder()

    plan_chosen(ViaRouters({(at(*A), split_stop): through_both}), [A], planned=planned, link_through=link)

    assert link.calls[0][1] == [refuel.Via(location=at(*A), index=5, chosen=True),
                                refuel.Via(location=split_stop, index=12, chosen=False, booths=(31, 32))]


def test_a_split_stop_keeps_its_booths_after_a_chosen_station():
    split_stop = (2.0, 47.3)
    planned = SimpleNamespace(start="start", end="end", route=PLANNED_ROUTE, router_url=OPTIMAL_GRAPH,
                              stops=(SimpleNamespace(location=split_stop, index=8, booths=(31, 32)),))
    routers = ViaRouters({(at(*A), split_stop): a_leg_route(20, (0, 5, 12), base=8100)})

    _route, vias, start = asyncio.run(
        refuel.through_chosen(routers, planned, a_car(10, 10), refuel.Start(0, fuel=10), [A]))

    assert vias == [refuel.Via(location=at(*A), index=5, chosen=True, booths=()),
                    refuel.Via(location=split_stop, index=12, chosen=False, booths=(31, 32))]
    assert start == refuel.Start(5, fuel=50)


def test_without_chosen_stations_the_link_is_not_built():
    link = LinkRecorder()

    answer = asyncio.run(refuel.plan(DetourRouters(), PLANNED, a_car(6, 6), toll_cost, fuel=40,
                                     link_through=link))

    assert answer == {"stop_needed": False, "fuel_left": 34.0}
    assert link.calls == []


def test_the_distance_from_the_previous_stop_runs_through_a_split_stop_between(store, fixed_rates):
    split_stop = (2.0, 48.0)
    planned = SimpleNamespace(start="start", end="end", route=PLANNED_ROUTE, router_url=OPTIMAL_GRAPH,
                              stops=(SimpleNamespace(location=split_stop, index=8, booths=(31, 32)),))
    insert_station(store, 1, 46.55 + 0.09 * 67 + 0.01, 2.0, DIESEL)
    detour = a_detour(600, 912, leg_distance=(200_000.0, 150_000.0, 180_000.0, 100_000.0))
    routers = ViaRouters({(at(*A), split_stop): a_leg_route(80, (0, 22, 40), base=9000)}, detour=detour)

    [station] = plan_chosen(routers, [A], planned=planned)["stations"]

    assert station["distance"] == 530_000.0
    assert station["distance_from_previous"] == 330_000.0
