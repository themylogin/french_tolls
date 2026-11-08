# -*- coding=utf-8 -*-
import asyncio
import sqlite3

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .. import car, db


@pytest.mark.parametrize("text,expected", [
    ("30", 30),
    ("50", 50),
    (" 60 ", 60),
])
def test_a_tank_volume_of_30_or_more_is_accepted(text, expected):
    assert car.parse_tank_volume(text) == expected


@pytest.mark.parametrize("text", [
    "29",
    "50.5",
    "50 l",
    "fifty",
    "-50",
    "",
    "99999999999999999999",
])
def test_any_other_tank_volume_is_refused(text):
    assert car.parse_tank_volume(text) is None


@pytest.mark.parametrize("text,expected", [
    ("6,5", 6.5),
    ("6.5", 6.5),
    ("0.1", 0.1),
    ("7", 7.0),
    ("29.9", 29.9),
    (" 5,5 ", 5.5),
])
def test_a_consumption_above_0_and_below_30_is_accepted(text, expected):
    assert car.parse_consumption(text) == expected


@pytest.mark.parametrize("text", [
    "0",
    "0.0",
    "30",
    "-5",
    "1e1",
    "nan",
    "inf",
    "6.5 l",
    "6.",
    "",
    "9" * 400,
])
def test_any_other_consumption_is_refused(text):
    assert car.parse_consumption(text) is None


@pytest.mark.parametrize("text,expected", [
    ("0", 0.0),
    ("5", 5.0),
    (" 7,5 ", 7.5),
    ("49.9", 49.9),
])
def test_a_reserve_below_the_tank_volume_is_accepted(text, expected):
    assert car.parse_reserve(text, 50) == expected


@pytest.mark.parametrize("text", ["50", "60", "-1", "five", "5 l", ""])
def test_any_other_reserve_is_refused(text):
    assert car.parse_reserve(text, 50) is None


def test_a_valid_car_object_gives_the_car():
    data = {"fuel_type": "diesel", "tank_volume": 50, "consume_80": 5.5, "consume_130": 7.2, "reserve": 5}

    assert car.parse_car(data) == car.CarParameters(fuel_type="diesel", tank_volume=50, consume_80=5.5,
                                                    consume_130=7.2, reserve=5.0)


def test_equal_consumptions_are_valid():
    data = {"fuel_type": "95", "tank_volume": 40, "consume_80": 6, "consume_130": 6, "reserve": 5}

    assert car.parse_car(data) == car.CarParameters(fuel_type="95", tank_volume=40, consume_80=6.0,
                                                    consume_130=6.0, reserve=5.0)


@pytest.mark.parametrize("changes", [
    {"tank_volume": 29},
    {"tank_volume": 50.5},
    {"tank_volume": True},
    {"tank_volume": "50"},
    {"consume_80": 0},
    {"consume_80": 30},
    {"consume_80": float("nan")},
    {"consume_130": float("inf")},
    {"consume_80": "6.5"},
    {"consume_130": True},
    {"fuel_type": "e85"},
    {"fuel_type": ["diesel"]},
    {"consume_80": 7.2, "consume_130": 5.5},
    {"reserve": 50},
    {"reserve": -1},
    {"reserve": "5"},
    {"reserve": True},
    {"reserve": float("nan")},
])
def test_a_car_object_out_of_its_limits_is_refused(changes):
    data = {"fuel_type": "diesel", "tank_volume": 50, "consume_80": 5.5, "consume_130": 7.2, "reserve": 5,
            **changes}

    assert car.parse_car(data) is None


@pytest.mark.parametrize("key", ["fuel_type", "tank_volume", "consume_80", "consume_130", "reserve"])
def test_a_car_object_without_a_key_is_refused(key):
    data = {"fuel_type": "diesel", "tank_volume": 50, "consume_80": 5.5, "consume_130": 7.2, "reserve": 5}
    del data[key]

    assert car.parse_car(data) is None


@pytest.mark.parametrize("data", [None, [], "car"])
def test_a_car_that_is_not_an_object_is_refused(data):
    assert car.parse_car(data) is None


def a_bot_car(**changes):
    values = {"fuel_type": "diesel", "tank_volume": 50, "consume_80": 5.5, "consume_130": 7.2, "gauge_steps": 16,
              "reserve": 5.0}
    return car.CarParameters(**{**values, **changes})


