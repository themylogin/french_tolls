# -*- coding=utf-8 -*-
import asyncio
import sqlite3

import pytest

from .. import bot, car
from .chat import USER_ID, Chat


def connect():
    return sqlite3.connect("/cache/database.db")


@pytest.fixture(autouse=True)
def no_cars():
    with connect() as connection:
        connection.execute("DELETE FROM car")


def store_car(fuel_type, tank_volume, consume_80, consume_130):
    with connect() as connection:
        connection.execute(
            "INSERT INTO car (telegram_user_id, fuel_type, tank_volume, consume_80, consume_130)"
            " VALUES (?, ?, ?, ?, ?)",
            (USER_ID, fuel_type, tank_volume, consume_80, consume_130))


def stored_cars():
    with connect() as connection:
        return connection.execute(
            "SELECT telegram_user_id, fuel_type, tank_volume, consume_80, consume_130, gauge_steps, reserve"
            " FROM car").fetchall()


def talk(scenario):
    async def run():
        async with Chat() as chat:
            await scenario(chat)
            return chat

    return asyncio.run(run())


def test_the_menu_names_car():
    async def scenario(chat):
        await bot.post_init(chat.application)

    chat = talk(scenario)

    [menu] = [sent for sent in chat.sent if sent.method == "setMyCommands"]
    assert [(c["command"], c["description"]) for c in menu.parameters["commands"]] == [
        ("help", "Help"),
        ("reset", "Reset the origin location"),
        ("car", "Enter car parameters"),
    ]


def test_six_answers_save_the_car():
    async def scenario(chat):
        await chat.send_command("car")
        await chat.send_text("50")
        await chat.press_labelled("16")
        await chat.press_labelled("Diesel")
        await chat.send_text("5,5")
        await chat.send_text("7.2")
        await chat.send_text("5")

    chat = talk(scenario)

    assert chat.texts() == [
        "Enter the tank volume in liters.",
        "Gauge: 16 sections",
        "Fuel type: Diesel",
        "Enter the consumption at 80 km/h in liters per 100 km.",
        "Enter the consumption at 130 km/h in liters per 100 km.",
        "At how many liters left in the tank do you want to refuel? Enter it, for example 5.",
        "Your car parameters are saved.\n\n"
        "Tank volume: 50 L\n"
        "Gauge: 16 sections\n"
        "Fuel type: Diesel\n"
        "At 80 km/h: 5.5 L/100 km\n"
        "At 130 km/h: 7.2 L/100 km\n"
        "Reserve: 5 L",
    ]
    assert stored_cars() == [(USER_ID, "diesel", 50, 5.5, 7.2, 16, 5.0)]


def test_the_gauge_question_is_a_photo_with_three_buttons():
    async def scenario(chat):
        await chat.send_command("car")
        await chat.send_text("50")

    chat = talk(scenario)

    [photo] = [sent for sent in chat.sent if sent.method == "sendPhoto"]
    assert photo.parameters["caption"] == "How many sections does your fuel gauge have?"
    keyboard = photo.markup["inline_keyboard"]
    assert [[button["text"] for button in row] for row in keyboard] == [["24", "16", "12"]]


def test_a_gauge_press_edits_the_caption_and_asks_for_the_fuel_type():
    async def scenario(chat):
        await chat.send_command("car")
        await chat.send_text("50")
        await chat.press_labelled("24")

    chat = talk(scenario)

    [edit] = [sent for sent in chat.sent if sent.method == "editMessageCaption"]
    assert edit.parameters["caption"] == "Gauge: 24 sections"
    assert edit.markup is None
    assert chat.texts()[-1] == "Choose the fuel type."


def test_a_typed_gauge_sends_the_photo_again():
    async def scenario(chat):
        await chat.send_command("car")
        await chat.send_text("50")
        await chat.send_text("24")

    chat = talk(scenario)

    photos = [sent for sent in chat.sent if sent.method == "sendPhoto"]
    assert [photo.parameters["caption"] for photo in photos] == [
        "How many sections does your fuel gauge have?",
        "Choose your gauge with a button.",
    ]
    assert [[button["text"] for button in row] for row in photos[-1].markup["inline_keyboard"]] == [
        ["24", "16", "12"]]


