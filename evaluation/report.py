#!/usr/bin/env python3
"""How faithfully did Google drive the routes this project computed?

Reads what was bought under `data/google_routes/` and prints three things:

1. the journeys Google drove least faithfully, with links to look at them;
2. the largest time deviations, in minutes and in proportion, as two lists;
3. the average multiplier from OSRM's travel time to Google's.

Makes no request to Google. It reads what was paid for. What it does ask, of
this project's own routers, is what the same journey looks like today, so a
report can say whether the algorithm has moved since the answers were bought.
"""
import argparse
import glob
import json
import os
import statistics
import sys
import urllib.parse
import urllib.request

from french_tolls.geometry import DEFAULT_CORRIDOR_M, decode_polyline, overlap

DATA_DIR = os.environ.get("DATA_DIR", "/data")
OUT_DIR = os.path.join(DATA_DIR, "google_routes")
FRENCH_TOLLS_URL = os.environ.get("FRENCH_TOLLS_URL", "http://web:8080")
PUBLIC_SITE_URL = os.environ.get(
    "PUBLIC_SITE_URL", "https://french-tolls.undiscoveredlatitudes.com")

TOP = 10


def google_route(stored):
    """The one route Google returned, or None if it returned none."""
    routes = (stored.get("response") or {}).get("routes") or []
    return routes[0] if routes else None


def google_polyline(route):
    encoded = ((route.get("polyline") or {}).get("encodedPolyline"))
    return decode_polyline(encoded) if encoded else []


def google_duration_s(route):
    """Google reports a duration as a string of seconds, like `17802s`."""
    raw = route.get("duration") or route.get("staticDuration")
    if isinstance(raw, str) and raw.endswith("s"):
        return float(raw[:-1])
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def ours_latlon(stored):
    """Our route's geometry as (lat, lon).

    Stored as an encoded polyline. The `nodes` form is still read, so a file
    bought before the corpus moved to encoding is not made unreadable by it --
    a bought answer stays readable, whatever else changes.
    """
    ours = stored["ours"]
    if "polyline" in ours:
        return decode_polyline(ours["polyline"])
    return [(lat, lon) for lon, lat in ours["nodes"]]


def site_link(stored):
    """This project's own map, opened on the journey.

    The page reads a URL fragment of exactly this shape; it is what the Telegram
    bot builds for its own link.
    """
    payload = {
        "from": {"name": stored["origin"]["name"],
                 "lonlat": [stored["origin"]["latlon"][1], stored["origin"]["latlon"][0]]},
        "to": {"name": stored["destination"]["name"],
               "lonlat": [stored["destination"]["latlon"][1], stored["destination"]["latlon"][0]]},
    }
    return f"{PUBLIC_SITE_URL}/#" + urllib.parse.quote(json.dumps(payload), safe="")


def maps_link(stored, with_waypoints):
    """A Google Maps link for the journey, with or without our waypoints.

    With them, it is the route we asked Google to drive. Without them, it is
    what Google does when left alone — which is the comparison that says what
    the waypoints were worth.
    """
    def latlon(pair):
        return f"{pair[0]:.6f},{pair[1]:.6f}"

    query = {
        "api": "1",
        "origin": latlon(stored["origin"]["latlon"]),
        "destination": latlon(stored["destination"]["latlon"]),
    }
    if with_waypoints and stored["waypoints"]:
        query["waypoints"] = "|".join(
            f"{lat:.6f},{lon:.6f}" for lon, lat in stored["waypoints"])

    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(query)


