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

from french_tolls.overlap import decode_polyline, encode_polyline, overlap
from french_tolls.refine import MAX_WAYPOINTS, drift_sections, waypoints_for

DATA_DIR = os.environ.get("DATA_DIR", "/data")
FRENCH_TOLLS_URL = os.environ.get("FRENCH_TOLLS_URL", "http://web:8080")
API_KEY = os.environ.get("GOOGLE_DIRECTIONS_API_KEY", "").strip()

CITIES = os.path.join(DATA_DIR, "test_cities.yaml")
OUT_DIR = os.path.join(DATA_DIR, "google_routes")

ROUTES_ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"

# Google's published free allowance, in requests per calendar month.
#
# Counted rather than priced. The pricing page names Essentials and Pro tiers
# and does not say which a route request carrying intermediate waypoints falls
# into, so a figure in money cannot be derived from it -- and the figure this
# step used to print was not derived from it either, it was written from memory.
# What an operator can act on before a run is how much of the month's allowance
# it will consume, and what that leaves for the application, which shares the key.
FREE_REQUESTS_PER_MONTH = 10000

# Two Google requests per journey. The first asks what Google drives through the
# waypoints the optimal search emitted; the second asks what it drives through
# the refined set, and that is the route a driver is actually sent down. The
# first cannot be skipped -- the refined waypoints are placed in the stretches it
# reveals -- so two is the floor rather than a choice.
REQUESTS_PER_JOURNEY = 2

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
            stored = read_stored(origin, destination)
            if not is_complete(stored):
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

    **This deliberately no longer matches the application.** `refine` asks at
    TRAFFIC_AWARE_OPTIMAL, because the cheaper search invents motorway
    exit-and-re-entry manoeuvres that change which booths a route crosses. This
    measures durations against OSRM's, and there is no setting that answers both
    questions: a traffic-aware duration and an empty-road duration are not
    comparable, whatever the road. So the two diverge on purpose, and what this
    reports is the faithfulness of a route on an empty road rather than of the
    link the bot now emits.

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


def measure(theirs, ours_points):
    """How faithfully Google followed, and how far it strayed."""
    share, length = overlap(theirs, ours_points, )
    sections = drift_sections(theirs, ours_points)
    return share, sum(s["length"] for s in sections), sections


def duration_s(route):
    """Google reports a duration as a string of seconds, like `17802s`."""
    raw = route.get("duration") or route.get("staticDuration")
    if isinstance(raw, str) and raw.endswith("s"):
        return float(raw[:-1])
    return float(raw) if isinstance(raw, (int, float)) else None


def merge_waypoints(sent, added, ours_points):
    """The refined list, in the order our route reaches its members.

    Google is asked to visit waypoints in the order given, so a list in another
    order describes a different journey.
    """
    if not added:
        return [list(w) for w in sent]

    along = [0.0]
    for a, b in zip(ours_points, ours_points[1:]):
        along.append(along[-1] + haversine_m(a, b))

    def at(lon, lat):
        best, best_d = 0, None
        for i, p in enumerate(ours_points):
            d = haversine_m(p, (lat, lon))
            if best_d is None or d < best_d:
                best, best_d = i, d
        return along[best]

    positions = [(at(lon, lat), [lon, lat]) for lon, lat in sent]
    positions += [(w["at_m"], [w["latlon"][1], w["latlon"][0]]) for w in added]
    positions.sort(key=lambda p: p[0])
    return [p[1] for p in positions]