def test_a_car_is_described_in_six_lines():
    parameters = a_bot_car(consume_130=7.0)

    assert car.describe(parameters).split("\n") == [
        "Tank volume: 50 L",
        "Gauge: 16 sections",
        "Fuel type: Diesel",
        "At 80 km/h: 5.5 L/100 km",
        "At 130 km/h: 7 L/100 km",
        "Reserve: 5 L",
    ]


@pytest.mark.parametrize("consumption,expected", [
    (29.99999, "At 80 km/h: 29.99999 L/100 km"),
    (0.00001, "At 80 km/h: 0.00001 L/100 km"),
    (10.0, "At 80 km/h: 10 L/100 km"),
])
def test_a_consumption_is_shown_without_trailing_zeros(consumption, expected):
    parameters = a_bot_car(fuel_type="95", tank_volume=40, consume_80=consumption, consume_130=30.0)

    assert car.describe(parameters).split("\n")[3] == expected


def test_a_reserve_is_shown_without_trailing_zeros():
    assert car.describe(a_bot_car(reserve=7.5)).split("\n")[5] == "Reserve: 7.5 L"


def button_labels(reply):
    return [[label for label, _choice in row] for row in reply.buttons]


def test_a_driver_without_a_car_is_asked_for_the_tank_volume():
    reply = car.start("c1", None)

    assert reply.text == "Enter the tank volume in liters."
    assert reply.buttons == ()
    assert reply.dialog == car.CarDialog(token="c1", step="tank_volume")
    assert reply.save is None


def test_a_driver_with_a_car_sees_it_and_is_asked_to_change_it():
    reply = car.start("c1", a_bot_car())

    assert reply.text == (
        "Your car parameters:\n\n"
        "Tank volume: 50 L\n"
        "Gauge: 16 sections\n"
        "Fuel type: Diesel\n"
        "At 80 km/h: 5.5 L/100 km\n"
        "At 130 km/h: 7.2 L/100 km\n"
        "Reserve: 5 L\n\n"
        "Do you want to change them?"
    )
    assert reply.buttons == ((("Yes", "yes"), ("No", "no")),)
    assert reply.dialog == car.CarDialog(token="c1", step="confirm")


def test_a_valid_tank_volume_asks_for_the_gauge():
    reply = car.answer_text(car.CarDialog(token="c1", step="tank_volume"), "30")

    assert reply.text == "How many sections does your fuel gauge have?"
    assert reply.photo
    assert button_labels(reply) == [["24", "16", "12"]]
    assert reply.dialog == car.CarDialog(token="c1", step="gauge", tank_volume=30)


@pytest.mark.parametrize("text", ["29", "50.5", "50 l", "fifty", "99999999999999999999"])
def test_an_invalid_tank_volume_repeats_the_question(text):
    dialog = car.CarDialog(token="c1", step="tank_volume")

    reply = car.answer_text(dialog, text)

    assert reply.text == "The tank volume must be a whole number of 30 or more. Enter it again."
    assert reply.dialog == dialog
    assert reply.save is None


def test_a_typed_gauge_is_refused_with_the_photo_again():
    dialog = car.CarDialog(token="c1", step="gauge", tank_volume=50)

    reply = car.answer_text(dialog, "24")

    assert reply.text == "Choose your gauge with a button."
    assert reply.photo
    assert button_labels(reply) == [["24", "16", "12"]]
    assert reply.dialog == dialog


def test_a_gauge_press_asks_for_the_fuel_type():
    dialog = car.CarDialog(token="c1", step="gauge", tank_volume=50)

    reply = car.answer_button(dialog, "c1", "24")

    assert reply.text == "Choose the fuel type."
    assert reply.pressed_text == "Gauge: 24 sections"
    assert not reply.photo
    assert button_labels(reply) == [["Diesel"], ["95"], ["98"]]
    assert reply.dialog == car.CarDialog(token="c1", step="fuel_type", tank_volume=50, gauge_steps=24)


def test_a_typed_fuel_type_is_refused_with_the_buttons_again():
    dialog = car.CarDialog(token="c1", step="fuel_type", tank_volume=50, gauge_steps=16)

    reply = car.answer_text(dialog, "diesel")

    assert reply.text == "Choose the fuel type with a button."
    assert button_labels(reply) == [["Diesel"], ["95"], ["98"]]
    assert reply.dialog == dialog


