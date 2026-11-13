# -*- coding=utf-8 -*-
import argparse
import asyncio
import datetime
import json
import logging
import re
import sys
import unicodedata

import aiohttp
from bs4 import BeautifulSoup
import isodate
from pyproj import Geod
import shapely
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from . import car, db
from .config import config
from .models import GasStation, GasStationArea

__all__ = ["ParseError", "main", "osm_position", "parse_station_page", "stations_in_area", "update",
           "valid_station_count"]

logger = logging.getLogger(__name__)

GEOD = Geod(ellps="WGS84")


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


async def valid_station_count(session):
    diesel = set(car.station_fuels("diesel"))
    petrol = set(car.station_fuels("95"))
    count = 0
    for prices in await session.scalars(select(GasStation.prices)):
        fuels = {fuel for fuel, _date, _price in prices}
        if fuels & diesel and fuels & petrol:
            count += 1
    return count


def osm_position(candidates, brand, listed):
    near = []
    for candidate in candidates:
        position = _osm_point(candidate)
        if _distance_m(listed, position) <= 20000:
            near.append((position, candidate["tags"]))

    if len(near) > 1:
        near = _with_brand(near, brand)
    if not near:
        return None

    return min(near, key=lambda item: _distance_m(listed, item[0]))[0]


def _osm_point(candidate):
    if "area" in candidate:
        centroid = shapely.Polygon([(longitude, latitude) for latitude, longitude in candidate["area"]]).centroid
        return (centroid.y, centroid.x)

    return (candidate["latitude"], candidate["longitude"])


def _distance_m(a, b):
    return GEOD.inv(a[1], a[0], b[1], b[0])[2]


def _with_brand(near, brand):
    words = _folded(brand or "").split()
    if not words:
        return near

    branded = [
        (position, tags)
        for position, tags in near
        if words[0] in _folded(" | ".join(tags.get(key, "") for key in ("brand", "name", "operator")))
    ]
    return branded or near


def _folded(text):
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(character for character in decomposed if not unicodedata.combining(character)).lower()


async def update(max_age, base_url="https://www.prix-carburants.gouv.fr", osm_path="/cache/osm_gas_stations.json"):
    cutoff = _utcnow() - max_age

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
        try:
            positions = await _listed_positions(http, base_url)
        except (aiohttp.ClientError, asyncio.TimeoutError, ParseError) as error:
            logger.error("Cannot read the open station list: %s", error)
            return 1

        osm_stations = _osm_stations(osm_path)

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
            _refresh(http, requests, base_url, station_id, positions[station_id],
                     osm_stations.get(str(station_id), []))
            for station_id in selected
        ])

    failed = refreshed.count("failed")
    read = [result for result in refreshed if result != "failed"]
    async with db.Session() as session:
        before = await valid_station_count(session)
        if read:
            upsert = insert(GasStation)
            upsert = upsert.on_conflict_do_update(
                index_elements=[GasStation.id],
                set_={column.name: upsert.excluded[column.name]
                      for column in GasStation.__table__.columns if not column.primary_key})
            await session.execute(upsert, [row for _source, row in read])
        after = await valid_station_count(session)
        if before > 0 and after * 5 <= before * 4:
            await session.rollback()
            logger.error("The update is refused: %d valid stations after it, %d before it", after, before)
            return 1
        await session.commit()

    sources = [source for source, _row in read]
    logger.info("%d stations refreshed (%d at the OpenStreetMap position, %d at the list position), %d failed",
                len(read), sources.count("osm"), sources.count("list"), failed)
    if failed:
        return 1

    return 0


def _osm_stations(path):
    try:
        with open(path, encoding="utf-8") as file:
            stations = json.load(file)
    except (OSError, ValueError) as error:
        logger.warning("The OpenStreetMap stations are not used: %s", error)
        return {}

    if not isinstance(stations, dict):
        logger.warning("The OpenStreetMap stations are not used: %s is not a JSON object", path)
        return {}

    return stations


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


async def _refresh(http, requests, base_url, station_id, listed, candidates):
    async with requests:
        try:
            async with http.get(f"{base_url}/station/{station_id}") as reply:
                reply.raise_for_status()
                html = await reply.text()
            read_at = _utcnow()
            fields = parse_station_page(html)
        except (aiohttp.ClientError, asyncio.TimeoutError, ParseError) as error:
            logger.error("Station %d failed: %s", station_id, error)
            return "failed"

        position = osm_position(candidates, fields["name"], listed)
        source = "osm"
        if position is None:
            position = listed
            source = "list"

    latitude, longitude = position
    logger.debug("Station %d read", station_id)
    return source, {"id": station_id, "latitude": latitude, "longitude": longitude, "last_updated_at": read_at,
                    **fields}


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