def haversine_m(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371000.0 * math.asin(math.sqrt(h))


def is_complete(stored):
    """Has this journey been bought under the two-phase scheme?

    `refined` is the discriminator rather than `response`. A file written before
    refinement existed carries a `response` too, but it holds the route through
    the *unrefined* waypoints -- the same key meaning a different thing -- and
    such a journey still owes the request that buys the route worth measuring.
    """
    return bool(stored) and "response" in stored and "refined" in stored


def adopt_unrefined(stored):
    """Bring a pre-refinement answer up to the two-phase shape, for nothing.

    Everything phase one would have asked Google is already in the file: the
    waypoints that were sent, our route, and the route Google drove through
    them. So the drift, the refined waypoints and the before-measurements are
    all derivable, and the journey needs only the second request rather than
    both -- twenty requests to bring the corpus forward instead of forty.
    """
    route = (stored.get("response") or {}).get("routes", [None])[0]
    if route is None:
        return None

    sent = stored.get("waypoints") or []
    ours_points = decode_polyline(stored["ours"]["polyline"])
    theirs = decode_polyline(route["polyline"]["encodedPolyline"])
    share, drift, sections = measure(theirs, ours_points)

    budget = MAX_WAYPOINTS - len(sent)
    added = waypoints_for(sections, ours_points, budget)

    out = dict(stored)
    out["sent_waypoints"] = sent
    out["waypoints"] = merge_waypoints(sent, added, ours_points)
    out["added"] = [[w["latlon"][1], w["latlon"][0]] for w in added]
    out["budget"] = budget
    out["before"] = {
        "overlap": share,
        "drift": drift,
        "stretches": len(sections),
        "covered_by_budget": (
            sum(s["length"] for s in sorted(sections, key=lambda s: -s["length"])[:budget]) / drift
            if drift and budget > 0 else (1.0 if not drift else 0.0)),
        "distance": route.get("distanceMeters"),
        "duration": duration_s(route),
    }

    if not added:
        # Google already followed us, so the route on file is the one the link
        # produces. Complete without spending anything at all.
        out["refined"] = False
    else:
        # The stored route was driven through the old waypoints; it is not what
        # the refined link produces, so it is dropped and phase two buys the
        # route that is.
        out.pop("response", None)

    return out


def read_stored(origin, destination):
    """What is already on disk for this journey, or None.

    A journey may be here with only its first phase done -- the sweep writes
    between the two -- so a caller has to look at what it holds, not merely
    whether it exists.
    """
    try:
        with open(path_for(origin, destination)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_stored(origin, destination, payload):
    """Write a journey's answer, atomically."""
    os.makedirs(OUT_DIR, exist_ok=True)
    path = path_for(origin, destination)
    tmp = f"{path}.part"
    with open(tmp, "w") as f:
        json.dump(payload, f)
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
    requests = planned * REQUESTS_PER_JOURNEY
    print(f"    would fetch now: {planned} journeys")
    print(f"    Google requests: up to {requests} "
          f"({REQUESTS_PER_JOURNEY} per journey, one to find the detours and one "
          f"to drive the corrected route)")
    print(f"    of the month's free allowance of {FREE_REQUESTS_PER_MONTH}, that is "
          f"{requests * 100 / FREE_REQUESTS_PER_MONTH:.0f}%, leaving about "
          f"{max(FREE_REQUESTS_PER_MONTH - requests, 0)} for the application, "
          f"which shares the key")

    if not API_KEY:
        raise SystemExit(
            "GOOGLE_DIRECTIONS_API_KEY is unset or empty. Set it in .env. "
            "Nothing was requested."
        )

    if not args.yes:
        print()
        print("==> nothing requested. Re-run with --yes to use the allowance above.")
        print("    A first run of `--limit 10 --yes` is the cheap way to see what "
              "comes back before buying the rest.")
        return 0

    print(f"==> fetching {planned} journeys")
    fetched = failures = requests_made = 0
    started = time.time()

    for origin, destination in pairs[:planned]:
        label = f"{origin['name']} -> {destination['name']}"
        existing = read_stored(origin, destination)

        try:
            if existing is not None and not is_complete(existing) and "before" not in existing:
                # A file from before refinement existed. Everything phase one
                # would ask is already in it, so it is adopted rather than
                # re-bought.
                adopted = adopt_unrefined(existing)
                if adopted is not None:
                    existing = adopted
                    write_stored(origin, destination, existing)

            if existing is None:
                # Phase one. What does Google drive through the waypoints the
                # optimal search emitted? Its answer is not what is measured --
                # a link carries the refined set, so this route describes a link
                # nobody receives -- but the stretches where it left our route
                # are the only thing that says where a new waypoint belongs.
                ours = our_route(origin, destination)
                optimal = ours["optimal"]
                sent = optimal["waypoints"]
                first_body = google_request_body(origin, destination, sent)
                first = ask_google(first_body)
                requests_made += 1

                route = (first.get("routes") or [None])[0]
                if route is None:
                    raise RuntimeError("Google returned no route")

                ours_points = [(lat, lon) for lon, lat in optimal["nodes"]]
                theirs = decode_polyline(route["polyline"]["encodedPolyline"])
                share, drift, sections = measure(theirs, ours_points)

                budget = MAX_WAYPOINTS - len(sent)
                added = waypoints_for(sections, ours_points, budget)
                refined = merge_waypoints(sent, added, ours_points)

                # Of phase one only the numbers survive. They are why the
                # refinement happened and what the improvement is measured
                # against; its geometry is never drawn or ranked, and keeping it
                # would double a corpus already in the hundreds of megabytes.
                existing = {
                    "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "origin": origin,
                    "destination": destination,
                    "sent_waypoints": sent,
                    "waypoints": refined,
                    "added": [[w["latlon"][1], w["latlon"][0]] for w in added],
                    "budget": budget,
                    "before": {
                        "overlap": share,
                        "drift": drift,
                        "stretches": len(sections),
                        "covered_by_budget": (
                            sum(s["length"] for s in sorted(
                                sections, key=lambda s: -s["length"])[:budget]) / drift
                            if drift and budget > 0 else (1.0 if not drift else 0.0)),
                        "distance": route.get("distanceMeters"),
                        "duration": duration_s(route),
                    },
                    "ours": {
                        "distance": optimal["distance"],
                        # `duration_osrm`, not `duration`: the service serves the
                        # latter multiplied by TIME_MULTIPLIER, which is the very
                        # figure this corpus exists to measure. Storing the served
                        # number would make the next report read x1.0 and call the
                        # correction perfect.
                        "duration": optimal["duration_osrm"],
                        "cost": optimal["cost"],
                        "waypoints_needed": optimal["waypoints_needed"],
                        "complete": optimal["complete"],
                        "unpriced": optimal["unpriced"],
                        # Our own geometry encoded rather than as floats: 24 KB a
                        # route instead of 167 KB, and it is our data, free to
                        # recompute. Only Google's answer is stored verbatim,
                        # because only Google's answer was paid for.
                        "polyline": encode_polyline(ours_points),
                        "node_count": len(optimal["nodes"]),
                        "fast_distance": ours["fast"]["distance"],
                        "fast_duration": ours["fast"]["duration_osrm"],
                        "fast_cost": ours["fast"]["cost"],
                    },
                    "request": first_body,
                }

                if not added:
                    # Google already drove our route, so the route it drove *is*
                    # the route the link produces. Nothing more to buy.
                    existing["response"] = first
                    existing["refined"] = False

                # Written before the second request, so a run interrupted
                # between the two resumes rather than paying for phase one again.
                write_stored(origin, destination, existing)

            if "response" not in existing:
                # Phase two. What does Google drive through the refined
                # waypoints? This is the route a driver is sent down, and the
                # only one worth ranking.
                second_body = google_request_body(
                    origin, destination, existing["waypoints"])
                second = ask_google(second_body)
                requests_made += 1
                existing["response"] = second
                existing["request"] = second_body
                existing["refined"] = True
                write_stored(origin, destination, existing)

        except urllib.error.HTTPError as e:
            detail = e.read()[:400].decode(errors="replace")
            print(f"    FAILED {label}: HTTP {e.code} {detail}")
            failures += 1
            continue
        except Exception as e:                                     # noqa: BLE001
            print(f"    FAILED {label}: {type(e).__name__}: {e}")
            failures += 1
            continue

        fetched += 1
        if fetched % 25 == 0 or fetched == planned:
            rate = fetched / max(time.time() - started, 1e-6)
            print(f"    {fetched}/{planned} fetched, {failures} failed, "
                  f"{requests_made} requests, {rate:.1f}/s")

        time.sleep(args.delay)

    print(f"==> fetched {fetched}, failed {failures}")
    print(f"    Google requests made: {requests_made}")
    print(f"    still outstanding: {len(outstanding(cities))}")
    return 1 if failures and not fetched else 0


if __name__ == "__main__":
    sys.exit(main())
