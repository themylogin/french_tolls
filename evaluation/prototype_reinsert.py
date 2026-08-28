#!/usr/bin/env python3
"""Prototype: where would a waypoint go, to pull Google back onto our route?

Given our optimal route and the route Google actually drove through the
waypoints we gave it, find the stretches where Google left our corridor, rank
them by length, and place a new waypoint in the middle of the worst ones.

The waypoint goes on **our** route, not on Google's. Google drifting means it
found a road it liked better between two of our waypoints; the fix is to name a
point on the road we wanted, in the middle of the stretch it skipped, so the leg
is cut in two and neither half has room for that detour.

Reads only what is already stored. Requests nothing.
"""
import argparse
import glob
import json
import math
import os
import sys
import urllib.parse

from french_tolls.geometry import DEFAULT_CORRIDOR_M, SegmentIndex, decode_polyline

DATA_DIR = os.environ.get("DATA_DIR", "/data")
ROUTES_DIR = os.path.join(DATA_DIR, "google_routes")

# A Google Maps directions URL carries at most nine intermediate waypoints.
MAX_WAYPOINTS = 9

EARTH_RADIUS_M = 6371000.0


def metres(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    h = (math.sin((lat2 - lat1) / 2) ** 2 +
         math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def cumulative(points):
    """Distance along a polyline at each point."""
    out = [0.0]
    for a, b in zip(points, points[1:]):
        out.append(out[-1] + metres(a, b))
    return out


def nearest_position(index, ours_cumulative, point):
    """How far along our route the closest point to `point` lies, in metres.

    Coarse on purpose: the nearest *vertex*, not the nearest point on the
    nearest segment. Our route has a vertex every fifty metres or so, and this
    is used to locate the middle of a stretch that is kilometres long.
    """
    best_i, best_d = None, None
    for i, ours_point in enumerate(index):
        d = metres(ours_point, point)
        if best_d is None or d < best_d:
            best_i, best_d = i, d
    return ours_cumulative[best_i], best_i, best_d


def drift_sections(theirs, ours, corridor_m):
    """The stretches of Google's route that ran outside our corridor.

    Each carries its length, and the points at which it left and rejoined.
    """
    index = SegmentIndex(ours)

    sections = []
    current = None

    for a, b in zip(theirs, theirs[1:]):
        length = metres(a, b)
        if length == 0.0:
            continue
        midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        outside = not index.within(midpoint, corridor_m)

        if outside:
            if current is None:
                current = {"from": a, "to": b, "length": 0.0, "points": [a]}
            current["length"] += length
            current["to"] = b
            current["points"].append(b)
        elif current is not None:
            sections.append(current)
            current = None

    if current is not None:
        sections.append(current)

    return sections


def waypoint_for(section, ours, ours_cumulative, ours_index_points):
    """A point on our route, in the middle of the stretch Google skipped.

    The stretch is located on our route by its two ends -- where Google left and
    where it rejoined -- and the waypoint is our route's own midpoint between
    them. Placing it on Google's drifted path instead would name a point on the
    road we are trying to steer away from.
    """
    start_m, start_i, start_d = nearest_position(
        ours_index_points, ours_cumulative, section["from"])
    end_m, end_i, end_d = nearest_position(
        ours_index_points, ours_cumulative, section["to"])

    if end_m < start_m:
        start_m, end_m = end_m, start_m
        start_i, end_i = end_i, start_i

    middle_m = (start_m + end_m) / 2

    # The vertex of our route nearest that distance along it.
    best_i = min(range(len(ours_cumulative)),
                 key=lambda i: abs(ours_cumulative[i] - middle_m))

    return {
        "latlon": ours[best_i],
        "at_m": ours_cumulative[best_i],
        "skipped_from_m": start_m,
        "skipped_to_m": end_m,
        "skipped_len_m": end_m - start_m,
        "index": best_i,
    }


def maps_url(origin, destination, waypoints):
    query = {
        "api": "1",
        "origin": f"{origin[0]:.6f},{origin[1]:.6f}",
        "destination": f"{destination[0]:.6f},{destination[1]:.6f}",
    }
    if waypoints:
        query["waypoints"] = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in waypoints)
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(query)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True, help="origin city name")
    parser.add_argument("--destination", required=True, help="destination city name")
    parser.add_argument("--corridor", type=float, default=DEFAULT_CORRIDOR_M)
    args = parser.parse_args()

    stored = None
    for path in sorted(glob.glob(os.path.join(ROUTES_DIR, "*.json"))):
        with open(path) as f:
            candidate = json.load(f)
        if (candidate["origin"]["name"] == args.origin
                and candidate["destination"]["name"] == args.destination):
            stored = candidate
            break

    if stored is None:
        raise SystemExit(f"no stored answer for {args.origin} -> {args.destination}")

    ours = decode_polyline(stored["ours"]["polyline"])
    theirs = decode_polyline(
        stored["response"]["routes"][0]["polyline"]["encodedPolyline"])
    existing = [(lat, lon) for lon, lat in stored["waypoints"]]

    ours_cumulative = cumulative(ours)
    total = ours_cumulative[-1]

    print(f"{args.origin} -> {args.destination}")
    print(f"  our route    : {total / 1000:.1f} km, {len(ours)} points")
    print(f"  Google drove : {stored['response']['routes'][0]['distanceMeters'] / 1000:.1f} km")
    print(f"  waypoints now: {len(existing)}   budget left: {MAX_WAYPOINTS - len(existing)}")
    print()

    sections = drift_sections(theirs, ours, args.corridor)
    sections.sort(key=lambda s: -s["length"])

    drift_total = sum(s["length"] for s in sections)
    print(f"  {len(sections)} stretches outside the {args.corridor:.0f} m corridor, "
          f"{drift_total / 1000:.1f} km in total")
    print(f"  the longest ten:")
    for i, section in enumerate(sections[:10], 1):
        print(f"    {i:2d}. {section['length'] / 1000:7.2f} km   "
              f"leaves at {section['from'][0]:.5f},{section['from'][1]:.5f}  "
              f"rejoins at {section['to'][0]:.5f},{section['to'][1]:.5f}")
    print()

    budget = MAX_WAYPOINTS - len(existing)
    if budget <= 0:
        print("  no budget for another waypoint; the link is already full")
        return 0

    print(f"  placing {budget} new waypoint(s), one in the middle of each of the "
          f"{budget} longest stretches:")
    added = []
    for section in sections[:budget]:
        w = waypoint_for(section, ours, ours_cumulative, ours)
        added.append(w)
        print(f"    {w['latlon'][0]:.6f},{w['latlon'][1]:.6f}   "
              f"at {w['at_m'] / 1000:.1f} km along our route  "
              f"(middle of the {w['skipped_len_m'] / 1000:.1f} km Google skipped, "
              f"{w['skipped_from_m'] / 1000:.1f}-{w['skipped_to_m'] / 1000:.1f} km)")
    print()

    # Merged into the existing list, in the order our route reaches them.
    positions = []
    for lat, lon in existing:
        _, i, _ = nearest_position(ours, ours_cumulative, (lat, lon))
        positions.append((ours_cumulative[i], (lat, lon), "existing"))
    for w in added:
        positions.append((w["at_m"], tuple(w["latlon"]), "new"))
    positions.sort()

    print("  the full waypoint list, in driven order:")
    for at, (lat, lon), kind in positions:
        mark = "NEW " if kind == "new" else "    "
        print(f"    {mark}{lat:.6f},{lon:.6f}   at {at / 1000:6.1f} km")
    print()

    merged = [p[1] for p in positions]
    print("  before:")
    print("   ", maps_url(ours[0], ours[-1], existing))
    print("  after:")
    print("   ", maps_url(ours[0], ours[-1], merged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
