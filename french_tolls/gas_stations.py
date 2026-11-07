# -*- coding=utf-8 -*-
import argparse
import asyncio
import datetime
import json
import logging
import re
import sys

import aiohttp
from bs4 import BeautifulSoup
import isodate
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from . import db
from .config import config
from .models import GasStation, GasStationArea

__all__ = ["ParseError", "main", "parse_station_page", "stations_in_area", "update"]

logger = logging.getLogger(__name__)


class ParseError(Exception):
    pass


def parse_station_page(html):
    page = BeautifulSoup(html, "html.parser")

    price_table = page.select_one("table.details_pdv")
    if price_table is None:
        raise ParseError("no price table")

    station_heading = page.find("p", string=re.compile(r"^\s*Coordonnées station\s*$"))
    if station_heading is None:
        raise ParseError("no station block")
    station_block = station_heading.find_next_sibling("div", class_="fr-pb-3v")
    if station_block is None:
        raise ParseError("no station block")

    lines = _lines(station_block)
    name = None
    if lines:
        brand = re.fullmatch(r"Marque\s*:\s*(.*)", lines[0])
        if brand is not None:
            name = brand.group(1)
            lines = lines[1:]

    return {
        "name": name,
        "address": lines,
        "services": _services(page),
        "prices": _prices(price_table),
    }


def _lines(block):
    parts = [[]]
    for node in block.children:
        if node.name == "br":
            parts.append([])
        else:
            parts[-1].append(node.get_text())

    lines = [" ".join("".join(part).split()) for part in parts]
    return [line for line in lines if line]


def _services(page):
    heading = page.find("p", string=re.compile(r"^\s*Services\s*$"))
    if heading is None:
        return []

    return [" ".join(name.get_text().split()) for name in heading.parent.select("div.fr-pl-1w")]


def _prices(price_table):
    prices = []
    for row in price_table.select("tbody tr"):
        fuel = row.select_one("td strong")
        if fuel is None:
            raise ParseError("a price row has no fuel")
        fuel = " ".join(fuel.get_text().split())

        price = row.select_one("td.prix strong")
        if price is None:
            continue

        date = row.select_one("span.date")
        if date is None:
            raise ParseError(f"{fuel} has a price and no date")
        try:
            day = datetime.datetime.strptime(date.get_text(strip=True), "%d/%m/%y").date()
        except ValueError:
            raise ParseError(f"{fuel} has the date {date.get_text(strip=True)!r}") from None

        prices.append([fuel, day.isoformat(), price.get_text(strip=True)])

    return prices


async def stations_in_area(south, west, north, east):
    # The R*Tree keeps 32-bit floats and rounds each box outwards, so it can
    # match a station just outside the area. The index selects the candidates,
    # and the exact position in gas_station decides.
    query = (
        select(GasStation)
        .join(GasStationArea, GasStationArea.id == GasStation.id)
        .where(
            GasStationArea.max_latitude >= south,
            GasStationArea.min_latitude <= north,
            GasStationArea.max_longitude >= west,
            GasStationArea.min_longitude <= east,
            GasStation.latitude.between(south, north),
            GasStation.longitude.between(west, east),
        )
    )

    async with db.Session() as session:
        return list(await session.scalars(query))


async def update(max_age, base_url="https://www.prix-carburants.gouv.fr"):
    cutoff = _utcnow() - max_age

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
        try:
            positions = await _listed_positions(http, base_url)
        except (aiohttp.ClientError, asyncio.TimeoutError, ParseError) as error:
            logger.error("Cannot read the open station list: %s", error)
            return 1

        async with db.Session() as session:
            stored = dict((await session.execute(select(GasStation.id, GasStation.last_updated_at))).all())

        selected = [
            station_id
            for station_id in positions
            if station_id not in stored or stored[station_id] < cutoff
        ]
        logger.info("%d stations listed, %d selected", len(positions), len(selected))

        requests = asyncio.Semaphore(4)
        refreshed = await asyncio.gather(*[
            _refresh(http, requests, base_url, station_id, positions[station_id])
            for station_id in selected
        ])

    failed = refreshed.count(False)
    logger.info("%d stations refreshed, %d failed", len(selected) - failed, failed)
    if failed:
        return 1

    return 0


async def _listed_positions(http, base_url):
    async with http.get(f"{base_url}/map/recupererOpenPdvs/") as reply:
        reply.raise_for_status()
        body = await reply.text()

    try:
        entries = json.loads(body)
        if not isinstance(entries, list):
            raise ParseError("the list is not a JSON list")

        positions = {}
        for entry in entries:
            if not isinstance(entry["id"], int):
                raise ParseError(f"the id {entry['id']!r} is not an integer")
            positions[entry["id"]] = (float(entry["coordLatitude"]), float(entry["coordLongitude"]))
    except (KeyError, TypeError, ValueError) as error:
        raise ParseError(f"the list has an entry without an id and a position: {error!r}") from None

    return positions


async def _refresh(http, requests, base_url, station_id, position):
    async with requests:
        try:
            async with http.get(f"{base_url}/station/{station_id}") as reply:
                reply.raise_for_status()
                html = await reply.text()
            read_at = _utcnow()
            fields = parse_station_page(html)
        except (aiohttp.ClientError, asyncio.TimeoutError, ParseError) as error:
            logger.error("Station %d failed: %s", station_id, error)
            return False

        latitude, longitude = position
        values = {"latitude": latitude, "longitude": longitude, "last_updated_at": read_at, **fields}
        async with db.Session() as session:
            await session.execute(
                insert(GasStation)
                .values(id=station_id, **values)
                .on_conflict_do_update(index_elements=[GasStation.id], set_=values))
            await session.commit()

    logger.debug("Station %d refreshed", station_id)
    return True


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="gas-stations",
        description="Refresh each listed gas station whose stored row is older than MAX_AGE.",
    )
    parser.add_argument("max_age", metavar="MAX_AGE", type=isodate.parse_duration,
                        help="an ISO 8601 duration, for example PT23H")
    arguments = parser.parse_args(argv)

    logging.basicConfig(
        level=config.log_level,
        format="[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s",
    )

    sys.exit(asyncio.run(update(arguments.max_age)))


if __name__ == "__main__":
    main()
