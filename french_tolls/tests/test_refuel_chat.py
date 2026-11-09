# -*- coding=utf-8 -*-
import pytest

from .. import refuel_chat
from ..car import CarParameters


def labels(steps):
    return [" ".join(label for label, _step in row) for row in refuel_chat.GAUGES[steps]]


def steps_of(steps):
    return [[step for _label, step in row] for row in refuel_chat.GAUGES[steps]]


def test_the_24_step_gauge():
    assert labels(24) == ["1 . . | . . 3/4", "3/4 . . | . . 1/2", "1/2 . . | . . 1/4", "1/4 . . | . . 0"]
    assert steps_of(24) == [list(range(24, 17, -1)), list(range(18, 11, -1)), list(range(12, 5, -1)),
                            list(range(6, -1, -1))]


def test_the_16_step_gauge():
    assert labels(16) == ["1 . | , 3/4", "3/4 . | , 1/2", "1/2 . | , 1/4", "1/4 . | , 0"]
    assert steps_of(16) == [list(range(16, 11, -1)), list(range(12, 7, -1)), list(range(8, 3, -1)),
                            list(range(4, -1, -1))]


def test_the_12_step_gauge():
    assert labels(12) == ["1 . 5/6 . 2/3 . 1/2", "1/2 . 1/3 . 1/6 . 0"]
    assert steps_of(12) == [list(range(12, 5, -1)), list(range(6, -1, -1))]


def test_a_row_starts_with_the_step_that_ends_the_row_before_it():
    for rows in refuel_chat.GAUGES.values():
        for before, row in zip(rows, rows[1:]):
            assert before[-1] == row[0]


@pytest.mark.parametrize("step,steps,mark", [
    (8, 16, "1/2"),
    (21, 24, "7/8"),
    (0, 12, "0"),
    (16, 16, "1"),
    (13, 16, "13/16"),
])
def test_the_mark_of_a_step(step, steps, mark):
    assert refuel_chat.gauge_mark(step, steps) == mark


@pytest.mark.parametrize("text,range_km", [
    ("120", 120.0),
    ("87,5", 87.5),
    (" 0 ", 0.0),
    ("3000", 3000.0),
])
def test_a_range_is_read(text, range_km):
    assert refuel_chat.parse_range(text) == range_km


@pytest.mark.parametrize("text", ["3001", "half", "48.85, 2.35", "-5", "120 km", ""])
def test_other_text_is_not_a_range(text):
    assert refuel_chat.parse_range(text) is None


def a_station(**changes):
    station = {
        "name": "Leclerc",
        "google_url": "https://www.google.com/maps/search/?api=1&query=47.010000%2C2.000000",
        "badge": None,
        "distance_from_previous": 235_400.0,
        "price": 1.799,
        "detour_duration": 420.0,
        "toll_difference": 0.0,
    }
    return {**station, **changes}


def test_one_station_with_a_badge():
    text = refuel_chat.station_list([a_station(badge="24")])

    assert text.split("\n") == [
        '1. <a href="https://www.google.com/maps/search/?api=1&amp;query=47.010000%2C2.000000">Leclerc</a>'
        " <b>24</b> · 235 km",
        "1.799 €/L · +7 min",
    ]


def test_a_station_without_a_badge_has_no_bold_text():
    first_line = refuel_chat.station_list([a_station()]).split("\n")[0]

    assert "<b>" not in first_line
    assert first_line.endswith(">Leclerc</a> · 235 km")


def test_a_detour_that_pays_more_tolls():
    assert refuel_chat.station_list([a_station(toll_difference=1.15)]).split("\n")[1] == (
        "1.799 €/L · +7 min · +1.15 €")


def test_a_detour_that_saves_time_and_tolls():
    assert refuel_chat.station_list([a_station(detour_duration=-120.0, toll_difference=-1.25)]).split("\n")[1] == (
        "1.799 €/L · -2 min · -1.25 €")


def test_the_stations_are_numbered_with_an_empty_line_between_them():
    text = refuel_chat.station_list([a_station(name=f"S{number}") for number in range(1, 11)])

    blocks = text.split("\n\n")
    assert len(blocks) == 10
    assert [block.split(".")[0] for block in blocks] == [str(number) for number in range(1, 11)]
    assert text.startswith("1. <a ")


def test_the_paragraph_of_one_station_keeps_its_number():
    assert refuel_chat.station_paragraph(3, a_station(toll_difference=-3.4)).split("\n") == [
        '3. <a href="https://www.google.com/maps/search/?api=1&amp;query=47.010000%2C2.000000">Leclerc</a>'
        " · 235 km",
        "1.799 €/L · +7 min · -3.40 €",
    ]


def test_a_name_with_html_characters_is_escaped():
    assert ">A&amp;B &lt;24h&gt;</a>" in refuel_chat.station_list([a_station(name="A&B <24h>")])


@pytest.mark.parametrize("name", [None, "", "  "])
def test_a_station_without_a_name_is_unnamed(name):
    assert ">Unnamed station</a>" in refuel_chat.station_list([a_station(name=name)])


def test_the_keyboard_of_ten_stations():
    assert refuel_chat.station_rows(10) == [["1", "2", "3", "4", "5"], ["6", "7", "8", "9", "10"]]


def test_the_keyboard_of_seven_stations():
    assert refuel_chat.station_rows(7) == [["1", "2", "3", "4", "5"], ["6", "7"]]


def test_enough_fuel():
    assert refuel_chat.no_stop_text({"stop_needed": False, "fuel_left": 12.7}) == (
        "No need to refuel: you'll arrive with 12 L.")


def test_enough_range():
    assert refuel_chat.no_stop_text({"stop_needed": False, "range_left": 83.4}) == (
        "No need to refuel: you'll arrive with 83 km of range.")


def a_car(reserve_km):
    return CarParameters(fuel_type="diesel", tank_volume=50, consume_80=5.5, consume_130=7.2, reserve_km=reserve_km)


@pytest.mark.parametrize("reserve_km,shown", [(50.0, "50"), (42.5, "42.5")])
def test_no_station_names_the_reserve_in_km(reserve_km, shown):
    assert refuel_chat.no_station_text(a_car(reserve_km)) == (
        f"No gas station sells this fuel within 50 km of the point where the range left reaches {shown} km.")
