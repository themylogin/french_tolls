# -*- coding=utf-8 -*-
"""The OSM gas station extract. The tests run the real osmium, and no test reaches Geofabrik."""
import functools
import http.server
import json
import pathlib
import subprocess
import tempfile
import threading

import pytest

from .. import osm_gas_stations


@pytest.fixture
def served(tmp_path):
    directory = tmp_path / "served"
    directory.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    yield directory, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join()
    server.server_close()


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    directory = tmp_path / "scratch"
    directory.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(directory))
    return directory


@pytest.fixture
def cache(tmp_path):
    directory = tmp_path / "cache"
    directory.mkdir()
    return directory


def feature(geometry, properties):
    return json.dumps({"type": "Feature", "geometry": geometry, "properties": properties}) + "\n"


def fixture_pbf(path):
    fixture = pathlib.Path(__file__).with_name("osm_gas_stations.osm")
    subprocess.run(["osmium", "cat", str(fixture), "-o", str(path)], check=True)
    return path


def in_any_order(stations):
    return {ref: sorted(listed, key=json.dumps) for ref, listed in stations.items()}


def test_a_point_gives_its_position_and_tags():
    lines = [feature({"type": "Point", "coordinates": [2.7350978, 47.9120276]},
                     {"amenity": "fuel", "ref:FR:prix-carburants": "45200007"})]

    assert osm_gas_stations.stations_by_ref(lines) == {
        "45200007": [{"latitude": 47.9120276, "longitude": 2.7350978,
                      "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "45200007"}}],
    }


def test_a_multipolygon_gives_one_area_per_outer_ring():
    lines = [feature(
        {"type": "MultiPolygon", "coordinates": [
            [[[5.0, 47.0], [5.1, 47.0], [5.1, 47.1], [5.0, 47.0]]],
            [[[4.0, 43.0], [4.4, 43.0], [4.4, 43.4], [4.0, 43.0]],
             [[4.1, 43.1], [4.2, 43.2], [4.2, 43.1], [4.1, 43.1]]],
        ]},
        {"amenity": "fuel", "ref:FR:prix-carburants": "21490003"},
    )]

    assert osm_gas_stations.stations_by_ref(lines) == {
        "21490003": [
            {"area": [[47.0, 5.0], [47.0, 5.1], [47.1, 5.1]],
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "21490003"}},
            {"area": [[43.0, 4.0], [43.0, 4.4], [43.4, 4.4]],
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "21490003"}},
        ],
    }


def test_a_line_string_is_skipped():
    lines = [feature({"type": "LineString", "coordinates": [[1.0, 46.0], [1.1, 46.0], [1.1, 46.1]]},
                     {"amenity": "fuel", "ref:FR:prix-carburants": "45200010"})]

    assert osm_gas_stations.stations_by_ref(lines) == {}


def test_a_feature_without_fuel_or_without_id_is_skipped():
    lines = [
        feature({"type": "Point", "coordinates": [2.6, 47.6]},
                {"amenity": "charging_station", "ref:FR:prix-carburants": "45200007"}),
        feature({"type": "Point", "coordinates": [2.5, 47.5]},
                {"amenity": "fuel", "name": "Sans id"}),
    ]

    assert osm_gas_stations.stations_by_ref(lines) == {}


def test_a_station_with_two_ids_is_listed_under_each():
    lines = [feature({"type": "Point", "coordinates": [2.1, 48.1]},
                     {"amenity": "fuel", "ref:FR:prix-carburants": "45200008; 45200009"})]

    station = {"latitude": 48.1, "longitude": 2.1,
               "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "45200008; 45200009"}}
    assert osm_gas_stations.stations_by_ref(lines) == {"45200008": [station], "45200009": [station]}


def test_stations_with_the_same_id_share_one_key():
    lines = [
        feature({"type": "Point", "coordinates": [-0.45, 44.95]},
                {"amenity": "fuel", "ref:FR:prix-carburants": "33560002"}),
        feature({"type": "MultiPolygon", "coordinates": [[[[-0.5, 44.9], [-0.4, 44.9], [-0.4, 45.0], [-0.5, 44.9]]]]},
                {"amenity": "fuel", "ref:FR:prix-carburants": "33560002"}),
    ]

    assert osm_gas_stations.stations_by_ref(lines) == {
        "33560002": [
            {"latitude": 44.95, "longitude": -0.45,
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "33560002"}},
            {"area": [[44.9, -0.5], [44.9, -0.4], [45.0, -0.4]],
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "33560002"}},
        ],
    }


def test_every_tag_is_kept_unchanged():
    tags = {"amenity": "fuel", "brand": "Total Access", "hgv": "only", "name": "Relais  Beaune (PL)",
            "ref:FR:prix-carburants": "45200007"}
    lines = [feature({"type": "Point", "coordinates": [2.7350978, 47.9120276]}, tags)]

    assert osm_gas_stations.stations_by_ref(lines)["45200007"][0]["tags"] == {
        "amenity": "fuel", "brand": "Total Access", "hgv": "only", "name": "Relais  Beaune (PL)",
        "ref:FR:prix-carburants": "45200007",
    }


