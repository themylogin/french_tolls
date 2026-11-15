# -*- coding=utf-8 -*-
"""The refuel dialog of the bot, from `Plan refuel` to `Drive with Google`.

Here rather than in the unit suite: `bot` imports `route`, which loads the booth
artefacts at import. The integration store has no gas station, so the flow
tests replace `bot.plan_stops` with prepared answers. Only the first test runs
`plan_stops` itself, against fake routers.
"""
import asyncio
import copy
import sqlite3
from urllib.parse import parse_qs, urlparse

import pytest

from .. import bot, route
from ..car import CarParameters
from ..config import config
from ..drive import Part, Stop
from ..osrm import RouterUnavailable, Snap
from ..refuel import Start
from .chat import USER_ID, Chat, labelled
from .google_replay import Replay
from .journeys import by_key
from .test_split_route import StationRouters, built_route, plan_of, position


def a_car(**changes):
    values = {"fuel_type": "diesel", "tank_volume": 50, "consume_80": 10.0, "consume_130": 10.0, "reserve_km": 50.0,
              "gauge_steps": 16}
    return CarParameters(**{**values, **changes})


def test_a_finished_plan_is_a_part_through_its_station(monkeypatch):
    optimal = built_route(range(1, 31))
    station = position(8)
    routers = StationRouters(optimal, leg_start=(0, 8))
    snap = Snap(location=optimal.coordinates[0], hint="h", nodes=(1, 2), distance_m=0.0)
    planned = route.PlannedRoute(start=snap, end=snap, route=optimal, stops=(), optimal=optimal,
                                 router_url=config.osrm_optimal_url)

    async def fake_planned_route(_routers, _origin, _destination, _name):
        return planned

    async def fake_plan_waypoints(_routers, optimal_, _start, _end, *, max_waypoints):
        return plan_of(optimal_, [5, 20])

    monkeypatch.setattr(bot, "Routers", lambda: routers)
    monkeypatch.setattr(route, "Routers", lambda: routers)
    monkeypatch.setattr(route, "plan_waypoints", fake_plan_waypoints)
    monkeypatch.setattr(bot, "planned_route", fake_planned_route)
    offer = bot.RefuelOffer(route="optimal", drive_token="d1",
                            part=Part(origin=optimal.coordinates[0], destination=optimal.coordinates[-1], cost=0.0))

    answer, part = asyncio.run(bot.plan_stops(offer, a_car(), Start(0, fuel=5.05), ((station[1], station[0]),)))

    assert answer["stop_needed"] is False
    assert part.stops == (Stop(location=station, booths=frozenset(), index=8),)
    assert station in part.waypoints
    assert part.fast_booths is not None


def test_a_finished_plan_on_the_fastest_route_goes_through_its_station_only(monkeypatch):
    fast = built_route(range(1, 31))
    station = position(8)
    routers = StationRouters(fast, leg_start=(0, 8))
    snap = Snap(location=fast.coordinates[0], hint="h", nodes=(1, 2), distance_m=0.0)
    planned = route.PlannedRoute(start=snap, end=snap, route=fast, stops=(), optimal=fast,
                                 router_url=config.osrm_toll_url)

    async def fake_planned_route(_routers, _origin, _destination, name):
        assert name == "fast"
        return planned

    monkeypatch.setattr(bot, "Routers", lambda: routers)
    monkeypatch.setattr(bot, "planned_route", fake_planned_route)
    offer = bot.RefuelOffer(route="fast", drive_token="d1",
                            part=Part(origin=fast.coordinates[0], destination=fast.coordinates[-1], cost=0.0))

    _answer, part = asyncio.run(bot.plan_stops(offer, a_car(), Start(0, fuel=5.05), ((station[1], station[0]),)))

    assert part.stops == (Stop(location=station, booths=frozenset(), index=8),)
    assert part.waypoints == (station,)
    assert part.booths == part.fast_booths
    assert routers.asked == [(config.osrm_toll_url, (station,))] * 2


# --- the flow, with prepared plans ----------------------------------------------

QUESTION = "How much fuel do you have? Choose it on the gauge or enter the range in kilometers."
EXPIRED = "That route has expired. Please send the locations again."
_routes = {}


@pytest.fixture(autouse=True)
def recorded_routes(monkeypatch):
    """Each journey is routed once per suite run: the plans here are prepared, the routes are real."""
    async def get_route(from_, to):
        key = (tuple(from_), tuple(to))
        if key not in _routes:
            _routes[key] = await route.get_route(from_, to)
        return copy.deepcopy(_routes[key])

    monkeypatch.setattr(bot, "get_route", get_route)


