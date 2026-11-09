# -*- coding=utf-8 -*-
"""What the refuel dialog of the bot shows and reads, without Telegram and without a router."""
from fractions import Fraction
import html
import math
import re

from .car import number_text

__all__ = ["GAUGES", "gauge_mark", "no_station_text", "no_stop_text", "parse_range", "station_list",
           "station_paragraph", "station_rows"]

# The keyboards of the three gauges, by their steps. Each button is
# `(label, step)`, from full to empty. A row repeats the label that ends the
# row before it, with the same step.
GAUGES = {
    24: (
        (("1", 24), (".", 23), (".", 22), ("|", 21), (".", 20), (".", 19), ("3/4", 18)),
        (("3/4", 18), (".", 17), (".", 16), ("|", 15), (".", 14), (".", 13), ("1/2", 12)),
        (("1/2", 12), (".", 11), (".", 10), ("|", 9), (".", 8), (".", 7), ("1/4", 6)),
        (("1/4", 6), (".", 5), (".", 4), ("|", 3), (".", 2), (".", 1), ("0", 0)),
    ),
    16: (
        (("1", 16), (".", 15), ("|", 14), (",", 13), ("3/4", 12)),
        (("3/4", 12), (".", 11), ("|", 10), (",", 9), ("1/2", 8)),
        (("1/2", 8), (".", 7), ("|", 6), (",", 5), ("1/4", 4)),
        (("1/4", 4), (".", 3), ("|", 2), (",", 1), ("0", 0)),
    ),
    12: (
        (("1", 12), (".", 11), ("5/6", 10), (".", 9), ("2/3", 8), (".", 7), ("1/2", 6)),
        (("1/2", 6), (".", 5), ("1/3", 4), (".", 3), ("1/6", 2), (".", 1), ("0", 0)),
    ),
}


def gauge_mark(step, steps):
    for row in GAUGES[steps]:
        for label, value in row:
            if value == step and label not in (".", ",", "|"):
                return label
    return str(Fraction(step, steps))


def parse_range(text):
    match = re.fullmatch(r"\s*(\d+)(?:[.,](\d+))?\s*", text)
    if match is None:
        return None

    range_km = float(".".join(filter(None, match.groups())))
    if range_km > 3000:
        return None

    return range_km


def no_stop_text(answer):
    if "range_left" in answer:
        return f"No need to refuel: you'll arrive with {math.floor(answer['range_left'])} km of range."
    return f"No need to refuel: you'll arrive with {math.floor(answer['fuel_left'])} L."


def no_station_text(parameters):
    return ("No gas station sells this fuel within 50 km of the point where the range left reaches "
            f"{number_text(parameters.reserve_km)} km.")


def station_list(stations):
    """The stations of a plan answer, as one HTML message."""
    return "\n\n".join(station_paragraph(number, station) for number, station in enumerate(stations, start=1))


def station_rows(count):
    """The labels of the number buttons for `count` stations, in rows of five."""
    numbers = [str(number) for number in range(1, count + 1)]
    return [numbers[first:first + 5] for first in range(0, count, 5)]


def station_paragraph(number, station):
    """The two lines of the station listed as `number`, in HTML."""
    name = html.escape((station["name"] or "").strip() or "Unnamed station")
    title = f'{number}. <a href="{html.escape(station["google_url"])}">{name}</a>'
    if station["badge"]:
        title += f" <b>{html.escape(station['badge'])}</b>"
    first = f"{title} · {round(station['distance_from_previous'] / 1000)} km"

    second = f"{station['price']:.3f} €/L · {_minutes(station['detour_duration'])}"
    if round(station["toll_difference"], 2) != 0:
        second += f" · {_signed(station['toll_difference'])} €"
    return f"{first}\n{second}"


def _minutes(seconds):
    minutes = round(seconds / 60)
    if minutes >= 0:
        return f"+{minutes} min"
    return f"{minutes} min"


def _signed(amount):
    if amount > 0:
        return f"+{amount:.2f}"
    return f"-{abs(amount):.2f}"