def current_route(stored):
    """What this project answers for the same journey today.

    Bought answers are compared against the route that was sent to Google, not
    against this. This exists so the report can say whether the algorithm has
    moved since — a difference that is about us, not about Google.
    """
    body = json.dumps({
        "from": [stored["origin"]["latlon"][1], stored["origin"]["latlon"][0]],
        "to": [stored["destination"]["latlon"][1], stored["destination"]["latlon"][0]],
    }).encode()
    request = urllib.request.Request(
        f"{FRENCH_TOLLS_URL}/api/calculate", data=body,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.load(response)["optimal"]
    except Exception:                                              # noqa: BLE001
        return None


def load(corridor_m, check_current):
    """Every stored answer, measured."""
    journeys = []
    unusable = 0

    for path in sorted(glob.glob(os.path.join(OUT_DIR, "*.json"))):
        with open(path) as f:
            stored = json.load(f)

        route = google_route(stored)
        if route is None:
            unusable += 1
            continue

        theirs = google_polyline(route)
        mine = ours_latlon(stored)
        share, google_length = overlap(theirs, mine, corridor_m)

        google_seconds = google_duration_s(route)
        our_seconds = stored["ours"]["duration"]
        if not google_seconds or not our_seconds:
            unusable += 1
            continue

        entry = {
            "path": path,
            "stored": stored,
            "overlap": share,
            "google_distance": route.get("distanceMeters"),
            "google_duration": google_seconds,
            "google_length": google_length,
            "our_distance": stored["ours"]["distance"],
            "our_duration": our_seconds,
            "delta_s": google_seconds - our_seconds,
            "ratio": google_seconds / our_seconds,
            "waypoints": len(stored["waypoints"]),
            "complete": stored["ours"].get("complete"),
        }

        if check_current:
            now = current_route(stored)
            entry["moved"] = (
                None if now is None
                else abs(now["distance"] - stored["ours"]["distance"]) > 1.0
            )

        journeys.append(entry)

    return journeys, unusable


def hms(seconds):
    hours, rest = divmod(int(seconds), 3600)
    return f"{hours}h{rest // 60:02d}" if hours else f"{rest // 60}min"


def describe(entry, index):
    stored = entry["stored"]
    o, d = stored["origin"]["name"], stored["destination"]["name"]
    print(f"  {index:2d}. {o} -> {d}")
    print(f"      overlap {entry['overlap'] * 100:5.1f}%   "
          f"waypoints {entry['waypoints']}   "
          f"ours {entry['our_distance'] / 1000:.0f} km / {hms(entry['our_duration'])}   "
          f"Google {(entry['google_distance'] or 0) / 1000:.0f} km / {hms(entry['google_duration'])}")
    print(f"      our map      {site_link(stored)}")
    print(f"      Google, ours {maps_link(stored, True)}")
    print(f"      Google, bare {maps_link(stored, False)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corridor", type=float, default=DEFAULT_CORRIDOR_M,
                        help=f"corridor half-width in metres (default {DEFAULT_CORRIDOR_M:.0f})")
    parser.add_argument("--top", type=int, default=TOP, help=f"how many to list (default {TOP})")
    parser.add_argument("--check-current", action="store_true",
                        help="also ask this project for each journey today, to see if the "
                             "algorithm has moved since the answers were bought")
    args = parser.parse_args()

    if not os.path.isdir(OUT_DIR):
        raise SystemExit(f"{OUT_DIR} does not exist. Run `make test_google_routes` first.")

    journeys, unusable = load(args.corridor, args.check_current)
    if not journeys:
        raise SystemExit(f"no usable answers under {OUT_DIR}.")

    # Coverage first, so no average below is ever mistaken for one over
    # everything.
    cities_path = os.path.join(DATA_DIR, "test_cities.yaml")
    expected = None
    if os.path.exists(cities_path):
        import yaml
        n = len((yaml.safe_load(open(cities_path)) or {}).get("cities") or [])
        expected = n * (n - 1)

    print("=" * 78)
    print("GOOGLE ROUTE COMPARISON")
    print("=" * 78)
    print(f"journeys compared : {len(journeys)}"
          + (f" of {expected} ({len(journeys) * 100 // expected}%)" if expected else ""))
    if expected and len(journeys) < expected:
        print(f"missing           : {expected - len(journeys)} — every figure below is "
              f"over the {len(journeys)} that were bought")
    if unusable:
        print(f"unusable answers  : {unusable}")
    print(f"corridor          : {args.corridor:.0f} m")

    # ---- 1. least faithful -------------------------------------------------
    print()
    print("-" * 78)
    print(f"1. THE {args.top} JOURNEYS GOOGLE DROVE LEAST FAITHFULLY")
    print("-" * 78)
    print("   overlap is the share of Google's route, by length, running within the")
    print("   corridor of ours. 100% means Google drove the road we asked for.")
    print()
    for i, entry in enumerate(sorted(journeys, key=lambda e: e["overlap"])[:args.top], 1):
        describe(entry, i)

    shares = [e["overlap"] for e in journeys]
    print()
    print(f"   overlap over all {len(journeys)}: "
          f"median {statistics.median(shares) * 100:.1f}%, "
          f"mean {statistics.fmean(shares) * 100:.1f}%, "
          f"worst {min(shares) * 100:.1f}%, best {max(shares) * 100:.1f}%")
    for threshold in (0.99, 0.95, 0.90, 0.75, 0.50):
        n = sum(1 for s in shares if s >= threshold)
        print(f"     at or above {threshold * 100:5.1f}%: {n:5d}  ({n * 100 / len(shares):5.1f}%)")

    # ---- 2. time deviations ------------------------------------------------
    print()
    print("-" * 78)
    print(f"2. THE {args.top} LARGEST TIME DEVIATIONS")
    print("-" * 78)
    print("   listed twice because the two disagree: the largest in minutes are long")
    print("   journeys, the largest in proportion are short ones.")
    print()
    print("   by absolute difference (Google minus ours):")
    for i, e in enumerate(sorted(journeys, key=lambda e: -abs(e["delta_s"]))[:args.top], 1):
        s = e["stored"]
        print(f"     {i:2d}. {s['origin']['name']} -> {s['destination']['name']}: "
              f"{e['delta_s'] / 60:+7.1f} min  "
              f"(ours {hms(e['our_duration'])}, Google {hms(e['google_duration'])}, "
              f"x{e['ratio']:.3f})")
    print()
    print("   by proportion:")
    for i, e in enumerate(sorted(journeys, key=lambda e: -abs(e["ratio"] - 1))[:args.top], 1):
        s = e["stored"]
        print(f"     {i:2d}. {s['origin']['name']} -> {s['destination']['name']}: "
              f"x{e['ratio']:.3f}  "
              f"(ours {hms(e['our_duration'])}, Google {hms(e['google_duration'])}, "
              f"{e['delta_s'] / 60:+.1f} min)")

    # ---- 3. the multiplier -------------------------------------------------
    ratios = [e["ratio"] for e in journeys]
    print()
    print("-" * 78)
    print("3. TRAVEL TIME: OSRM TO GOOGLE")
    print("-" * 78)
    print(f"   mean multiplier   : x{statistics.fmean(ratios):.4f}")
    print(f"   median            : x{statistics.median(ratios):.4f}")
    if len(ratios) > 1:
        print(f"   standard deviation: {statistics.stdev(ratios):.4f}")
    ordered = sorted(ratios)
    for label, value in (("min", ordered[0]),
                         ("p10", ordered[len(ordered) // 10]),
                         ("p90", ordered[min(len(ordered) - 1, len(ordered) * 9 // 10)]),
                         ("max", ordered[-1])):
        print(f"   {label:18s}: x{value:.4f}")
    print()
    print(f"   over {len(journeys)} journeys. A multiplier above 1 means Google thinks the")
    print("   drive takes longer than OSRM does.")

    if args.check_current:
        moved = sum(1 for e in journeys if e.get("moved"))
        print()
        print(f"   journeys whose route has changed since it was bought: {moved}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
