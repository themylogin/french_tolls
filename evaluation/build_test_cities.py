#!/usr/bin/env python3
"""Fifty cities spread over mainland France, for the Google comparison.

Writes `data/test_cities.yaml`:

    cities:
      - osm_id: 20524
        name: Paris
        latlon: [48.8566, 2.3522]

Two decisions are worth knowing before reading the code.

**Mainland is decided by the road network, with ferries excluded.** A latitude
and longitude box would have to be drawn by hand, would clip somewhere real
sooner or later, and would assert as geography something the graph already
knows. But the plain question -- can the router reach it? -- says yes to
Corsica, because the car profile is happy to take a ferry: measured, Bastia is
21.3 hours from Paris by road and ferry. Asking with `exclude=ferry` is the
question actually meant, and it answers unreachable for Bastia while leaving
Lyon at 5.0 hours either way.

The overseas departments need no handling: the Geofabrik France extract this
project downloads carries none of them. Measured, it holds 0 city or town nodes
outside mainland Europe and Corsica.

**The fifty are chosen for spread, not for size.** Repeatedly taking the
candidate furthest from everything already chosen covers the territory. Taking
the fifty largest would put a handful in the Paris basin and none in the Massif
Central, and the point is to exercise routes across the whole country.
"""
import argparse
import json
import math
import os
import sys
import urllib.parse
import urllib.request

import osmium
import yaml

DATA_DIR = os.environ.get("DATA_DIR", "/data")
TOLL_URL = os.environ.get("OSRM_TOLL_URL", "http://osrm-toll:5000")

FILTERED_PBF = os.path.join(DATA_DIR, "filtered.osm.pbf")
OUT = os.path.join(DATA_DIR, "test_cities.yaml")

# The pipeline's own filtered extract already carries every `place=` node, so
# this reads 20 MB rather than passing over the 4.7 GB original.
PLACE_RANK = ("city", "town")

DEFAULT_COUNT = 50

# Somewhere unambiguously on the mainland road network, used as the origin of
# the reachability test. Paris, Place du Châtelet.
MAINLAND_REFERENCE = (2.347, 48.858)

# One /table request carries up to this many destinations. The routers are
# started with --max-table-size 2000, so this stays under it with room for the
# single source.
TABLE_BATCH = 1500


class Places(osmium.SimpleHandler):
    """Every named node whose `place` is one this cares about."""

    def __init__(self):
        super().__init__()
        self.found = {value: [] for value in PLACE_RANK}

    def node(self, n):
        value = n.tags.get("place")
        if value not in self.found:
            return

        name = n.tags.get("name")
        if not name:
            # A place with no name cannot be reported in a table of results, and
            # every real French city has one.
            return

        try:
            location = (n.location.lat, n.location.lon)
        except osmium.InvalidLocationError:
            return

        self.found[value].append({"osm_id": n.id, "name": name, "latlon": [
            round(location[0], 7), round(location[1], 7)]})


def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.load(r)


def reachable(candidates):
    """Those the router can drive to from the mainland reference.

    Asked with /table in batches rather than one route each: a table of 1 500
    destinations is one request where the routes would be 1 500.
    """
    out = []
    unreachable = 0

    for start in range(0, len(candidates), TABLE_BATCH):
        batch = candidates[start:start + TABLE_BATCH]
        coords = ";".join(
            [f"{MAINLAND_REFERENCE[0]},{MAINLAND_REFERENCE[1]}"] +
            [f"{c['latlon'][1]},{c['latlon'][0]}" for c in batch]
        )
        # exclude=ferry is what makes this mean "mainland". The car profile
        # declares ferry as an excludable class, so the router answers the
        # question without one rather than being asked to score a route it then
        # has to be argued out of.
        url = (f"{TOLL_URL}/table/v1/driving/{coords}"
               f"?sources=0&annotations=duration&exclude=ferry")
        body = get(url)
        if body.get("code") != "Ok":
            raise SystemExit(f"the router refused a table request: {body.get('code')}")

        # durations[0] is the row from the reference to every destination. A null
        # is a destination no route reaches.
        durations = body["durations"][0][1:]
        for candidate, duration in zip(batch, durations):
            if duration is None:
                unreachable += 1
            else:
                out.append(candidate)

    return out, unreachable


def haversine(a, b):
    """Metres between two (lat, lon) pairs."""
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(h))