def test_a_valid_consumption_at_80_asks_for_the_consumption_at_130():
    dialog = car.CarDialog(token="c1", step="consume_80", tank_volume=50, gauge_steps=16, fuel_type="diesel")

    reply = car.answer_text(dialog, "6,5")

    assert reply.text == "Enter the consumption at 130 km/h in liters per 100 km."
    assert reply.dialog == car.CarDialog(token="c1", step="consume_130", tank_volume=50, gauge_steps=16,
                                         fuel_type="diesel", consume_80=6.5)
    assert reply.save is None


def test_a_consumption_at_130_below_the_one_at_80_repeats_the_question():
    dialog = car.CarDialog(token="c1", step="consume_130", tank_volume=50, gauge_steps=16, fuel_type="diesel",
                           consume_80=7.2)

    reply = car.answer_text(dialog, "5.5")

    assert reply.text == ("The consumption at 130 km/h must be equal to or more than the consumption at 80 km/h, "
                          "7.2 L/100 km. Enter it again.")
    assert reply.dialog == dialog
    assert reply.save is None


def test_a_consumption_at_130_equal_to_the_one_at_80_asks_for_the_reserve():
    dialog = car.CarDialog(token="c1", step="consume_130", tank_volume=50, gauge_steps=16, fuel_type="diesel",
                           consume_80=6.0)

    reply = car.answer_text(dialog, "6")

    assert reply.text == "At how many liters left in the tank do you want to refuel? Enter it, for example 5."
    assert reply.dialog == car.CarDialog(token="c1", step="reserve", tank_volume=50, gauge_steps=16,
                                         fuel_type="diesel", consume_80=6.0, consume_130=6.0)
    assert reply.save is None


@pytest.mark.parametrize("step", ["consume_80", "consume_130"])
@pytest.mark.parametrize("text", ["0", "30", "-5", "1e1", "nan", "6.5 l"])
def test_an_invalid_consumption_repeats_the_question(step, text):
    dialog = car.CarDialog(token="c1", step=step, tank_volume=50, gauge_steps=16, fuel_type="diesel",
                           consume_80=5.5)

    reply = car.answer_text(dialog, text)

    assert reply.text == ("The consumption must be a number more than 0 and less than 30, for example 6.5. "
                          "Enter it again.")
    assert reply.dialog == dialog
    assert reply.save is None


def test_a_valid_reserve_saves_the_six_values():
    dialog = car.CarDialog(token="c1", step="reserve", tank_volume=50, gauge_steps=16, fuel_type="diesel",
                           consume_80=5.5, consume_130=7.2)

    reply = car.answer_text(dialog, "5")

    assert reply.save == a_bot_car()
    assert reply.dialog is None


@pytest.mark.parametrize("text", ["50", "five"])
def test_an_invalid_reserve_repeats_the_question(text):
    dialog = car.CarDialog(token="c1", step="reserve", tank_volume=50, gauge_steps=16, fuel_type="diesel",
                           consume_80=5.5, consume_130=7.2)

    reply = car.answer_text(dialog, text)

    assert reply.text == ("The reserve must be a number of 0 or more and less than the tank volume, 50 L. "
                          "Enter it again.")
    assert reply.dialog == dialog
    assert reply.save is None


def test_a_typed_answer_to_the_change_question_repeats_it():
    dialog = car.CarDialog(token="c1", step="confirm")

    reply = car.answer_text(dialog, "yes")

    assert reply.text == "Do you want to change them?"
    assert reply.buttons == ((("Yes", "yes"), ("No", "no")),)
    assert reply.dialog == dialog


def test_a_fuel_press_asks_for_the_consumption_at_80():
    dialog = car.CarDialog(token="c1", step="fuel_type", tank_volume=50, gauge_steps=16)

    reply = car.answer_button(dialog, "c1", "95")

    assert reply.text == "Enter the consumption at 80 km/h in liters per 100 km."
    assert reply.pressed_text == "Fuel type: 95"
    assert reply.buttons == ()
    assert reply.dialog == car.CarDialog(token="c1", step="consume_80", tank_volume=50, gauge_steps=16,
                                         fuel_type="95")


def test_yes_asks_for_the_tank_volume():
    reply = car.answer_button(car.CarDialog(token="c1", step="confirm"), "c1", "yes")

    assert reply.text == "Enter the tank volume in liters."
    assert reply.pressed_text is None
    assert reply.dialog == car.CarDialog(token="c1", step="tank_volume")


