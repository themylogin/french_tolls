# -*- coding=utf-8 -*-
import json
import logging
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request

from .config import config

__all__ = ["extract_stations", "main", "run", "stations_by_ref"]

logger = logging.getLogger(__name__)


def run(url, output_path):
    output_path = pathlib.Path(output_path)
    try:
        with tempfile.TemporaryDirectory() as scratch:
            pbf_path = pathlib.Path(scratch) / "france-latest.osm.pbf"
            _download(url, pbf_path)
            stations = extract_stations(pbf_path)
        _write(stations, output_path)
    except (OSError, subprocess.CalledProcessError) as error:
        logger.error("The run failed: %s", error)
        return 1

    listed = [station for stations_of_ref in stations.values() for station in stations_of_ref]
    areas = sum(1 for station in listed if "area" in station)
    logger.info("%d ids, %d nodes, %d areas written to %s",
                len(stations), len(listed) - areas, areas, output_path)
    return 0


def _download(url, path):
    logger.info("Downloading %s", url)
    with urllib.request.urlopen(url, timeout=60) as response, open(path, "wb") as file:
        shutil.copyfileobj(response, file)


def _write(stations, output_path):
    file = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=output_path.parent, suffix=".tmp", delete=False)
    try:
        with file:
            json.dump(stations, file, ensure_ascii=False)
        # NamedTemporaryFile creates the file with the mode 0600.
        os.chmod(file.name, 0o644)
        os.replace(file.name, output_path)
    except BaseException:
        os.unlink(file.name)
        raise


def extract_stations(pbf_path):
    fuel_path = pbf_path.with_name("fuel.osm.pbf")
    features_path = pbf_path.with_name("fuel.geojsonseq")
    subprocess.run(["osmium", "tags-filter", str(pbf_path), "nwr/amenity=fuel", "-o", str(fuel_path)], check=True)
    subprocess.run(["osmium", "export", str(fuel_path), "-f", "geojsonseq", "--geometry-types=point,polygon",
                    "-o", str(features_path)], check=True)

    with open(features_path, encoding="utf-8") as features:
        return stations_by_ref(features)


def stations_by_ref(lines):
    stations = {}
    for line in lines:
        feature = json.loads(line.lstrip("\x1e"))
        tags = feature["properties"]
        if tags.get("amenity") != "fuel" or "ref:FR:prix-carburants" not in tags:
            continue

        written = _stations(feature["geometry"], tags)
        if not written:
            continue

        for ref in tags["ref:FR:prix-carburants"].split(";"):
            ref = ref.strip()
            if ref:
                stations.setdefault(ref, []).extend(written)

    return stations


def _stations(geometry, tags):
    if geometry["type"] == "Point":
        longitude, latitude = geometry["coordinates"]
        return [{"latitude": latitude, "longitude": longitude, "tags": tags}]

    if geometry["type"] == "MultiPolygon":
        return [
            {"area": [[latitude, longitude] for longitude, latitude in polygon[0][:-1]], "tags": tags}
            for polygon in geometry["coordinates"]
        ]

    return []


def main():
    logging.basicConfig(
        level=config.log_level,
        format="[%(asctime)s] %(levelname)-8s [%(name)s] %(message)s",
    )

    sys.exit(run("https://download.geofabrik.de/europe/france-latest.osm.pbf", "/cache/osm_gas_stations.json"))


if __name__ == "__main__":
    main()
