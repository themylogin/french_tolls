# -*- coding=utf-8 -*-
import dataclasses
import re

from sqlalchemy.dialects.sqlite import insert

from . import db
from .models import Car

__all__ = ["FUEL_TYPES", "GAUGE_STEPS", "CarDialog", "CarParameters", "CarReply", "answer_button", "answer_text",
           "describe", "load_car", "number_text", "parse_car", "parse_consumption", "parse_reserve_km",
           "parse_tank_volume", "save_car", "start", "station_fuels"]

FUEL_TYPES = (
    ("diesel", "Diesel", ("Gazole (B7)",)),
    ("95", "95", ("SP95-E10 (E10)", "SP95 (E5)")),
    ("98", "98", ("SP98 (E5)",)),
)

# The steps of the three gauges on the picture, in the order of its buttons.
GAUGE_STEPS = (24, 16, 12)


@dataclasses.dataclass(frozen=True)
class CarParameters:
    fuel_type: str
    tank_volume: int
    consume_80: float
    consume_130: float
    reserve_km: float
    # The web dialog does not ask it. The bot always sets it before it saves.
    gauge_steps: int | None = None


@dataclasses.dataclass(frozen=True)
class CarDialog:
    token: str
    step: str
    tank_volume: int | None = None
    gauge_steps: int | None = None
    fuel_type: str | None = None
    consume_80: float | None = None
    consume_130: float | None = None


@dataclasses.dataclass(frozen=True)
class CarReply:
    text: str
    dialog: CarDialog | None
    buttons: tuple = ()
    save: CarParameters | None = None
    pressed_text: str | None = None
    # The reply is the gauge picture, with the text as its caption.
    photo: bool = False


def start(token, parameters):
    if parameters is None:
        return _ask_tank_volume(CarDialog(token=token, step="tank_volume"))

    return _ask_whether_to_change(f"Your car parameters:\n\n{describe(parameters)}\n\nDo you want to change them?",
                                  CarDialog(token=token, step="confirm"))


def answer_text(dialog, text):
    if dialog.step == "confirm":
        return _ask_whether_to_change("Do you want to change them?", dialog)

    if dialog.step == "tank_volume":
        volume = parse_tank_volume(text)
        if volume is None:
            return CarReply(text="The tank volume must be a whole number of 30 or more. Enter it again.",
                            dialog=dialog)
        return _ask_gauge("How many sections does your fuel gauge have?",
                          dataclasses.replace(dialog, step="gauge", tank_volume=volume))

    if dialog.step == "gauge":
        return _ask_gauge("Choose your gauge with a button.", dialog)

    if dialog.step == "fuel_type":
        return _ask_fuel_type("Choose the fuel type with a button.", dialog)

    if dialog.step == "reserve_km":
        reserve_km = parse_reserve_km(text)
        if reserve_km is None:
            return CarReply(text="The reserve must be a number from 0 to 500 km, for example 50. Enter it again.",
                            dialog=dialog)
        parameters = CarParameters(fuel_type=dialog.fuel_type, tank_volume=dialog.tank_volume,
                                   consume_80=dialog.consume_80, consume_130=dialog.consume_130,
                                   gauge_steps=dialog.gauge_steps, reserve_km=reserve_km)
        return CarReply(text=f"Your car parameters are saved.\n\n{describe(parameters)}", dialog=None,
                        save=parameters)

    consumption = parse_consumption(text)
    if consumption is None:
        return CarReply(text="The consumption must be a number more than 0 and less than 30, for example 6.5. "
                             "Enter it again.",
                        dialog=dialog)

    if dialog.step == "consume_80":
        return _ask_consumption(130, dataclasses.replace(dialog, step="consume_130", consume_80=consumption))

    if consumption < dialog.consume_80:
        return CarReply(text="The consumption at 130 km/h must be equal to or more than the consumption at 80 km/h, "
                             f"{number_text(dialog.consume_80)} L/100 km. Enter it again.",
                        dialog=dialog)

    return CarReply(text="At how many kilometers of range do you want to refuel? Enter it, for example 50.",
                    dialog=dataclasses.replace(dialog, step="reserve_km", consume_130=consumption))


def answer_button(dialog, token, choice):
    if dialog is None or dialog.token != token:
        return _expired(dialog)

    if dialog.step == "gauge" and choice in {str(steps) for steps in GAUGE_STEPS}:
        reply = _ask_fuel_type("Choose the fuel type.",
                               dataclasses.replace(dialog, step="fuel_type", gauge_steps=int(choice)))
        return dataclasses.replace(reply, pressed_text=f"Gauge: {choice} sections")

    if dialog.step == "fuel_type" and choice in _labels():
        reply = _ask_consumption(80, dataclasses.replace(dialog, step="consume_80", fuel_type=choice))
        return dataclasses.replace(reply, pressed_text=f"Fuel type: {_labels()[choice]}")

    if dialog.step == "confirm" and choice == "yes":
        return _ask_tank_volume(dataclasses.replace(dialog, step="tank_volume"))

    if dialog.step == "confirm" and choice == "no":
        return CarReply(text="Your car parameters are unchanged.", dialog=None)

    return _expired(dialog)