def test_no_keeps_the_car_and_ends_the_dialog():
    reply = car.answer_button(car.CarDialog(token="c1", step="confirm"), "c1", "no")

    assert reply.text == "Your car parameters are unchanged."
    assert reply.dialog is None
    assert reply.save is None


@pytest.mark.parametrize("dialog,token,choice", [
    (None, "c1", "diesel"),
    (None, "c1", "yes"),
    (None, "c1", "24"),
    (car.CarDialog(token="c2", step="fuel_type", tank_volume=50), "c1", "diesel"),
    (car.CarDialog(token="c2", step="gauge", tank_volume=50), "c1", "24"),
    (car.CarDialog(token="c1", step="gauge", tank_volume=50), "c1", "20"),
    (car.CarDialog(token="c1", step="fuel_type", tank_volume=50, gauge_steps=16), "c1", "24"),
    (car.CarDialog(token="c1", step="consume_80", tank_volume=50, fuel_type="diesel"), "c1", "98"),
    (car.CarDialog(token="c1", step="fuel_type", tank_volume=50), "c1", "yes"),
    (car.CarDialog(token="c1", step="confirm"), "c1", "diesel"),
    (car.CarDialog(token="c1", step="fuel_type", tank_volume=50), "c1", "petrol"),
])
def test_a_button_that_does_not_fit_the_current_question_has_expired(dialog, token, choice):
    reply = car.answer_button(dialog, token, choice)

    assert reply.text == "This question has expired. Send /car to start again."
    assert reply.dialog == dialog
    assert reply.save is None
    assert reply.pressed_text is None


class Press(str):
    pass


def run_dialog(parameters, answers):
    reply = car.start("c1", parameters)
    replies = [reply]
    for answer in answers:
        if isinstance(answer, Press):
            reply = car.answer_button(reply.dialog, "c1", answer)
        else:
            reply = car.answer_text(reply.dialog, answer)
        replies.append(reply)
    return replies


def test_six_valid_answers_save_the_car_once():
    replies = run_dialog(None, ["50", Press("16"), Press("diesel"), "5.5", "7.2", "5"])

    assert [reply.save for reply in replies[:-1]] == [None] * 6
    assert replies[-1].save == a_bot_car()
    assert replies[-1].dialog is None
    assert replies[-1].text == (
        "Your car parameters are saved.\n\n"
        "Tank volume: 50 L\n"
        "Gauge: 16 sections\n"
        "Fuel type: Diesel\n"
        "At 80 km/h: 5.5 L/100 km\n"
        "At 130 km/h: 7.2 L/100 km\n"
        "Reserve: 5 L"
    )


def test_the_questions_come_in_order():
    replies = run_dialog(None, ["50", Press("16"), Press("diesel"), "5.5", "7.2"])

    assert [reply.text for reply in replies] == [
        "Enter the tank volume in liters.",
        "How many sections does your fuel gauge have?",
        "Choose the fuel type.",
        "Enter the consumption at 80 km/h in liters per 100 km.",
        "Enter the consumption at 130 km/h in liters per 100 km.",
        "At how many liters left in the tank do you want to refuel? Enter it, for example 5.",
    ]


def test_a_driver_with_a_car_changes_it_after_yes():
    replies = run_dialog(a_bot_car(), [Press("yes"), "60", Press("12"), Press("98"), "6", "8,5", "40"])

    assert [reply.save for reply in replies[:-1]] == [None] * 7
    assert replies[-1].save == car.CarParameters(fuel_type="98", tank_volume=60, consume_80=6.0, consume_130=8.5,
                                                 gauge_steps=12, reserve=40.0)


def test_an_invalid_answer_does_not_skip_a_question():
    replies = run_dialog(None, ["29", "50", "16", Press("16"), "diesel", Press("95"), "0", "5.5", "30", "7.2",
                                "600", "5"])

    assert replies[-1].save == a_bot_car(fuel_type="95")


@pytest.mark.parametrize("label,stored", [("Diesel", "diesel"), ("95", "95"), ("98", "98")])
def test_each_fuel_button_stores_its_fuel_type(label, stored):
    fuel_question = run_dialog(None, ["50", Press("16")])[-1]
    choice = dict(row[0] for row in fuel_question.buttons)[label]

    replies = run_dialog(None, ["50", Press("16"), Press(choice), "5.5", "7.2", "5"])

    assert replies[-1].save.fuel_type == stored