def test_a_line_with_a_record_separator_is_read():
    lines = ["\x1e" + feature({"type": "Point", "coordinates": [2.7350978, 47.9120276]},
                              {"amenity": "fuel", "ref:FR:prix-carburants": "45200007"})]

    assert list(osm_gas_stations.stations_by_ref(lines)) == ["45200007"]


def test_the_fixture_extract_gives_every_case_of_the_spec(tmp_path):
    stations = osm_gas_stations.extract_stations(fixture_pbf(tmp_path / "extract.osm.pbf"))

    assert in_any_order(stations) == in_any_order({
        "45200007": [
            {"latitude": 47.9120276, "longitude": 2.7350978,
             "tags": {"amenity": "fuel", "brand": "Total Access", "hgv": "only",
                      "ref:FR:prix-carburants": "45200007"}},
        ],
        "45200008": [
            {"latitude": 48.1, "longitude": 2.1,
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "45200008; 45200009"}},
        ],
        "45200009": [
            {"latitude": 48.1, "longitude": 2.1,
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "45200008; 45200009"}},
        ],
        "33560002": [
            {"latitude": 44.95, "longitude": -0.45,
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "33560002"}},
            {"area": [[44.9, -0.5], [44.9, -0.4], [45.0, -0.4]],
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "33560002"}},
        ],
        "21490003": [
            {"area": [[47.0, 5.0], [47.0, 5.1], [47.1, 5.1]],
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "21490003"}},
            {"area": [[47.0, 5.2], [47.0, 5.3], [47.1, 5.3]],
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "21490003"}},
        ],
        "13200006": [
            {"area": [[43.0, 4.0], [43.0, 4.4], [43.4, 4.4], [43.4, 4.0]],
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "13200006"}},
        ],
    })


def test_a_run_writes_the_stations_of_the_downloaded_extract(served, scratch, cache):
    directory, base_url = served
    fixture_pbf(directory / "france-latest.osm.pbf")

    status = osm_gas_stations.run(f"{base_url}/france-latest.osm.pbf", cache / "osm_gas_stations.json")

    assert status == 0
    written = json.loads((cache / "osm_gas_stations.json").read_text(encoding="utf-8"))
    assert in_any_order(written) == in_any_order({
        "45200007": [
            {"latitude": 47.9120276, "longitude": 2.7350978,
             "tags": {"amenity": "fuel", "brand": "Total Access", "hgv": "only",
                      "ref:FR:prix-carburants": "45200007"}},
        ],
        "45200008": [
            {"latitude": 48.1, "longitude": 2.1,
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "45200008; 45200009"}},
        ],
        "45200009": [
            {"latitude": 48.1, "longitude": 2.1,
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "45200008; 45200009"}},
        ],
        "33560002": [
            {"latitude": 44.95, "longitude": -0.45,
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "33560002"}},
            {"area": [[44.9, -0.5], [44.9, -0.4], [45.0, -0.4]],
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "33560002"}},
        ],
        "21490003": [
            {"area": [[47.0, 5.0], [47.0, 5.1], [47.1, 5.1]],
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "21490003"}},
            {"area": [[47.0, 5.2], [47.0, 5.3], [47.1, 5.3]],
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "21490003"}},
        ],
        "13200006": [
            {"area": [[43.0, 4.0], [43.0, 4.4], [43.4, 4.4], [43.4, 4.0]],
             "tags": {"amenity": "fuel", "ref:FR:prix-carburants": "13200006"}},
        ],
    })
    assert [path.name for path in cache.iterdir()] == ["osm_gas_stations.json"]
    assert list(scratch.iterdir()) == []


def test_a_failed_download_keeps_the_earlier_file(served, scratch, cache):
    _, base_url = served
    (cache / "osm_gas_stations.json").write_bytes(b'{"45200007": []}')

    status = osm_gas_stations.run(f"{base_url}/france-latest.osm.pbf", cache / "osm_gas_stations.json")

    assert status == 1
    assert (cache / "osm_gas_stations.json").read_bytes() == b'{"45200007": []}'
    assert [path.name for path in cache.iterdir()] == ["osm_gas_stations.json"]


def test_a_failed_extraction_keeps_the_earlier_file_and_deletes_the_download(served, scratch, cache):
    directory, base_url = served
    (directory / "france-latest.osm.pbf").write_bytes(b"not a pbf")
    (cache / "osm_gas_stations.json").write_bytes(b'{"45200007": []}')

    status = osm_gas_stations.run(f"{base_url}/france-latest.osm.pbf", cache / "osm_gas_stations.json")

    assert status == 1
    assert (cache / "osm_gas_stations.json").read_bytes() == b'{"45200007": []}'
    assert [path.name for path in cache.iterdir()] == ["osm_gas_stations.json"]
    assert list(scratch.iterdir()) == []


def test_main_runs_on_the_geofabrik_extract_and_writes_to_the_cache(monkeypatch):
    calls = []

    def fake_run(url, output_path):
        calls.append((url, output_path))
        return 1

    monkeypatch.setattr(osm_gas_stations, "run", fake_run)

    with pytest.raises(SystemExit) as exit_info:
        osm_gas_stations.main()

    assert exit_info.value.code == 1
    assert calls == [("https://download.geofabrik.de/europe/france-latest.osm.pbf", "/cache/osm_gas_stations.json")]
