# -*- coding=utf-8 -*-
"""The gas station inventory: the schema, the page parser, the area query, and the run.

The store is a real SQLite file in a temporary directory, migrated by Alembic,
as in `test_spending.py`. The triggers and the R*Tree index exist only in the
revision, so a schema built from the models would test neither.

The source is a local aiohttp server. No test reaches prix-carburants.gouv.fr.
"""
import asyncio
import datetime
import json
import pathlib
import sqlite3

from aiohttp import web
from aiohttp.test_utils import TestServer
from alembic import command
from alembic.config import Config
import isodate
import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .. import db, gas_stations

def alembic_config(db_path):
    cfg = Config(__file__.rsplit("/", 3)[0] + "/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


@pytest.fixture
def store(tmp_path, monkeypatch):
    db_path = tmp_path / "database.db"
    command.upgrade(alembic_config(db_path), "head")

    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setattr(db, "Session", async_sessionmaker(engine, expire_on_commit=False))
    yield db_path
    asyncio.run(engine.dispose())


def insert_station(db_path, station_id, latitude, longitude, name="Old", last_updated_at="2026-11-01 10:00:00"):
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO gas_station"
            " (id, latitude, longitude, name, address, services, prices, last_updated_at)"
            " VALUES (?, ?, ?, ?, '[]', '[]', '[]', ?)",
            (station_id, latitude, longitude, name, last_updated_at),
        )


def index_entries(db_path, station_id):
    with sqlite3.connect(db_path) as connection:
        return connection.execute(
            "SELECT min_latitude, max_latitude, min_longitude, max_longitude"
            " FROM gas_station_area WHERE id = ?",
            (station_id,),
        ).fetchall()


def indexed_ids_in_box(db_path, south, west, north, east):
    with sqlite3.connect(db_path) as connection:
        return [
            station_id
            for (station_id,) in connection.execute(
                "SELECT id FROM gas_station_area"
                " WHERE max_latitude >= ? AND min_latitude <= ?"
                " AND max_longitude >= ? AND min_longitude <= ?",
                (south, north, west, east),
            )
        ]


def test_the_models_and_the_revisions_agree(store):
    command.check(alembic_config(store))