def test_the_fuel_buttons_come_in_one_column_in_this_order():
    fuel_question = run_dialog(None, ["50", Press("16")])[-1]

    assert fuel_question.buttons == ((("Diesel", "diesel"),), (("95", "95"),), (("98", "98"),))


def test_the_gauge_buttons_come_in_one_row_in_this_order():
    gauge_question = run_dialog(None, ["50"])[-1]

    assert gauge_question.buttons == ((("24", "24"), ("16", "16"), ("12", "12")),)


@pytest.mark.parametrize("steps", [24, 16, 12])
def test_each_gauge_button_stores_its_steps(steps):
    replies = run_dialog(None, ["50", Press(str(steps)), Press("diesel"), "5.5", "7.2", "5"])

    assert replies[-1].save.gauge_steps == steps


def alembic_config(db_path):
    config = Config(__file__.rsplit("/", 3)[0] + "/alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return config


@pytest.fixture
def store(tmp_path, monkeypatch):
    db_path = tmp_path / "database.db"
    command.upgrade(alembic_config(db_path), "head")

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db, "Session", async_sessionmaker(engine, expire_on_commit=False))
    yield db_path
    asyncio.run(engine.dispose())


def car_rows(db_path):
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT telegram_user_id, fuel_type, tank_volume, consume_80, consume_130, gauge_steps, reserve"
            " FROM car ORDER BY telegram_user_id"
        ).fetchall()


def test_a_first_save_creates_the_car(store):
    parameters = a_bot_car()

    asyncio.run(car.save_car(777001, parameters))

    assert car_rows(store) == [(777001, "diesel", 50, 5.5, 7.2, 16, 5.0)]
    assert asyncio.run(car.load_car(777001)) == parameters


def test_a_second_save_replaces_the_car(store):
    asyncio.run(car.save_car(777001, a_bot_car()))

    asyncio.run(car.save_car(777001, car.CarParameters(fuel_type="98", tank_volume=60, consume_80=6.0,
                                                       consume_130=8.5, gauge_steps=24, reserve=7.5)))

    assert car_rows(store) == [(777001, "98", 60, 6.0, 8.5, 24, 7.5)]


def test_two_drivers_have_two_cars(store):
    first = a_bot_car()
    second = car.CarParameters(fuel_type="95", tank_volume=45, consume_80=4.8, consume_130=6.9, gauge_steps=12,
                               reserve=8.0)

    asyncio.run(car.save_car(777001, first))
    asyncio.run(car.save_car(777002, second))

    assert asyncio.run(car.load_car(777001)) == first
    assert asyncio.run(car.load_car(777002)) == second


def test_a_driver_without_a_car_has_none(store):
    assert asyncio.run(car.load_car(777001)) is None


def test_a_car_with_an_unknown_gauge_has_none(store):
    with sqlite3.connect(store) as connection:
        connection.execute(
            "INSERT INTO car (telegram_user_id, fuel_type, tank_volume, consume_80, consume_130, gauge_steps)"
            " VALUES (777001, 'diesel', 50, 5.5, 7.2, 10)")

    assert asyncio.run(car.load_car(777001)) is None


def test_a_car_stored_before_the_gauge_and_the_reserve_gets_16_steps_and_5_l(tmp_path):
    db_path = tmp_path / "database.db"
    command.upgrade(alembic_config(db_path), "c5fd29a893f0")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO car (telegram_user_id, fuel_type, tank_volume, consume_80, consume_130)"
            " VALUES (777001, 'diesel', 50, 5.5, 7.2)")

    command.upgrade(alembic_config(db_path), "head")

    assert car_rows(db_path) == [(777001, "diesel", 50, 5.5, 7.2, 16, 5.0)]


def test_a_car_with_a_reserve_in_km_gets_5_l(tmp_path):
    db_path = tmp_path / "database.db"
    command.upgrade(alembic_config(db_path), "f99c669a7732")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO car (telegram_user_id, fuel_type, tank_volume, consume_80, consume_130, gauge_steps,"
            " reserve_km) VALUES (777001, 'diesel', 50, 5.5, 7.2, 24, 80)")

    command.upgrade(alembic_config(db_path), "head")

    assert car_rows(db_path) == [(777001, "diesel", 50, 5.5, 7.2, 24, 5.0)]