def test_an_old_gauge_button_has_expired():
    async def scenario(chat):
        await chat.send_command("car")
        await chat.send_text("50")
        await chat.send_command("car")
        await chat.send_text("50")
        first = [sent for sent in chat.sent if sent.method == "sendPhoto"][0]
        await chat.press(first.buttons[-1], first.message_id)
        await chat.press_labelled("16")

    chat = talk(scenario)

    assert chat.texts()[-2:] == ["This question has expired. Send /car to start again.", "Choose the fuel type."]


def test_the_fuel_question_offers_three_buttons():
    async def scenario(chat):
        await chat.send_command("car")
        await chat.send_text("50")
        await chat.press_labelled("16")

    chat = talk(scenario)

    keyboard = chat.messages[-1].markup["inline_keyboard"]
    assert [[button["text"] for button in row] for row in keyboard] == [["Diesel"], ["95"], ["98"]]


def test_an_invalid_answer_repeats_the_question():
    async def scenario(chat):
        await chat.send_command("car")
        await chat.send_text("29")
        await chat.send_text("50")
        await chat.press_labelled("16")
        await chat.send_text("diesel")
        await chat.press_labelled("95")
        await chat.send_text("0")

    chat = talk(scenario)

    assert chat.texts() == [
        "Enter the tank volume in liters.",
        "The tank volume must be a whole number of 30 or more. Enter it again.",
        "Gauge: 16 sections",
        "Choose the fuel type.",
        "Fuel type: 95",
        "Enter the consumption at 80 km/h in liters per 100 km.",
        "The consumption must be a number more than 0 and less than 30, for example 6.5. Enter it again.",
    ]
    assert stored_cars() == []


def test_a_driver_with_a_car_keeps_it_with_no():
    store_car("diesel", 50, 5.5, 7.2)

    async def scenario(chat):
        await chat.send_command("car")
        await chat.press_labelled("No")

    chat = talk(scenario)

    assert chat.texts() == [
        "Your car parameters:\n\n"
        "Tank volume: 50 L\n"
        "Gauge: 16 sections\n"
        "Fuel type: Diesel\n"
        "At 80 km/h: 5.5 L/100 km\n"
        "At 130 km/h: 7.2 L/100 km\n"
        "Reserve: 5 L\n\n"
        "Do you want to change them?",
        "Your car parameters are unchanged.",
    ]
    assert [sent.parameters.get("reply_markup") for sent in chat.sent
            if sent.method == "editMessageReplyMarkup"] == [None]
    assert stored_cars() == [(USER_ID, "diesel", 50, 5.5, 7.2, 16, 5.0)]


def test_a_driver_with_a_car_changes_it_with_yes():
    store_car("diesel", 50, 5.5, 7.2)

    async def scenario(chat):
        await chat.send_command("car")
        await chat.press_labelled("Yes")
        await chat.send_text("60")
        await chat.press_labelled("12")
        await chat.press_labelled("98")
        await chat.send_text("6")
        await chat.send_text("8,5")
        await chat.send_text("40")

    talk(scenario)

    assert stored_cars() == [(USER_ID, "98", 60, 6.0, 8.5, 12, 40.0)]


def test_a_dialog_stopped_before_the_reserve_keeps_the_stored_reserve():
    store_car("diesel", 50, 5.5, 7.2)

    async def scenario(chat):
        await chat.send_command("car")
        await chat.press_labelled("Yes")
        await chat.send_text("60")
        await chat.press_labelled("12")
        await chat.press_labelled("98")
        await chat.send_text("6")
        await chat.send_text("8,5")
        await chat.send_command("car")

    talk(scenario)

    assert stored_cars() == [(USER_ID, "diesel", 50, 5.5, 7.2, 16, 5.0)]


