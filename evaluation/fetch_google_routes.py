#!/usr/bin/env python3
"""Ask Google to drive the routes this project computes. COSTS MONEY.

For every ordered pair of test cities: ask this project for the optimal route
and the waypoints it emits, then ask Google for a driving route through exactly
those waypoints, and keep the whole answer.

    fetch_google_routes.py                    # says what it would cost, spends nothing
    fetch_google_routes.py --limit 10 --yes   # buys ten
    fetch_google_routes.py --yes              # buys the rest

Nothing is requested without `--yes`. A pair already on disk is never requested
again, and a request that fails writes nothing, so it is simply outstanding next
time. That makes a sweep resumable at the granularity of one journey, which
matters when the sweep is 2 450 paid requests long.
"""
import argparse
import datetime
import math
import json
import os
import sys
import time
import urllib.error
import urllib.request

import yaml

from french_tolls.geometry import encode_polyline

DATA_DIR = os.environ.get("DATA_DIR", "/data")
FRENCH_TOLLS_URL = os.environ.get("FRENCH_TOLLS_URL", "http://web:8080")
API_KEY = os.environ.get("GOOGLE_DIRECTIONS_API_KEY", "").strip()

CITIES = os.path.join(DATA_DIR, "test_cities.yaml")
OUT_DIR = os.path.join(DATA_DIR, "google_routes")

ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

# Any request carrying intermediate waypoints falls into Google's Advanced tier.
# Used only to state the cost before it is incurred; it is not billing, it is a
# number to think with.
USD_PER_1000_ADVANCED = 10.0

# Sequential, with a pause. 2 450 requests at this rate is about ten minutes,
# which is dominated by politeness rather than by work, and it keeps a failure
# to one request instead of a burst.
DELAY_S = 0.2


def load_cities():
    if not os.path.exists(CITIES):
        raise SystemExit(f"{CITIES} is missing. Run `make test_cities` first.")
    with open(CITIES) as f:
        cities = (yaml.safe_load(f) or {}).get("cities") or []
    if not cities:
        raise SystemExit(f"{CITIES} holds no cities.")
    return cities


def path_for(origin, destination):
    return os.path.join(OUT_DIR, f"{origin['osm_id']}-{destination['osm_id']}.json")


def outstanding(cities):
    """Every ordered pair with no answer on disk yet.

    Ordered, not unordered: A to B and B to A cross different barriers, are
    priced differently, and get different waypoints, so one says nothing about
    the other.
    """
    pairs = []
    for origin in cities:
        for destination in cities:
            if origin["osm_id"] == destination["osm_id"]:
                continue
            if not os.path.exists(path_for(origin, destination)):
                pairs.append((origin, destination))
    return pairs


def great_circle_km(a, b):
    lat1, lon1 = math.radians(a["latlon"][0]), math.radians(a["latlon"][1])
    lat2, lon2 = math.radians(b["latlon"][0]), math.radians(b["latlon"][1])
    h = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def longest_independent(pairs, count):
    """The longest journeys that share no city with one another.

    Taking the first N outstanding pairs gives N destinations from one origin,
    because the list is ordered origin-major. That is a sample of one city's
    surroundings rather than of the country, and it flatters or damns the
    algorithm according to what happens to lie around that city.

    Longest, because a long journey crosses more of the toll network and gives
    the waypoints more to get wrong. Independent, because a city appearing in
    two journeys makes their results share whatever is peculiar about it.
    """
    ordered = sorted(pairs, key=lambda p: -great_circle_km(p[0], p[1]))

    used = set()
    chosen = []
    for origin, destination in ordered:
        if origin["osm_id"] in used or destination["osm_id"] in used:
            continue
        chosen.append((origin, destination))
        used.add(origin["osm_id"])
        used.add(destination["osm_id"])
        if len(chosen) >= count:
            break

    return chosen