def spread(candidates, count, already):
    """Farthest-point sampling: each new city is the one furthest from the rest.

    Deterministic, and needs no random seed. Where nothing has been chosen yet,
    it starts from the candidate nearest the centroid of them all, so the first
    pick does not depend on the order the extract happened to yield.
    """
    chosen = list(already)

    if not chosen:
        centroid = (
            sum(c["latlon"][0] for c in candidates) / len(candidates),
            sum(c["latlon"][1] for c in candidates) / len(candidates),
        )
        seed = min(candidates, key=lambda c: (haversine(c["latlon"], centroid), c["osm_id"]))
        chosen.append(seed)

    taken = {c["osm_id"] for c in chosen}
    # Distance from each candidate to the nearest chosen city, kept up to date
    # rather than recomputed: with 50 picks over a few thousand candidates the
    # difference is between instant and noticeable.
    nearest = {
        c["osm_id"]: min(haversine(c["latlon"], ch["latlon"]) for ch in chosen)
        for c in candidates if c["osm_id"] not in taken
    }

    while len(chosen) < count and nearest:
        # The id breaks a tie, so two runs agree.
        best_id = max(nearest, key=lambda i: (nearest[i], -i))
        best = next(c for c in candidates if c["osm_id"] == best_id)
        chosen.append(best)
        taken.add(best_id)
        del nearest[best_id]
        for other_id, distance in nearest.items():
            other = next(c for c in candidates if c["osm_id"] == other_id)
            nearest[other_id] = min(distance, haversine(other["latlon"], best["latlon"]))

    return chosen


def load_existing():
    if not os.path.exists(OUT):
        return []
    with open(OUT) as f:
        parsed = yaml.safe_load(f) or {}
    return parsed.get("cities") or []


def write(cities):
    tmp = OUT + ".part"
    with open(tmp, "w") as f:
        f.write(
            "# Test cities for the Google route comparison: mainland France,\n"
            "# spread over the territory rather than ranked by size.\n"
            "#\n"
            "# Committed, and the ids are load-bearing: data/google_routes/ is keyed\n"
            "# on them, so removing or renumbering a city invalidates every route\n"
            "# that named it. Regenerate only when you mean to buy the routes again.\n"
        )
        yaml.safe_dump({"cities": cities}, f, sort_keys=False, allow_unicode=True, width=100)
    os.replace(tmp, OUT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT,
                        help=f"how many cities to end up with (default {DEFAULT_COUNT})")
    args = parser.parse_args()

    existing = load_existing()
    if len(existing) >= args.count:
        print(f"==> {OUT} already holds {len(existing)} cities; nothing to do")
        return 0

    if not os.path.exists(FILTERED_PBF):
        raise SystemExit(
            f"{FILTERED_PBF} is missing. It is produced by `make build_osm_toll_booths`, "
            f"which filters the France extract down to the place and booth nodes."
        )

    print(f"==> reading places from {FILTERED_PBF}")
    handler = Places()
    handler.apply_file(FILTERED_PBF)
    for value in PLACE_RANK:
        print(f"    place={value}: {len(handler.found[value])}")

    # Cities first; towns only if there are not enough cities to choose from.
    # Reported either way, so the mix is never a surprise.
    candidates = list(handler.found["city"])
    used = ["city"]
    if len(candidates) < args.count * 4:
        candidates += handler.found["town"]
        used.append("town")
    print(f"    drawing from place={'+'.join(used)}: {len(candidates)} candidates")

    print("==> excluding what the router cannot reach by road, ferries excluded")
    candidates, unreachable = reachable(candidates)
    print(f"    unreachable without a ferry (Corsica, islands, off-network): {unreachable}")
    print(f"    reachable candidates: {len(candidates)}")

    if len(candidates) < args.count:
        raise SystemExit(f"only {len(candidates)} reachable candidates for {args.count} cities")

    # Existing entries are kept in place and never reordered: the stored Google
    # routes are keyed on these ids.
    by_id = {c["osm_id"]: c for c in candidates}
    kept = [by_id.get(c["osm_id"], c) for c in existing]
    if existing:
        print(f"==> keeping {len(kept)} cities already in the file")

    chosen = spread(candidates, args.count, kept)
    write(chosen)

    print(f"==> wrote {OUT} with {len(chosen)} cities")
    print(f"    pairs to buy from Google: {len(chosen) * (len(chosen) - 1)} "
          f"(both directions of {len(chosen) * (len(chosen) - 1) // 2})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