def test_a_decimal_comma_is_a_consumption_and_not_a_location():
    async def scenario(chat):
        await chat.send_command("car")
        await chat.send_text("50")
        await chat.press_labelled("16")
        await chat.press_labelled("Diesel")
        await chat.send_text("6,5")

    chat = talk(scenario)

    assert chat.texts()[-1] == \
        "Enter the consumption at 130 km/h in liters per 100 km."
    assert "Now, send me the destination location" not in chat.texts()


def test_after_the_dialog_a_typed_number_gets_the_help():
    async def scenario(chat):
        await chat.send_command("car")
        await chat.send_text("50")
        await chat.press_labelled("16")
        await chat.press_labelled("Diesel")
        await chat.send_text("5.5")
        await chat.send_text("7.2")
        await chat.send_text("5")
        await chat.send_text("50")

    chat = talk(scenario)

    assert chat.texts()[-1].startswith("This is a bot that will calculate a route within mainland France")


def test_two_applications_do_not_share_a_dialog():
    async def run():
        async with Chat() as first, Chat() as second:
            await first.send_command("car")
            await second.send_text("50")
            return second

    second = asyncio.run(run())

    assert len(second.texts()) == 1
    assert second.texts()[0].startswith("This is a bot that will calculate a route within mainland France")


def test_an_old_fuel_button_has_expired():
    async def scenario(chat):
        await chat.send_command("car")
        await chat.send_text("50")
        await chat.press_labelled("16")
        await chat.send_text("diesel")
        await chat.press_labelled("Diesel")
        await chat.send_text("5.5")
        await chat.send_text("7.2")
        await chat.send_text("5")
        await chat.press_labelled("98")

    chat = talk(scenario)

    assert chat.texts()[-1] == "This question has expired. Send /car to start again."
    assert "That route has expired. Please send the locations again." not in chat.texts()
    assert stored_cars() == [(USER_ID, "diesel", 50, 5.5, 7.2, 16, 5.0)]


def test_car_during_a_dialog_starts_again():
    store_car("diesel", 50, 5.5, 7.2)

    async def scenario(chat):
        await chat.send_command("car")
        await chat.press_labelled("Yes")
        await chat.send_text("60")
        await chat.send_command("car")

    chat = talk(scenario)

    assert chat.texts()[-1].startswith("Your car parameters:\n\nTank volume: 50 L\n")
    assert chat.texts()[-1].endswith("Do you want to change them?")
    assert stored_cars() == [(USER_ID, "diesel", 50, 5.5, 7.2, 16, 5.0)]


def test_car_during_a_dialog_drops_the_answers():
    async def scenario(chat):
        await chat.send_command("car")
        await chat.send_text("60")
        await chat.send_command("car")
        await chat.send_text("70")
        await chat.press_labelled("16")
        await chat.press_labelled("Diesel")
        await chat.send_text("5.5")
        await chat.send_text("7.2")
        await chat.send_text("5")

    chat = talk(scenario)

    assert chat.texts()[2] == "Enter the tank volume in liters."
    assert stored_cars() == [(USER_ID, "diesel", 70, 5.5, 7.2, 16, 5.0)]


def test_a_failed_save_says_so_and_keeps_the_old_car(monkeypatch):
    store_car("diesel", 50, 5.5, 7.2)

    async def failing_save(_telegram_user_id, _parameters):
        raise OSError("disk full")

    monkeypatch.setattr(car, "save_car", failing_save)

    async def scenario(chat):
        await chat.send_command("car")
        await chat.press_labelled("Yes")
        await chat.send_text("60")
        await chat.press_labelled("16")
        await chat.press_labelled("98")
        await chat.send_text("6")
        await chat.send_text("8,5")
        await chat.send_text("5")
        await chat.send_text("50")

    chat = talk(scenario)

    assert chat.texts()[-2] == "Error saving your car parameters. I am very sorry for that 😞"
    assert chat.texts()[-1].startswith("This is a bot that will calculate a route within mainland France")
    assert stored_cars() == [(USER_ID, "diesel", 50, 5.5, 7.2, 16, 5.0)]