def test_the_store_holds_three_tables_and_the_index(store):
    with sqlite3.connect(store) as connection:
        names = {name for (name,) in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert names == {
        "alembic_version",
        "autocomplete",
        "google_requests",
        "gas_station",
        "gas_station_area",
        "gas_station_area_node",
        "gas_station_area_parent",
        "gas_station_area_rowid",
    }


# The triggers keep the index equal to the table, whatever code writes the table.
# These tests write with plain sqlite3 on purpose.


def test_an_inserted_station_is_indexed_at_its_position(store):
    insert_station(store, 29520005, 48.209, -3.818)

    [(min_latitude, max_latitude, min_longitude, max_longitude)] = index_entries(store, 29520005)
    assert min_latitude == pytest.approx(48.209, abs=1e-5)
    assert max_latitude == pytest.approx(48.209, abs=1e-5)
    assert min_longitude == pytest.approx(-3.818, abs=1e-5)
    assert max_longitude == pytest.approx(-3.818, abs=1e-5)


def test_a_moved_station_is_indexed_at_its_new_position(store):
    insert_station(store, 29520005, 48.209, -3.818)

    with sqlite3.connect(store) as connection:
        connection.execute("UPDATE gas_station SET latitude = 44.928, longitude = 2.443 WHERE id = 29520005")

    [(min_latitude, _, min_longitude, _)] = index_entries(store, 29520005)
    assert min_latitude == pytest.approx(44.928, abs=1e-5)
    assert min_longitude == pytest.approx(2.443, abs=1e-5)
    assert indexed_ids_in_box(store, 48.1, -3.9, 48.3, -3.7) == []
    assert indexed_ids_in_box(store, 44.8, 2.3, 45.0, 2.5) == [29520005]


def test_a_renumbered_station_is_indexed_under_its_new_id(store):
    insert_station(store, 29520005, 48.209, -3.818)

    with sqlite3.connect(store) as connection:
        connection.execute("UPDATE gas_station SET id = 29520006 WHERE id = 29520005")

    assert index_entries(store, 29520005) == []
    assert len(index_entries(store, 29520006)) == 1


def test_a_deleted_station_leaves_the_index(store):
    insert_station(store, 29520005, 48.209, -3.818)

    with sqlite3.connect(store) as connection:
        connection.execute("DELETE FROM gas_station WHERE id = 29520005")

    assert index_entries(store, 29520005) == []


@pytest.fixture
def station_page():
    return (pathlib.Path(__file__).parent / "station_29520005.html").read_text(encoding="utf-8")


def page(block="<strong>Marque :</strong> Leclerc<br/>Rue de quimper", rows="", services=""):
    return (
        f'<table class="details_pdv"><tbody>{rows}</tbody></table>'
        f'<div><p class="fr-h3">Coordonnées station</p><div class="fr-pb-3v">{block}</div></div>'
        f'<div><p class="fr-h3">Services</p><div>{services}</div></div>'
    )


def test_the_saved_page_is_parsed(station_page):
    assert gas_stations.parse_station_page(station_page) == {
        "name": "Leclerc",
        "address": ["Rue de quimper", "29520 Chateauneuf du faou"],
        "services": ["Lavage automatique"],
        "prices": [
            ["SP95-E10 (E10)", "2026-11-06", "1.999"],
            ["E85 (E85)", "2026-10-26", "0.877"],
            ["Gazole (B7)", "2026-11-06", "2.149"],
        ],
    }


def test_an_independent_station_keeps_the_text_of_the_page():
    parsed = gas_stations.parse_station_page(page(block="<strong>Marque :</strong> Indépendant sans enseigne"))

    assert parsed["name"] == "Indépendant sans enseigne"
    assert parsed["address"] == []


def test_a_block_without_a_brand_line_is_all_address():
    parsed = gas_stations.parse_station_page(page(block="Rue de quimper<br/>\n  29520\n  Chateauneuf du faou\n"))

    assert parsed["name"] is None
    assert parsed["address"] == ["Rue de quimper", "29520 Chateauneuf du faou"]


def test_an_empty_services_section_gives_an_empty_list():
    assert gas_stations.parse_station_page(page())["services"] == []


def test_the_price_text_is_kept_exactly():
    rows = (
        '<tr><td><strong>SP95 (E5)</strong><br><span class="date">05/11/26</span></td>'
        '<td class="prix"><strong>2.100</strong></td></tr>'
    )

    assert gas_stations.parse_station_page(page(rows=rows))["prices"] == [["SP95 (E5)", "2026-11-05", "2.100"]]


def test_a_fuel_without_a_price_is_not_stored():
    rows = '<tr><td><strong>SP98 (E5)</strong><br>&nbsp;</td><td class="prix"></td></tr>'

    assert gas_stations.parse_station_page(page(rows=rows))["prices"] == []


def test_a_page_without_the_price_table_is_refused():
    with pytest.raises(gas_stations.ParseError, match="no price table"):
        gas_stations.parse_station_page(page().replace('class="details_pdv"', ""))


def test_a_page_without_the_station_block_is_refused():
    with pytest.raises(gas_stations.ParseError, match="no station block"):
        gas_stations.parse_station_page(page().replace("Coordonnées station", "Horaires"))


def test_a_price_without_a_date_is_refused():
    rows = '<tr><td><strong>SP98 (E5)</strong><br>&nbsp;</td><td class="prix"><strong>2.100</strong></td></tr>'

    with pytest.raises(gas_stations.ParseError, match="SP98 \\(E5\\) has a price and no date"):
        gas_stations.parse_station_page(page(rows=rows))


def area_ids(south, west, north, east):
    return sorted(station.id for station in asyncio.run(gas_stations.stations_in_area(south, west, north, east)))


def test_the_area_holds_only_the_stations_in_the_box(store):
    insert_station(store, 29520005, 48.209, -3.818)
    insert_station(store, 15000012, 44.928, 2.443)

    assert area_ids(47.0, -5.0, 49.0, -1.0) == [29520005]


def test_a_station_on_the_edge_is_in_the_area(store):
    insert_station(store, 1, 48.0, -3.0)

    assert area_ids(48.0, -4.0, 49.0, -3.0) == [1]


def test_a_station_just_outside_the_box_is_not_in_the_area(store):
    insert_station(store, 1, 48.0000001, -3.5)

    assert area_ids(47.0, -4.0, 48.0, -3.0) == []


def test_the_area_query_reads_the_index(store):
    statements = []
    engine = db.Session.kw["bind"].sync_engine
    event.listen(engine, "before_cursor_execute",
                 lambda _connection, _cursor, statement, parameters, *_: statements.append((statement, parameters)))

    asyncio.run(gas_stations.stations_in_area(47.0, -5.0, 49.0, -1.0))

    [(statement, parameters)] = statements
    with sqlite3.connect(store) as connection:
        plan = [detail for (*_, detail) in connection.execute("EXPLAIN QUERY PLAN " + statement, parameters)]
    assert any(detail.startswith("SCAN gas_station_area VIRTUAL TABLE INDEX") for detail in plan)
    assert "SEARCH gas_station USING INTEGER PRIMARY KEY (rowid=?)" in plan


class LocalSource:
    def __init__(self, listed, pages, list_status=200, list_body=None, hold=(), delay=0):
        self.listed = listed
        self.pages = pages
        self.list_status = list_status
        self.list_body = list_body
        self.hold = hold
        self.delay = delay
        self.requested = []
        self.open = 0
        self.most_open = 0

    async def station_list(self, _request):
        body = self.list_body
        if body is None:
            body = json.dumps([
                {"id": station_id, "coordLatitude": str(latitude), "coordLongitude": str(longitude),
                 "deptCode": "29", "regionCode": "6", "zipCode": "29520"}
                for station_id, latitude, longitude in self.listed
            ])
        return web.Response(status=self.list_status, text=body, content_type="application/json")

    async def station(self, request):
        station_id = int(request.match_info["station_id"])
        self.requested.append(station_id)
        self.open += 1
        self.most_open = max(self.most_open, self.open)
        try:
            if station_id in self.hold:
                await self.released.wait()
            await asyncio.sleep(self.delay)
        finally:
            self.open -= 1

        if station_id not in self.pages:
            return web.Response(status=404)
        return web.Response(text=self.pages[station_id], content_type="text/html")

    async def update(self, max_age):
        self.released = asyncio.Event()
        app = web.Application()
        app.router.add_get("/map/recupererOpenPdvs/", self.station_list)
        app.router.add_get("/station/{station_id}", self.station)
        server = TestServer(app)
        await server.start_server()
        try:
            return await gas_stations.update(max_age, base_url=f"http://{server.host}:{server.port}")
        finally:
            # A held handler would otherwise keep the server open until its shutdown timeout.
            self.released.set()
            await server.close()

    def run(self, max_age="PT23H"):
        return asyncio.run(self.update(isodate.parse_duration(max_age)))


def stored_row(db_path, station_id):
    with sqlite3.connect(db_path) as connection:
        return connection.execute("SELECT * FROM gas_station WHERE id = ?", (station_id,)).fetchone()


def stored_ids(db_path):
    with sqlite3.connect(db_path) as connection:
        return [station_id for (station_id,) in connection.execute("SELECT id FROM gas_station ORDER BY id")]


def hours_ago(hours):
    return str(datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(hours=hours))


@pytest.mark.parametrize("list_status, list_body", [
    (503, "[]"),
    (200, "not json"),
    (200, '{"id": 1, "coordLatitude": "48.209", "coordLongitude": "-3.818"}'),
    (200, '[{"id": "1", "coordLatitude": "48.209", "coordLongitude": "-3.818"}]'),
    (200, '[{"id": 1}]'),
])
def test_a_list_that_cannot_be_read_changes_nothing(store, station_page, list_status, list_body):
    insert_station(store, 1, 44.0, 2.0, last_updated_at=hours_ago(30))
    before = stored_row(store, 1)
    source = LocalSource([], {1: station_page}, list_status=list_status, list_body=list_body)

    assert source.run() == 1
    assert source.requested == []
    assert stored_row(store, 1) == before


def test_a_new_station_is_stored_under_its_listed_id(store, station_page):
    source = LocalSource([(29520005, 48.209, -3.818)], {29520005: station_page})

    assert source.run() == 0
    assert source.requested == [29520005]
    station_id, latitude, longitude, name, address, services, prices, _ = stored_row(store, 29520005)
    assert (station_id, latitude, longitude, name) == (29520005, 48.209, -3.818, "Leclerc")
    assert json.loads(address) == ["Rue de quimper", "29520 Chateauneuf du faou"]
    assert json.loads(services) == ["Lavage automatique"]
    assert json.loads(prices)[0] == ["SP95-E10 (E10)", "2026-11-06", "1.999"]


def test_a_fresh_station_is_skipped(store, station_page):
    insert_station(store, 1, 48.209, -3.818, last_updated_at=hours_ago(2))
    before = stored_row(store, 1)
    source = LocalSource([(1, 48.209, -3.818)], {1: station_page})

    assert source.run() == 0
    assert source.requested == []
    assert stored_row(store, 1) == before


def test_a_stale_station_is_refreshed(store, station_page):
    insert_station(store, 1, 48.209, -3.818, last_updated_at=hours_ago(30))
    source = LocalSource([(1, 48.209, -3.818)], {1: station_page})

    assert source.run() == 0
    assert source.requested == [1]
    assert stored_row(store, 1)[3] == "Leclerc"


def test_a_zero_age_refreshes_every_listed_station(store, station_page):
    insert_station(store, 1, 48.209, -3.818, last_updated_at=hours_ago(0.01))
    source = LocalSource([(1, 48.209, -3.818), (2, 48.0, -3.0)], {1: station_page, 2: station_page})

    assert source.run("PT0S") == 0
    assert sorted(source.requested) == [1, 2]


def test_a_station_that_left_the_list_stays_stored(store, station_page):
    insert_station(store, 3, 44.0, 2.0, last_updated_at=hours_ago(30))
    before = stored_row(store, 3)
    source = LocalSource([(1, 48.209, -3.818)], {1: station_page})

    assert source.run() == 0
    assert stored_row(store, 3) == before


def test_the_listed_position_replaces_the_stored_one(store, station_page):
    insert_station(store, 1, 44.0, 2.0, last_updated_at=hours_ago(30))
    source = LocalSource([(1, 48.209, -3.818)], {1: station_page})

    assert source.run() == 0
    assert stored_row(store, 1)[1:3] == (48.209, -3.818)
    assert area_ids(48.1, -3.9, 48.3, -3.7) == [1]


def test_the_update_time_is_the_time_of_the_read(store, station_page):
    source = LocalSource([(1, 48.209, -3.818)], {1: station_page})

    started = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    assert source.run() == 0
    ended = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    assert started <= datetime.datetime.fromisoformat(stored_row(store, 1)[7]) <= ended


def test_a_station_that_is_not_found_fails_alone(store, station_page):
    insert_station(store, 2, 44.0, 2.0, last_updated_at=hours_ago(30))
    before = stored_row(store, 2)
    source = LocalSource([(1, 48.209, -3.818), (2, 44.0, 2.0)], {1: station_page})

    assert source.run() == 1
    assert sorted(source.requested) == [1, 2]
    assert stored_row(store, 1)[3] == "Leclerc"
    assert stored_row(store, 2) == before


def test_a_page_with_an_unknown_layout_is_logged_with_its_id(store, caplog, monkeypatch):
    # The fileConfig of alembic/env.py, run by the store fixture, disables each
    # logger that exists at that time. The real command does not migrate.
    monkeypatch.setattr(gas_stations.logger, "disabled", False)
    source = LocalSource([(7, 48.209, -3.818)], {7: "<html><body></body></html>"})

    assert source.run() == 1
    assert stored_ids(store) == []
    assert "Station 7 failed: no price table" in caplog.text


def test_no_more_than_four_page_requests_are_open_at_once(store, station_page):
    listed = [(station_id, 48.209, -3.818) for station_id in range(1, 101)]
    source = LocalSource(listed, {station_id: station_page for station_id in range(1, 101)}, delay=0.01)

    assert source.run() == 0
    assert len(source.requested) == 100
    assert source.most_open == 4


def test_an_interrupted_run_keeps_what_it_stored(store, station_page):
    listed = [(station_id, 48.209, -3.818) for station_id in range(1, 6)]
    pages = {station_id: station_page for station_id in range(1, 6)}
    first = LocalSource(listed, pages, hold={5})
    second = LocalSource(listed, pages)

    async def go():
        run = asyncio.create_task(first.update(isodate.parse_duration("PT23H")))

        async def four_stored():
            while stored_ids(store) != [1, 2, 3, 4]:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(four_stored(), timeout=10)
        run.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run

        return await second.update(isodate.parse_duration("PT23H"))

    assert asyncio.run(go()) == 0
    assert 5 in first.requested
    assert second.requested == [5]


def test_an_age_that_is_not_iso_8601_is_refused(monkeypatch, capsys):
    monkeypatch.setattr(gas_stations, "update", lambda *_: pytest.fail("the run started"))

    with pytest.raises(SystemExit) as stopped:
        gas_stations.main(["23h"])

    assert stopped.value.code == 2
    assert "invalid parse_duration value: '23h'" in capsys.readouterr().err


def test_no_age_shows_the_usage(monkeypatch, capsys):
    monkeypatch.setattr(gas_stations, "update", lambda *_: pytest.fail("the run started"))

    with pytest.raises(SystemExit) as stopped:
        gas_stations.main([])

    assert stopped.value.code == 2
    assert "usage: gas-stations [-h] MAX_AGE" in capsys.readouterr().err


def test_the_command_exits_with_the_status_of_the_run(monkeypatch):
    ages = []

    async def update(max_age):
        ages.append(max_age)
        return 1

    monkeypatch.setattr(gas_stations, "update", update)

    with pytest.raises(SystemExit) as stopped:
        gas_stations.main(["PT23H"])

    assert stopped.value.code == 1
    assert ages == [datetime.timedelta(hours=23)]