def _expired(dialog):
    return CarReply(text="This question has expired. Send /car to start again.", dialog=dialog)


def _ask_whether_to_change(text, dialog):
    return CarReply(text=text, dialog=dialog, buttons=((("Yes", "yes"), ("No", "no")),))


def _ask_tank_volume(dialog):
    return CarReply(text="Enter the tank volume in liters.", dialog=dialog)


def _ask_gauge(text, dialog):
    return CarReply(text=text, dialog=dialog, buttons=(tuple((str(steps), str(steps)) for steps in GAUGE_STEPS),),
                    photo=True)


def _ask_fuel_type(text, dialog):
    return CarReply(text=text, dialog=dialog, buttons=tuple(((label, key),) for key, label in _labels().items()))


def _ask_consumption(speed, dialog):
    return CarReply(text=f"Enter the consumption at {speed} km/h in liters per 100 km.", dialog=dialog)


def parse_tank_volume(text):
    # Eighteen digits always fit the 64-bit SQLite integer.
    match = re.fullmatch(r"\s*(\d{1,18})\s*", text)
    if match is None:
        return None

    volume = int(match.group(1))
    if volume < 30:
        return None

    return volume


def _decimal(text):
    match = re.fullmatch(r"\s*(\d+)(?:[.,](\d+))?\s*", text)
    if match is None:
        return None

    return float(".".join(filter(None, match.groups())))


def parse_consumption(text):
    consumption = _decimal(text)
    if consumption is None or not 0 < consumption < 30:
        return None

    return consumption


def parse_reserve_km(text):
    reserve_km = _decimal(text)
    if reserve_km is None or reserve_km > 500:
        return None

    return reserve_km


def parse_car(data):
    if not isinstance(data, dict):
        return None

    fuel_type = data.get("fuel_type")
    tank_volume = data.get("tank_volume")
    consume_80 = data.get("consume_80")
    consume_130 = data.get("consume_130")
    reserve_km = data.get("reserve_km")
    if not isinstance(fuel_type, str) or fuel_type not in _labels():
        return None
    if not _is_whole_number(tank_volume) or tank_volume < 30:
        return None
    if not _is_consumption(consume_80) or not _is_consumption(consume_130):
        return None
    if consume_130 < consume_80:
        return None
    if not _is_reserve_km(reserve_km):
        return None

    return CarParameters(fuel_type=fuel_type, tank_volume=tank_volume,
                         consume_80=float(consume_80), consume_130=float(consume_130),
                         reserve_km=float(reserve_km))


def _is_whole_number(value):
    # JSON `true` arrives as a bool, and a bool is an int.
    return isinstance(value, int) and not isinstance(value, bool)


def _is_consumption(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)) and 0 < value < 30


def _is_reserve_km(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)) and 0 <= value <= 500


def describe(parameters):
    return "\n".join([
        f"Tank volume: {parameters.tank_volume} L",
        f"Gauge: {parameters.gauge_steps} sections",
        f"Fuel type: {_labels()[parameters.fuel_type]}",
        f"At 80 km/h: {number_text(parameters.consume_80)} L/100 km",
        f"At 130 km/h: {number_text(parameters.consume_130)} L/100 km",
        f"Reserve: {number_text(parameters.reserve_km)} km",
    ])


def station_fuels(fuel_type):
    return {key: names for key, _label, names in FUEL_TYPES}[fuel_type]


def _labels():
    return {key: label for key, label, _station_fuels in FUEL_TYPES}


def number_text(value):
    # `:g` shows 29.99999 as 30, which is outside the limits.
    return f"{value:.6f}".rstrip("0").rstrip(".")


async def load_car(telegram_user_id):
    async with db.Session() as session:
        row = await session.get(Car, telegram_user_id)
        if row is None or row.gauge_steps not in GAUGE_STEPS:
            return None

        return CarParameters(fuel_type=row.fuel_type, tank_volume=row.tank_volume,
                             consume_80=row.consume_80, consume_130=row.consume_130,
                             gauge_steps=row.gauge_steps, reserve_km=row.reserve_km)


async def save_car(telegram_user_id, parameters):
    values = dataclasses.asdict(parameters)
    async with db.Session() as session:
        await session.execute(
            insert(Car)
            .values(telegram_user_id=telegram_user_id, **values)
            .on_conflict_do_update(index_elements=[Car.telegram_user_id], set_=values))
        await session.commit()
