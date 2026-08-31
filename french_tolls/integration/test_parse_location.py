# -*- coding=utf-8 -*-
"""Reading a location a driver typed.

Here rather than in the unit suite because `bot` imports `route`, which loads
the booth artefacts at import — and `route-algorithm-tests` requires that no
unit test import a module that reads an artefact at import time. This suite has
`data/` mounted, so it can.

Nothing here reaches a router or a chat.
"""
import pytest

from ..bot import parse_location


@pytest.mark.parametrize("text,expected", [
    # The defect: everything west of Greenwich. Found driving Ancenis-Saint-Géréon
    # to Ploërmel, where both ends are negative and the bot answered with help.
    ("47.3682464, -1.1844303", (-1.1844303, 47.3682464)),
    ("47.9323786,-2.39808", (-2.39808, 47.9323786)),
    # South of the equator too, though nothing in France is.
    ("-33.8688, 151.2093", (151.2093, -33.8688)),
    ("-12.5, -45.25", (-45.25, -12.5)),
    # Whole degrees, and the spacing a paste produces.
    ("48, 2", (2.0, 48.0)),
    ("43.25 ,  6.53659", (6.53659, 43.25)),
    # Something else in the sentence around it.
    ("I am at 45.764043, 4.835659 right now", (4.835659, 45.764043)),
])
def test_a_typed_location_is_read_as_longitude_and_latitude(text, expected):
    assert parse_location(text) == expected


@pytest.mark.parametrize("text", [
    "hello",
    "",
    "48.8566",             # one number is not a location
    "somewhere, else",
])
def test_text_that_is_not_a_location_is_not_one(text):
    assert parse_location(text) is None


def test_a_run_of_dots_is_not_a_number():
    """`[0-9.]+` matched this and handed `float` something it refuses."""
    assert parse_location("1.2.3, 4.5.6") is None


def test_the_order_is_reversed_on_the_way_out():
    """A person writes latitude first; everything downstream speaks lon, lat."""
    lon, lat = parse_location("47.3682464, -1.1844303")

    assert lat > 0 and lon < 0, "Ancenis is north of the equator and west of Greenwich"