def our_route(origin, destination):
    """This project's optimal route and waypoints, from the running application.

    Asked over HTTP rather than computed here on purpose: what is under
    measurement is what a user is given, not a private copy of the algorithm
    that could drift from it.
    """
    body = json.dumps({
        "from": [origin["latlon"][1], origin["latlon"][0]],
        "to": [destination["latlon"][1], destination["latlon"][0]],
    }).encode()
    request = urllib.request.Request(
        f"{FRENCH_TOLLS_URL}/api/calculate", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.load(response)


def google_request_body(origin, destination, waypoints):
    """The Routes API request, with every choice stated rather than defaulted.

    `TRAFFIC_UNAWARE` is the decision that makes the comparison mean anything:
    it is Google's own name for routing as though the road were empty, which is
    what OSRM computes from its profile's speeds. Anything traffic-aware would
    differ from ours for reasons that have nothing to do with waypoints.

    No departureTime -- supplying one enables traffic, which would make
    TRAFFIC_UNAWARE a contradiction.

    The three route modifiers are all defaults. They are written out anyway, so
    that a change to Google's defaults cannot quietly change what was measured.
    Tolls are emphatically not avoided: a route that uses toll roads is the
    entire subject.

    optimizeWaypointOrder is off and is not decoration. With it on, Google would
    answer a question about a journey nobody asked for.
    """
    def point(lon, lat):
        return {"location": {"latLng": {"latitude": lat, "longitude": lon}}}

    return {
        "origin": point(origin["latlon"][1], origin["latlon"][0]),
        "destination": point(destination["latlon"][1], destination["latlon"][0]),
        "intermediates": [point(lon, lat) for lon, lat in waypoints],
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_UNAWARE",
        "polylineQuality": "HIGH_QUALITY",
        "polylineEncoding": "ENCODED_POLYLINE",
        "computeAlternativeRoutes": False,
        "optimizeWaypointOrder": False,
        "routeModifiers": {
            "avoidTolls": False,
            "avoidHighways": False,
            "avoidFerries": False,
        },
        "units": "METRIC",
        "languageCode": "en",
        "regionCode": "FR",
    }


def ask_google(body):
    """One computeRoutes request, returning the parsed response.

    The field mask asks for everything. Google documents `*` as a development
    convenience and prefers a narrow mask in production; here the whole point is
    that the answer is bought once, and a field not stored today is a field that
    has to be bought again to obtain.
    """
    request = urllib.request.Request(
        ROUTES_ENDPOINT,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": API_KEY,
            "X-Goog-FieldMask": "*",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def store(origin, destination, waypoints, ours, request_body, response_body):
    """Keep the answer, and enough of the question to interpret it later.

    `ours` is stored beside Google's answer rather than left to be recomputed at
    report time. The report then compares what Google was actually asked to
    drive against what it drove; recomputing would compare Google's old answer
    against a route today's algorithm produces, and a change to the algorithm
    would read as Google having changed its mind.
    """
    os.makedirs(OUT_DIR, exist_ok=True)
    path = path_for(origin, destination)
    tmp = f"{path}.part"
    with open(tmp, "w") as f:
        json.dump({
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "origin": origin,
            "destination": destination,
            "waypoints": waypoints,
            "ours": ours,
            "request": request_body,
            "response": response_body,
        }, f)
    os.replace(tmp, path)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true",
                        help="actually spend money; without it, nothing is requested")
    parser.add_argument("--limit", type=int, default=None,
                        help="fetch at most this many journeys this run")
    parser.add_argument("--delay", type=float, default=DELAY_S,
                        help=f"seconds between requests (default {DELAY_S})")
    parser.add_argument("--longest-independent", action="store_true",
                        help="with --limit, pick the longest journeys that share no city "
                             "with one another, rather than the first outstanding pairs")
    args = parser.parse_args()

    cities = load_cities()
    pairs = outstanding(cities)
    total_pairs = len(cities) * (len(cities) - 1)
    done = total_pairs - len(pairs)

    print(f"==> {len(cities)} cities, {total_pairs} ordered pairs")
    print(f"    already bought: {done}")
    print(f"    outstanding:    {len(pairs)}")

    if not pairs:
        print("==> nothing to buy")
        return 0

    if args.longest_independent:
        if not args.limit:
            raise SystemExit("--longest-independent needs --limit to say how many")
        pairs = longest_independent(pairs, args.limit)
        print(f"    selected the {len(pairs)} longest journeys sharing no city:")
        for origin, destination in pairs:
            print(f"      {origin['name']} -> {destination['name']} "
                  f"({great_circle_km(origin, destination):.0f} km apart)")

    planned = min(len(pairs), args.limit) if args.limit else len(pairs)
    cost = planned * USD_PER_1000_ADVANCED / 1000.0
    print(f"    would fetch now: {planned}")
    print(f"    estimated cost:  ${cost:.2f} "
          f"(at ${USD_PER_1000_ADVANCED:.0f} per 1000, Google's Advanced tier)")

    if not API_KEY:
        raise SystemExit(
            "GOOGLE_DIRECTIONS_API_KEY is unset or empty. Set it in .env. "
            "Nothing was requested."
        )

    if not args.yes:
        print()
        print("==> nothing requested. Re-run with --yes to spend the amount above.")
        print("    A first run of `--limit 10 --yes` is the cheap way to see what "
              "comes back before buying the rest.")
        return 0

    print(f"==> fetching {planned} journeys")
    fetched = failures = 0
    started = time.time()

    for origin, destination in pairs[:planned]:
        label = f"{origin['name']} -> {destination['name']}"
        try:
            ours = our_route(origin, destination)
            optimal = ours["optimal"]
            waypoints = optimal["waypoints"]
            body = google_request_body(origin, destination, waypoints)
            response = ask_google(body)
        except urllib.error.HTTPError as e:
            detail = e.read()[:400].decode(errors="replace")
            print(f"    FAILED {label}: HTTP {e.code} {detail}")
            failures += 1
            continue
        except Exception as e:                                     # noqa: BLE001
            print(f"    FAILED {label}: {type(e).__name__}: {e}")
            failures += 1
            continue

        # Our own geometry goes in encoded rather than as an array of floats.
        # Measured over the first ten journeys, that is 24 KB a route instead of
        # 167 KB, and across 2 450 it is a 614 MB corpus instead of 972 MB. It
        # is our data, recomputable for nothing; only Google's answer is stored
        # verbatim, because only Google's answer was paid for.
        store(origin, destination, waypoints, {
            "distance": optimal["distance"],
            "duration": optimal["duration"],
            "cost": optimal["cost"],
            "waypoints_needed": optimal["waypoints_needed"],
            "complete": optimal["complete"],
            "unpriced": optimal["unpriced"],
            "polyline": encode_polyline([(lat, lon) for lon, lat in optimal["nodes"]]),
            "node_count": len(optimal["nodes"]),
            "fast_distance": ours["fast"]["distance"],
            "fast_duration": ours["fast"]["duration"],
            "fast_cost": ours["fast"]["cost"],
        }, body, response)

        fetched += 1
        if fetched % 25 == 0 or fetched == planned:
            rate = fetched / max(time.time() - started, 1e-6)
            print(f"    {fetched}/{planned} fetched, {failures} failed, "
                  f"{rate:.1f}/s")

        time.sleep(args.delay)

    spent = fetched * USD_PER_1000_ADVANCED / 1000.0
    print(f"==> fetched {fetched}, failed {failures}")
    print(f"    spent about ${spent:.2f}")
    print(f"    still outstanding: {len(outstanding(cities))}")
    return 1 if failures and not fetched else 0


if __name__ == "__main__":
    sys.exit(main())