@pytest.fixture(autouse=True)
def no_cars():
    with sqlite3.connect("/cache/database.db") as connection:
        connection.execute("DELETE FROM car")


def store_car(tank_volume=50, gauge_steps=16, reserve_km=50.0):
    with sqlite3.connect("/cache/database.db") as connection:
        connection.execute(
            "INSERT INTO car (telegram_user_id, fuel_type, tank_volume, consume_80, consume_130, gauge_steps,"
            " reserve_km) VALUES (?, 'diesel', ?, 5.5, 7.2, ?, ?)",
            (USER_ID, tank_volume, gauge_steps, reserve_km))


class Planner:
    """`bot.plan_stops`, answering from a list, and recording each call."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    async def __call__(self, offer, parameters, start, chosen):
        self.calls.append((offer.route, start, tuple(chosen)))
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def a_station(number):
    return {
        "name": f"Station {number}",
        "address": [],
        "latitude": 45.0 + number / 100,
        "longitude": 4.0,
        "google_url": f"https://www.google.com/maps/search/?api=1&query={45.0 + number / 100:.6f}%2C4.000000",
        "distance": 100_000.0 * number,
        "distance_from_previous": 100_000.0 * number,
        "badge": None,
        "fuel": "Gazole (B7)",
        "price": 1.8,
        "detour_duration": 300.0,
        "toll_difference": 0.0,
        "fuel_cost": 81.0,
        "cost": 90.0,
    }


def with_share(answer, share):
    if share == 0:
        return answer
    return {**answer, "cheaper_share": share, "cheaper_query": f"the query of a {share}% share"}


def a_list(count=10, share=0):
    answer = {"stop_needed": True, "liters": 45.0, "stations": [a_station(n) for n in range(1, count + 1)]}
    return with_share(answer, share), None


def a_destination_list(count=3, share=0):
    stations = [{**a_station(n), "route_index": 500} for n in range(1, count + 1)]
    answer = {"stop_needed": False, "fuel_left": 12.7, "liters": 37.3, "stations": stations}
    return with_share(answer, share), None


def a_cheaper_station(number):
    return {**a_station(number), "name": f"Cheaper {number}", "price": 1.7, "route_index": 100 * number}


class CheaperSearch:
    """`bot.cheaper_stops`, answering from a list, and recording each query."""

    def __init__(self, answers=()):
        self.answers = list(answers)
        self.calls = []

    async def __call__(self, query, parameters):
        self.calls.append(query)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def search_cheaper(monkeypatch, answers=()):
    search = CheaperSearch(answers)
    monkeypatch.setattr(bot, "cheaper_stops", search)
    return search


async def ask(chat, journey, choice):
    """Send a journey, and press `choice` where the answer offers a choice of route."""
    await chat.send_location(journey.origin)
    await chat.send_location(journey.destination)
    if choice is not None and labelled(chat.messages[-1], choice):
        await chat.press_labelled(choice)


def talk(monkeypatch, answers, scenario, key="toll-free", choice="Optimal"):
    """A journey, its `choice` of route, then `scenario`, with `bot.plan_stops` answering `answers`."""
    planner = Planner(answers)
    monkeypatch.setattr(bot, "plan_stops", planner)
    journey = by_key(key)

    async def run():
        async with Replay() as replay:
            async with Chat() as chat:
                await ask(chat, journey, choice)
                await scenario(chat)
            return chat, replay

    chat, replay = asyncio.run(run())
    return chat, planner, replay


def labels(call):
    return [[button["text"] for button in row] for row in (call.markup or {}).get("inline_keyboard", [])]


def the_answer(chat):
    """The last call that drew the answer message with its buttons."""
    return [call for call in chat.sent if "<b>Optimal route:</b>" in call.text and call.buttons][-1]


def markup_removed(chat, message_id):
    return any(call.method == "editMessageReplyMarkup" and call.message_id == message_id
               and call.markup is None for call in chat.sent)


def the_question(chat):
    return next(call for call in chat.sent if call.text == QUESTION)


def question_deleted(chat):
    question = the_question(chat).message_id
    deleted = any(call.method == "deleteMessage" and call.message_id == question for call in chat.sent)
    return deleted and QUESTION not in chat.texts()


async def plan_refuel(chat):
    await chat.press_labelled("Plan refuel")


# --- Plan refuel ------------------------------------------------------------------

def test_plan_refuel_without_a_car_points_to_car(monkeypatch):
    chat, planner, _replay = talk(monkeypatch, [], plan_refuel)

    assert chat.texts()[-1] == "Use /car to set up your car details in order to use this."
    assert not markup_removed(chat, the_answer(chat).message_id)
    assert planner.calls == []


def test_plan_refuel_after_car_asks_the_fuel(monkeypatch):
    async def scenario(chat):
        await chat.press_labelled("Plan refuel")
        store_car()
        await chat.press_labelled("Plan refuel")

    chat, _planner, _replay = talk(monkeypatch, [], scenario)

    assert chat.texts()[-2:] == ["Use /car to set up your car details in order to use this.", QUESTION]


def test_plan_refuel_asks_the_fuel_on_the_gauge_of_the_car(monkeypatch):
    store_car(gauge_steps=16)

    chat, _planner, replay = talk(monkeypatch, [], plan_refuel)

    assert markup_removed(chat, the_answer(chat).message_id)
    assert [" ".join(row) for row in labels(the_question(chat))] == [
        "1 . | , 3/4", "3/4 . | , 1/2", "1/2 . | , 1/4", "1/4 . | , 0"]
    assert replay.spent == 0


def test_plan_refuel_spends_drive_with_google(monkeypatch):
    store_car()

    async def scenario(chat):
        drive_token = labelled(the_answer(chat), "Drive with Google")
        await chat.press_labelled("Plan refuel")
        await chat.press(drive_token, the_answer(chat).message_id)

    chat, _planner, replay = talk(monkeypatch, [], scenario, key="accepted-first-ask")

    assert chat.texts()[-1] == EXPIRED
    assert replay.spent == 0


def test_drive_with_google_spends_plan_refuel(monkeypatch):
    store_car()

    async def scenario(chat):
        plan_token = labelled(the_answer(chat), "Plan refuel")
        await chat.press_labelled("Drive with Google")
        await chat.press(plan_token, the_answer(chat).message_id)

    chat, _planner, _replay = talk(monkeypatch, [], scenario, key="accepted-first-ask")

    assert chat.texts()[-1] == EXPIRED
    assert QUESTION not in chat.texts()


# --- the fuel question --------------------------------------------------------------

def test_a_gauge_press_plans_with_its_liters(monkeypatch):
    store_car(tank_volume=50, gauge_steps=16)

    async def scenario(chat):
        await plan_refuel(chat)
        await chat.press_labelled("1/2")

    chat, planner, _replay = talk(monkeypatch, [a_list()], scenario)

    assert question_deleted(chat)
    assert planner.calls == [("optimal", Start(0, fuel=25.0), ())]


def test_a_mark_between_two_labels_plans_with_its_liters(monkeypatch):
    store_car(tank_volume=50, gauge_steps=24)

    async def scenario(chat):
        await plan_refuel(chat)
        question = the_question(chat)
        await chat.press(f"{question.buttons[0].split(':')[0]}:21", question.message_id)

    _chat, planner, _replay = talk(monkeypatch, [a_list()], scenario)

    assert planner.calls == [("optimal", Start(0, fuel=43.75), ())]


@pytest.mark.parametrize("text,range_km", [("120", 120.0), ("87,5", 87.5)])
def test_a_typed_range_plans_with_it(monkeypatch, text, range_km):
    store_car()

    async def scenario(chat):
        await plan_refuel(chat)
        await chat.send_text(text)

    chat, planner, _replay = talk(monkeypatch, [a_list()], scenario)

    assert question_deleted(chat)
    assert planner.calls == [("optimal", Start(0, range_km=range_km), ())]


@pytest.mark.parametrize("text", ["half", "3001", "48.85, 2.35"])
def test_other_text_at_the_fuel_question_is_refused(monkeypatch, text):
    store_car()

    async def scenario(chat):
        await plan_refuel(chat)
        await chat.send_text(text)
        await chat.press_labelled("1/2")

    chat, planner, _replay = talk(monkeypatch, [a_list()], scenario)

    assert "Choose it on the gauge or enter the range in kilometers, for example 120." in chat.texts()
    assert len(planner.calls) == 1


def test_a_shared_location_closes_the_fuel_question(monkeypatch):
    store_car()

    async def scenario(chat):
        await plan_refuel(chat)
        await chat.send_location(by_key("toll-free").origin)
        await chat.press_labelled("1/2")

    chat, planner, _replay = talk(monkeypatch, [], scenario)

    assert chat.texts()[-2:] == ["Now, send me the destination location", EXPIRED]
    assert planner.calls == []


def test_reset_closes_the_fuel_question(monkeypatch):
    store_car()

    async def scenario(chat):
        await plan_refuel(chat)
        await chat.send_command("reset")
        await chat.send_text("120")

    chat, planner, _replay = talk(monkeypatch, [], scenario)

    assert chat.texts()[-1].startswith("This is a bot that will calculate a route within mainland France")
    assert planner.calls == []


def test_a_second_plan_refuel_closes_the_first_question(monkeypatch):
    store_car()

    async def scenario(chat):
        await plan_refuel(chat)
        first = the_question(chat)
        await ask(chat, by_key("toll-free"), "Optimal")
        await chat.press_labelled("Plan refuel")
        await chat.press(first.buttons[0], first.message_id)

    chat, planner, _replay = talk(monkeypatch, [], scenario)

    assert chat.texts()[-1] == EXPIRED
    assert planner.calls == []


def test_a_gauge_after_a_typed_range_has_expired(monkeypatch):
    store_car()

    async def scenario(chat):
        await plan_refuel(chat)
        await chat.send_text("120")
        question = the_question(chat)
        await chat.press(question.buttons[0], question.message_id)

    chat, planner, _replay = talk(monkeypatch, [a_list()], scenario)

    assert chat.texts()[-1] == EXPIRED
    assert planner.calls == [("optimal", Start(0, range_km=120.0), ())]


def test_the_plan_is_on_the_chosen_fastest_route(monkeypatch):
    store_car()

    async def scenario(chat):
        await chat.press_labelled("Fastest")
        await chat.press_labelled("Plan refuel")
        await chat.press_labelled("1/2")

    _chat, planner, replay = talk(monkeypatch, [a_list()], scenario, key="accepted-first-ask", choice=None)

    assert planner.calls[0][0] == "fast"
    assert replay.spent == 0


def test_the_plan_is_on_the_chosen_superoptimal_route(monkeypatch):
    store_car()

    async def scenario(chat):
        await chat.press_labelled("Super")
        await chat.press_labelled("Plan refuel")
        await chat.press_labelled("1/2")

    _chat, planner, replay = talk(monkeypatch, [a_list()], scenario, key="superoptimal", choice=None)

    assert planner.calls[0][0] == "super_optimal"
    assert replay.spent == 0


# --- the answers of the plan --------------------------------------------------------

async def half_a_tank(chat):
    await plan_refuel(chat)
    await chat.press_labelled("1/2")


def test_a_plan_shows_that_it_is_busy_and_then_its_answer(monkeypatch):
    store_car()

    chat, _planner, _replay = talk(monkeypatch, [a_list()], half_a_tank)

    [busy] = [call for call in chat.sent if call.text == "⏳ Finding gas stations..."]
    assert chat.messages[-1].message_id == busy.message_id
    assert chat.texts()[-1].startswith('1. <a href="')


@pytest.mark.parametrize("answer,text", [
    ({"stop_needed": False, "fuel_left": 12.7, "liters": 37.3, "stations": []},
     "No need to refuel: you'll arrive with 12 L. No gas station sells this fuel within 50 km of your destination."),
    ({"stop_needed": False, "range_left": 83.4, "liters": 45.0, "stations": []},
     "No need to refuel: you'll arrive with 83 km of range. "
     "No gas station sells this fuel within 50 km of your destination."),
])
def test_no_stop_needed_offers_drive_with_google(monkeypatch, answer, text):
    store_car()

    chat, _planner, _replay = talk(monkeypatch, [(answer, None)], half_a_tank)

    assert chat.texts()[-1] == text
    assert labels(chat.messages[-1]) == [["Drive with Google"]]


def test_no_stop_needed_drives_the_route_without_a_station(monkeypatch):
    store_car()

    async def scenario(chat):
        await half_a_tank(chat)
        await chat.press_labelled("Drive with Google")

    no_stop = {"stop_needed": False, "fuel_left": 12.7, "liters": 37.3, "stations": []}
    chat, _planner, replay = talk(monkeypatch, [(no_stop, None)], scenario)

    [part] = chat.parts
    query = parse_qs(urlparse(part.links[-1]).query)
    destination = by_key("toll-free").destination
    assert query["origin"] == ["Current Location"]
    assert query["destination"] == [f"{destination[1]:.6f},{destination[0]:.6f}"]
    assert "waypoints" not in query
    assert "Please enable Avoid tolls before driving." in part.text
    assert replay.spent == 0


def test_the_stations_are_listed_with_a_number_keyboard(monkeypatch):
    store_car()

    chat, _planner, _replay = talk(monkeypatch, [a_list(10)], half_a_tank)

    listed = chat.messages[-1]
    assert listed.parameters["parse_mode"] == "HTML"
    assert listed.parameters["link_preview_options"] == {"is_disabled": True}
    assert [block.split(".")[0] for block in listed.text.split("\n\n")] == [str(n) for n in range(1, 11)]
    assert labels(listed) == [["1", "2", "3", "4", "5"], ["6", "7", "8", "9", "10"]]


def test_a_number_press_chooses_its_station(monkeypatch):
    store_car()

    async def scenario(chat):
        await half_a_tank(chat)
        await chat.press_labelled("3")

    chat, planner, _replay = talk(monkeypatch, [a_list(), a_list(7)], scenario)

    first_list = next(m for m in chat.messages if m.text.startswith("3. <a "))
    assert first_list.text == (
        '3. <a href="https://www.google.com/maps/search/?api=1&amp;query=45.030000%2C4.000000">Station 3</a>'
        " · 300 km\n1.800 €/L · +5 min")
    assert labels(first_list) == []
    third = a_station(3)
    assert planner.calls[1] == ("optimal", Start(0, fuel=25.0), ((third["latitude"], third["longitude"]),))
    assert labels(chat.messages[-1]) == [["1", "2", "3", "4", "5"], ["6", "7"]]


def test_the_next_station_comes_after_the_chosen_ones(monkeypatch):
    store_car()

    async def scenario(chat):
        await half_a_tank(chat)
        await chat.press_labelled("3")
        await chat.press_labelled("2")

    _chat, planner, _replay = talk(monkeypatch, [a_list(), a_list(), a_list()], scenario)

    first, second = a_station(3), a_station(2)
    assert planner.calls[2][2] == ((first["latitude"], first["longitude"]), (second["latitude"], second["longitude"]))


def a_finished_part():
    """A toll-free plan with two gas stations, as `plan_stops` gives it."""
    nodes = tuple((1.0 + i * 0.01, 45.0) for i in range(201))
    stations = (Stop(location=nodes[50], booths=frozenset(), index=50),
                Stop(location=nodes[150], booths=frozenset(), index=150))
    return Part(origin=nodes[0], destination=nodes[-1], cost=0.0, nodes=nodes,
                waypoints=tuple(stop.location for stop in stations), booths=frozenset(), stops=stations)


def test_a_finished_plan_offers_drive_with_google(monkeypatch):
    store_car()

    async def scenario(chat):
        await half_a_tank(chat)
        await chat.press_labelled("3")

    finished = ({"stop_needed": False, "fuel_left": 12.7}, a_finished_part())
    chat, _planner, replay = talk(monkeypatch, [a_list(), finished], scenario)

    assert chat.texts()[-1].startswith("3. <a ")
    assert labels(chat.messages[-1]) == [["Drive with Google"]]
    assert "⏳ Finding gas stations..." not in chat.texts()
    assert replay.spent == 0


def test_a_plan_with_too_many_stops_is_not_offered(monkeypatch):
    store_car()

    async def scenario(chat):
        await half_a_tank(chat)
        await chat.press_labelled("3")

    chat, _planner, _replay = talk(monkeypatch, [a_list(), ({"stop_needed": False, "fuel_left": 12.7}, None)],
                                   scenario)

    assert chat.texts()[-1] == "The refuel plan has too many stops for one Google Maps link."
    assert labels(chat.messages[-1]) == []


def test_no_station_after_a_gauge_press(monkeypatch):
    store_car(reserve_km=50.0)

    chat, _planner, _replay = talk(monkeypatch, [a_list(0)], half_a_tank)

    assert chat.texts()[-1] == (
        "No gas station sells this fuel within 50 km of the point where the range left reaches 50 km.")


def test_no_station_after_a_typed_range(monkeypatch):
    store_car(reserve_km=42.5)

    async def scenario(chat):
        await plan_refuel(chat)
        await chat.send_text("120")

    chat, _planner, _replay = talk(monkeypatch, [a_list(0)], scenario)

    assert chat.texts()[-1] == (
        "No gas station sells this fuel within 50 km of the point where the range left reaches 42.5 km.")


def test_no_station_after_a_chosen_station_names_the_reserve_in_km(monkeypatch):
    store_car(reserve_km=50.0)

    async def scenario(chat):
        await plan_refuel(chat)
        await chat.send_text("120")
        await chat.press_labelled("3")

    chat, _planner, _replay = talk(monkeypatch, [a_list(), a_list(0)], scenario)

    assert chat.texts()[-1] == (
        "No gas station sells this fuel within 50 km of the point where the range left reaches 50 km.")


def test_a_failed_plan_ends_the_plan(monkeypatch):
    store_car()

    chat, _planner, _replay = talk(monkeypatch, [RouterUnavailable("the router is down")], half_a_tank)

    assert chat.texts()[-1] == "Error finding gas stations. I am very sorry for that 😞"
    assert labels(chat.messages[-1]) == []


def test_a_second_press_on_a_list_has_expired(monkeypatch):
    store_car()

    async def scenario(chat):
        await half_a_tank(chat)
        listed = chat.messages[-1]
        await chat.press(labelled(listed, "3"), listed.message_id)
        await chat.press(labelled(listed, "5"), listed.message_id)

    chat, planner, _replay = talk(monkeypatch, [a_list(), a_list()], scenario)

    assert chat.texts()[-1] == EXPIRED
    assert len(planner.calls) == 2


def test_two_applications_do_not_share_a_fuel_question(monkeypatch):
    store_car()
    monkeypatch.setattr(bot, "plan_stops", Planner([]))
    journey = by_key("toll-free")

    async def run():
        async with Chat() as first, Chat() as second:
            await ask(first, journey, "Optimal")
            await first.press_labelled("Plan refuel")
            await second.send_text("120")
            return second

    second = asyncio.run(run())

    assert second.texts()[-1].startswith("This is a bot that will calculate a route within mainland France")


def test_a_finished_plan_is_driven_through_its_stations(monkeypatch):
    store_car()
    part = a_finished_part()

    async def scenario(chat):
        await half_a_tank(chat)
        await chat.press_labelled("3")
        await chat.press_labelled("Drive with Google")

    finished = ({"stop_needed": False, "fuel_left": 12.7}, part)
    chat, _planner, replay = talk(monkeypatch, [a_list(), finished], scenario)

    [sent] = chat.parts[-1:]
    assert "Please enable Avoid tolls before driving." in sent.text
    query = parse_qs(urlparse(sent.links[-1]).query)
    assert query["origin"] == ["Current Location"]
    assert query["waypoints"] == ["45.000000,1.500000|45.000000,2.500000"]
    assert query["destination"] == ["45.000000,3.000000"]
    assert replay.spent == 0


# --- the stations at the destination ------------------------------------------------

def test_the_destination_list_has_numbers_and_drive_with_google(monkeypatch):
    store_car()

    chat, _planner, _replay = talk(monkeypatch, [a_destination_list(3)], half_a_tank)

    listed = chat.messages[-1]
    assert listed.text.split("\n")[0] == (
        "No need to refuel: you'll arrive with 12 L. Still, these are the 3 cheapest gas stations at your destination:")
    assert listed.parameters["parse_mode"] == "HTML"
    assert listed.parameters["link_preview_options"] == {"is_disabled": True}
    assert labels(listed) == [["1", "2", "3"], ["Drive with Google"]]


def test_one_destination_station_uses_the_singular(monkeypatch):
    store_car()

    chat, _planner, _replay = talk(monkeypatch, [a_destination_list(1)], half_a_tank)

    assert chat.texts()[-1].split("\n")[0] == (
        "No need to refuel: you'll arrive with 12 L. Still, this is the cheapest gas station at your destination:")


# --- the cheaper button ---------------------------------------------------------------

CHEAPER_6 = "Cheaper? (6% of gas stations)"
NUMBERS_10 = [["1", "2", "3", "4", "5"], ["6", "7", "8", "9", "10"]]


def test_ten_stations_with_a_share_of_6_offer_the_cheaper_button(monkeypatch):
    store_car()

    chat, _planner, _replay = talk(monkeypatch, [a_list(10, share=6)], half_a_tank)

    assert labels(chat.messages[-1]) == [*NUMBERS_10, [CHEAPER_6]]


def test_three_stations_with_a_share_of_15_offer_the_cheaper_button(monkeypatch):
    store_car()

    chat, _planner, _replay = talk(monkeypatch, [a_list(3, share=15)], half_a_tank)

    assert labels(chat.messages[-1]) == [["1", "2", "3"], ["Cheaper? (15% of gas stations)"]]


def test_the_list_after_a_chosen_station_offers_the_cheaper_button(monkeypatch):
    store_car()

    async def scenario(chat):
        await half_a_tank(chat)
        await chat.press_labelled("3")

    chat, _planner, _replay = talk(monkeypatch, [a_list(), a_list(7, share=4)], scenario)

    assert labels(chat.messages[-1]) == [["1", "2", "3", "4", "5"], ["6", "7"], ["Cheaper? (4% of gas stations)"]]


def test_a_destination_list_with_a_share_of_6_has_four_rows(monkeypatch):
    store_car()

    chat, _planner, _replay = talk(monkeypatch, [a_destination_list(10, share=6)], half_a_tank)

    assert labels(chat.messages[-1]) == [*NUMBERS_10, [CHEAPER_6], ["Drive with Google"]]


def test_no_cheaper_search_before_the_press(monkeypatch):
    store_car()
    search = search_cheaper(monkeypatch)

    talk(monkeypatch, [a_list(10, share=6)], half_a_tank)

    assert search.calls == []


def markup_edits(chat, message_id):
    return [call for call in chat.sent if call.method == "editMessageReplyMarkup" and call.message_id == message_id]


def test_a_press_on_the_cheaper_button_lists_the_cheaper_stations(monkeypatch):
    store_car()
    search = search_cheaper(monkeypatch, [[a_cheaper_station(n) for n in (1, 2, 3)]])
    lists = []

    async def scenario(chat):
        await half_a_tank(chat)
        lists.append(chat.messages[-1])
        await chat.press_labelled(CHEAPER_6)

    chat, _planner, replay = talk(monkeypatch, [a_list(10, share=6)], scenario)

    [stop_list] = lists
    assert [labels(call) for call in markup_edits(chat, stop_list.message_id)] == [NUMBERS_10]
    [busy] = [call for call in chat.sent if call.text == "⏳ Finding gas stations..." and
              call.message_id != stop_list.message_id]
    cheaper_list = chat.messages[-1]
    assert cheaper_list.message_id == busy.message_id
    assert cheaper_list.text.startswith(
        '1. <a href="https://www.google.com/maps/search/?api=1&amp;query=45.010000%2C4.000000">Cheaper 1</a>')
    assert labels(cheaper_list) == [["1", "2", "3"]]
    assert search.calls == ["the query of a 6% share"]
    assert replay.spent == 0


def test_a_press_on_the_cheaper_button_of_a_destination_list_keeps_drive_with_google(monkeypatch):
    store_car()
    search_cheaper(monkeypatch, [[a_cheaper_station(1)]])
    lists = []

    async def scenario(chat):
        await half_a_tank(chat)
        lists.append(chat.messages[-1])
        await chat.press_labelled("Cheaper? (8% of gas stations)")

    chat, _planner, _replay = talk(monkeypatch, [a_destination_list(3, share=8)], scenario)

    [destination_list] = lists
    assert [labels(call) for call in markup_edits(chat, destination_list.message_id)] == [
        [["1", "2", "3"], ["Drive with Google"]]]


@pytest.mark.parametrize("found,text", [
    ([], "None of them is within 5 km of your route."),
    (RouterUnavailable("the router is down"), "Error finding gas stations. I am very sorry for that 😞"),
], ids=["no cheaper station", "a router failure"])
def test_the_stop_list_stays_open_after_a_cheaper_search_without_stations(monkeypatch, found, text):
    store_car()
    search_cheaper(monkeypatch, [found])

    async def scenario(chat):
        await half_a_tank(chat)
        stop_list = chat.messages[-1]
        await chat.press_labelled(CHEAPER_6)
        assert chat.texts()[-1] == text
        assert labels(chat.messages[-1]) == []
        await chat.press(labelled(stop_list, "2"), stop_list.message_id)

    _chat, planner, _replay = talk(monkeypatch, [a_list(10, share=6), a_list()], scenario)

    second = a_station(2)
    assert planner.calls[1][2] == ((second["latitude"], second["longitude"]),)


# --- a choice on a cheaper list or a destination list ---------------------------------

def test_a_choice_on_the_cheaper_list_places_the_station_at_its_route_point(monkeypatch):
    store_car()
    search_cheaper(monkeypatch, [[a_cheaper_station(n) for n in (1, 2, 3)]])

    async def scenario(chat):
        await half_a_tank(chat)
        await chat.press_labelled(CHEAPER_6)
        await chat.press_labelled("2")

    chat, planner, _replay = talk(monkeypatch, [a_list(10, share=6), a_list()], scenario)

    assert any(message.text.startswith('2. <a href="') and ">Cheaper 2</a>" in message.text
               and labels(message) == [] for message in chat.messages)
    second = a_cheaper_station(2)
    assert planner.calls[1][2] == ((second["latitude"], second["longitude"], 200),)


def test_a_choice_on_the_destination_list_finishes_the_plan(monkeypatch):
    store_car()

    async def scenario(chat):
        await half_a_tank(chat)
        await chat.press_labelled("2")

    finished = ({"stop_needed": False, "fuel_left": 40.0}, a_finished_part())
    chat, planner, replay = talk(monkeypatch, [a_destination_list(3), finished], scenario)

    second = a_station(2)
    assert planner.calls[1][2] == ((second["latitude"], second["longitude"], 500),)
    assert chat.texts()[-1].startswith("2. <a ")
    assert labels(chat.messages[-1]) == [["Drive with Google"]]
    assert "⏳ Finding gas stations..." not in chat.texts()
    assert replay.spent == 0


def test_a_choice_on_the_cheaper_list_of_a_destination_list(monkeypatch):
    store_car()
    search_cheaper(monkeypatch, [[a_cheaper_station(n) for n in (1, 2)]])

    async def scenario(chat):
        await half_a_tank(chat)
        await chat.press_labelled("Cheaper? (8% of gas stations)")
        await chat.press_labelled("2")

    finished = ({"stop_needed": False, "fuel_left": 40.0}, a_finished_part())
    _chat, planner, _replay = talk(monkeypatch, [a_destination_list(3, share=8), finished], scenario)

    second = a_cheaper_station(2)
    assert planner.calls[1][2] == ((second["latitude"], second["longitude"], 200),)


@pytest.mark.parametrize("first,second", [("cheaper", "stop"), ("stop", "cheaper")])
def test_a_choice_on_one_list_closes_the_other(monkeypatch, first, second):
    store_car()
    search_cheaper(monkeypatch, [[a_cheaper_station(n) for n in (1, 2, 3)]])
    numbers = {"cheaper": "2", "stop": "5"}

    async def scenario(chat):
        await half_a_tank(chat)
        stop_list = chat.messages[-1]
        await chat.press_labelled(CHEAPER_6)
        lists = {"stop": stop_list, "cheaper": chat.messages[-1]}
        await chat.press(labelled(lists[first], numbers[first]), lists[first].message_id)
        await chat.press(labelled(lists[second], numbers[second]), lists[second].message_id)

    chat, planner, _replay = talk(monkeypatch, [a_list(10, share=6), a_list()], scenario)

    assert chat.texts()[-1] == EXPIRED
    assert len(planner.calls) == 2


def test_a_choice_on_the_destination_list_spends_its_drive_with_google(monkeypatch):
    store_car()

    async def scenario(chat):
        await half_a_tank(chat)
        destination_list = chat.messages[-1]
        drive_token = labelled(destination_list, "Drive with Google")
        await chat.press(labelled(destination_list, "2"), destination_list.message_id)
        await chat.press(drive_token, destination_list.message_id)

    finished = ({"stop_needed": False, "fuel_left": 40.0}, a_finished_part())
    chat, _planner, replay = talk(monkeypatch, [a_destination_list(3), finished], scenario)

    assert chat.texts()[-1] == EXPIRED
    assert chat.parts == []
    assert replay.spent == 0


def test_drive_with_google_closes_the_destination_list(monkeypatch):
    store_car()

    async def scenario(chat):
        await half_a_tank(chat)
        destination_list = chat.messages[-1]
        await chat.press(labelled(destination_list, "Drive with Google"), destination_list.message_id)
        await chat.press(labelled(destination_list, "2"), destination_list.message_id)

    chat, planner, _replay = talk(monkeypatch, [a_destination_list(3)], scenario)

    assert chat.texts()[-1] == EXPIRED
    assert len(planner.calls) == 1


def test_a_cheaper_button_after_a_choice_has_expired(monkeypatch):
    store_car()
    search = search_cheaper(monkeypatch)

    async def scenario(chat):
        await half_a_tank(chat)
        stop_list = chat.messages[-1]
        await chat.press(labelled(stop_list, "3"), stop_list.message_id)
        await chat.press(labelled(stop_list, CHEAPER_6), stop_list.message_id)

    chat, _planner, _replay = talk(monkeypatch, [a_list(10, share=6), a_list()], scenario)

    assert chat.texts()[-1] == EXPIRED
    assert search.calls == []


def test_the_cheaper_button_of_an_earlier_journey_has_expired(monkeypatch):
    store_car()
    search = search_cheaper(monkeypatch)

    async def scenario(chat):
        await half_a_tank(chat)
        first_list = chat.messages[-1]
        await ask(chat, by_key("toll-free"), "Optimal")
        await half_a_tank(chat)
        await chat.press(labelled(first_list, CHEAPER_6), first_list.message_id)

    chat, _planner, _replay = talk(monkeypatch, [a_list(10, share=6), a_destination_list(3, share=8)], scenario)

    assert chat.texts()[-1] == EXPIRED
    assert search.calls == []
