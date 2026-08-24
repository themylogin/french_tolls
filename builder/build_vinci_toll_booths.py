#!/usr/bin/env python3
"""Step 5 -- resolve OSM booth groups to toll operator gare codes.

OSM node ids mean nothing to a tariff consumer; operators identify a gare by
their own code. The Ulys placemark service takes a driven route and returns the
gares on it, so replaying the route set from step 4 resolves the inventory in
one pass with no new routing work.

Correspondence is positional. A placemark corresponds to the booth group with a
member node inside that group's threshold, among the groups that route's `covers`
lists -- 2.5 m for a lane barrier, 10 m for a gantry. Names are not consulted:
operator and OSM names disagree routinely, and `04903 BIARRITZ` is OSM's
`Peage de La Negresse`.

The step is resumable and therefore always runs: it reads its own output to see
which routes it has already asked about, and on a complete file it issues no
request at all.

A gare the operator places too far from the lane a route drives cannot be matched
by position at all. Those are stated by hand in the override file and consumed by
gare number when the spatial match finds nothing.

Strict by construction. A placemark matching no covered group, two covered groups
matching one placemark, a group whose recorded gare would change, and any covered
booth left without a gare at the end of a complete run are all stop conditions --
each means the inventory and the operator disagree, and a guess would bury that.

Outputs:
    <--out>  toll_booths (group -> {id, name} or null), routes
"""

import argparse
import collections
import json
import math
import os
import sys
import time

import osmium
import requests
import yaml

import overrides

BOOTH_TAGS = (("barrier", "toll_booth"), ("highway", "toll_gantry"))

PLACEMARK_URL = "https://api-ulys.azure-api.net/placemark/v2/legs"

# The request body is a precision-6 polyline, as this parameter says. Response
# geometry comes back at precision 5 regardless; see decode_polyline.
PLACEMARK_PARAMS = {"precision": "6", "includeLayersIds": "GaresPeage"}

# Sent by the VINCI Autoroutes route planner. The service rejects a bare request.
PLACEMARK_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json; charset=utf-8",
    "Origin": "https://www.vinci-autoroutes.com",
    "Referer": "https://www.vinci-autoroutes.com/",
    "x-calling-product": "SITE-VA-V2",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
}

# One threshold per kind of booth. A `barrier=toll_booth` is a lane, and the two
# datasets agree on it to within 2.21 m over 3524 measured matches; nothing falls
# in (2.5, 3.0], so 2.5 loses nothing and it resolves the one ambiguous placemark
# in the run. A `highway=toll_gantry` is a portal over the carriageway with no
# lane node for either dataset to anchor on, so the two disagree by several
# metres -- 7.35 m at Cagny, almost all of it *along* the road. 10 m looks unsafe
# (14 of 56 gantries have another group's node within it) and is not: those pairs
# are opposite carriageways of one free-flow point, and matching is restricted to
# one route's `covers`, where the nearest co-covered gantry is 1.8 km away.
BOOTH_THRESHOLD_M = 2.5
GANTRY_THRESHOLD_M = 10.0
MIN_REQUEST_INTERVAL_S = 1.0
MAX_ATTEMPTS = 5
KEY_ENV = "ULYS_SUBSCRIPTION_KEY"
CONNECT_TIMEOUT_S = 600


class Abort(Exception):
    """A disagreement between the inventory and the operator. Never guessed past."""


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

def haversine_m(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(h))


def decode_polyline(encoded, precision=5):
    """Decode an encoded polyline into [(lat, lon), ...].

    Response points are precision 5 even though the submitted geometry is
    precision 6. Decoding a response at 6 puts a French booth in the Gulf of
    Guinea, which shows up only as a match that never happens.
    """
    scale = 10.0 ** precision
    coords, index, lat, lon = [], 0, 0, 0
    while index < len(encoded):
        for axis in range(2):
            shift, result = 0, 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        coords.append((lat / scale, lon / scale))
    return coords


class Grid:
    """Coarse spatial index, for the nearest-booth detail in an abort message."""

    CELL_DEG = 0.02  # ~2.2 km of latitude

    def __init__(self, points):
        self.points = points  # id -> (lat, lon)
        self.cells = collections.defaultdict(list)
        for i, (lat, lon) in points.items():
            self.cells[self._cell(lat, lon)].append(i)

    def _cell(self, lat, lon):
        return int(lat / self.CELL_DEG), int(lon / self.CELL_DEG)

    def nearest(self, point):
        cy, cx = self._cell(*point)
        best, best_id = None, None
        # Widening rings, so a sparse neighbourhood still yields an answer.
        for ring in (1, 4, 16, 64):
            for dy in range(-ring, ring + 1):
                for dx in range(-ring, ring + 1):
                    for i in self.cells.get((cy + dy, cx + dx), ()):
                        d = haversine_m(point, self.points[i])
                        if best is None or d < best:
                            best, best_id = d, i
            if best_id is not None:
                return best, best_id
        return None, None


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

class BoothCollector(osmium.SimpleHandler):
    """Every booth node in the filtered extract, retained or excluded."""

    def __init__(self):
        super().__init__()
        self.coords = {}
        self.gantry = set()
        self.names = {}

    def node(self, n):
        if not n.location.valid():
            return
        if any(n.tags.get(k) == v for k, v in BOOTH_TAGS):
            self.coords[n.id] = (n.location.lat, n.location.lon)
            self.names[n.id] = n.tags.get("name")
            if n.tags.get("highway") == "toll_gantry":
                self.gantry.add(n.id)


def group_thresholds(members, gantry):
    """Match threshold per group, chosen by what kind of booth it holds."""
    out = {}
    for group, nodes in members.items():
        out[group] = (GANTRY_THRESHOLD_M if any(n in gantry for n in nodes)
                      else BOOTH_THRESHOLD_M)
    return out


def load_inventory(path):
    """(members by group, group of node) from the booth inventory."""
    with open(path, encoding="utf-8") as fh:
        inventory = yaml.safe_load(fh)
    members = {rep: [rep] for rep in inventory["toll_booths"]}
    for alias, entry in (inventory.get("aliases") or {}).items():
        members[entry["parent_id"]].append(alias)
    positions = {i: tuple(e["latlon"]) for i, e in inventory["toll_booths"].items()}
    positions.update({i: tuple(e["latlon"]) for i, e in (inventory.get("aliases") or {}).items()})
    return members, positions


def aliases_parent(members, node):
    """The group a node belongs to in the inventory, or None if it has none."""
    for group, nodes in members.items():
        if node in nodes:
            return group
    return None


def load_state(path):
    """Resume state: booth -> gare or None, processed pairs."""
    if not os.path.exists(path):
        return {}, []
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    booths = dict(doc.get("toll_booths") or {})
    stale = sorted(k for k, v in booths.items() if v is None)
    if stale:
        raise Abort(
            f"{path} was written when a booth without a gare was allowed, and "
            f"{len(stale)} entr(y/ies) are null. Delete it and run again.")
    done = [(r["from"], r["to"]) for r in (doc.get("routes") or [])]
    return booths, done


def write_state(path, booths, done):
    doc = {
        "toll_booths": {k: booths[k] for k in sorted(booths)},
        "routes": [{"from": a, "to": b} for a, b in sorted(done)],
    }
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(doc, fh, default_flow_style=False, sort_keys=False, width=100,
                       allow_unicode=True)
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# Services
# --------------------------------------------------------------------------

class Osrm:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def wait_ready(self, timeout_s=CONNECT_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        attempt = 0
        while True:
            attempt += 1
            try:
                self.session.get(
                    f"{self.base_url}/route/v1/driving/2.3522,48.8566;4.8357,45.7640",
                    params={"overview": "false"}, timeout=30,
                ).raise_for_status()
                print(f"    osrm ready after {attempt} attempt(s)")
                return
            except Exception as exc:  # noqa: BLE001 - any failure means not ready yet
                if time.monotonic() >= deadline:
                    raise SystemExit(
                        f"ERROR: {self.base_url} did not become available within "
                        f"{timeout_s}s (last error: {exc}).\n"
                        f"       Is the 'osrm-optimal' service running?"
                    )
                time.sleep(1.0)

    def geometry(self, a, b):
        """Full-overview precision-6 polyline for the driving route a -> b.

        Full, not simplified: a simplified overview drops vertices and pulls the
        line off the carriageway, and the placemark service then misses gares.
        """
        resp = self.session.get(
            f"{self.base_url}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}",
            params={"overview": "full", "geometries": "polyline6", "steps": "false"},
            timeout=180,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != "Ok" or not payload.get("routes"):
            raise Abort(f"osrm returned {payload.get('code')!r} for {a} -> {b}")
        return payload["routes"][0]["geometry"]


class Placemarks:
    """Ulys placemark client: one request per second, five attempts, one thread."""

    def __init__(self, key):
        self.session = requests.Session()
        self.headers = dict(PLACEMARK_HEADERS, **{"Ocp-Apim-Subscription-Key": key})
        self._last = 0.0
        self.requests_made = 0

    def _throttle(self):
        wait = MIN_REQUEST_INTERVAL_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)

    def legs(self, polyline):
        last_error = None
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                # Backoff exceeds the one-per-second floor on its own.
                time.sleep(2.0 ** attempt)
            self._throttle()
            self._last = time.monotonic()
            self.requests_made += 1
            try:
                resp = self.session.post(
                    PLACEMARK_URL, params=PLACEMARK_PARAMS, headers=self.headers,
                    data=json.dumps(polyline).encode("utf-8"), timeout=180,
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:  # noqa: BLE001 - retry every transport failure
                last_error = exc
                continue
            if not isinstance(payload, list):
                last_error = f"expected a list, got {type(payload).__name__}"
                continue
            return payload
        raise Abort(f"placemark service failed after {MAX_ATTEMPTS} attempts: {last_error}")


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------

def placemark_point(entry):
    points = ((entry.get("Placemark") or {}).get("Geometry") or {}).get("Points") or []
    if not points:
        raise Abort(f"placemark carries no point geometry: {entry.get('Placemark')}")
    return decode_polyline(points[0], precision=5)[0]


def unmapped_report(unmapped, booths, members, positions, collector, routes):
    """The table a human needs to decide what to do with each unmapped booth.

    Every column is a reason to reach for a different remedy: a private site is
    ignored, a lane beside a mapped gare gets a `vinci:` entry, and a booth with
    nothing mapped for kilometres means the operator reported no gare at all.
    """
    crossings = collections.Counter(
        c["node_id"] for r in routes for c in r["covers"])
    mapped = {g: v for g, v in booths.items() if g not in unmapped}

    rows = []
    for group in sorted(unmapped,
                        key=lambda g: (collector.names.get(g) or "~", g)):
        best = min(((min(haversine_m(positions[m], positions[x])
                         for m in members[group] for x in members[other]), other)
                    for other in mapped), default=(None, None))
        distance, other = best
        gare = mapped[other] if other is not None else None
        rows.append((
            f"https://www.openstreetmap.org/node/{group}",
            collector.names.get(group) or "(unnamed)",
            "gantry" if group in collector.gantry else "booth",
            str(crossings[group]),
            "-" if gare is None else f"{distance:,.0f} m".replace(",", " "),
            "none recorded" if gare is None else f"{gare['id']} {gare['name']}",
        ))

    head = ("node", "name", "kind", "routes", "nearest", "mapped gare")
    width = [max(len(r[i]) for r in (*rows, head)) for i in range(len(head))]
    # Counts and distances read better against the right edge; the rest left.
    right = (3, 4)

    def rule(left, mid, sep):
        return "  " + left + mid.join("\u2500" * (w + 2) for w in width) + sep

    def row(cells):
        return "  \u2502 " + " \u2502 ".join(
            cell.rjust(width[i]) if i in right else cell.ljust(width[i])
            for i, cell in enumerate(cells)) + " \u2502"

    return [rule("\u250c", "\u252c", "\u2510"),
            row(head),
            rule("\u251c", "\u253c", "\u2524"),
            *(row(r) for r in rows),
            rule("\u2514", "\u2534", "\u2518")]


def resolve_by_override(entry, covers, vinci):
    """Covered groups a hand-stated gare says this placemark belongs to.

    The fallback for a gare the operator places beyond any sane threshold: the
    override names the booth outright, so the placemark is matched by gare number
    instead of by distance.
    """
    gare_id = (entry["Placemark"].get("Tags") or {}).get("ID_PEAGE")
    return [g for g in covers
            if g in vinci and vinci[g]["id"] == str(gare_id)]


def match(point, covers, members, positions, thresholds):
    """Covered groups with a member inside their own threshold, nearest first."""
    hits = []
    for group in covers:
        best = min(haversine_m(point, positions[m]) for m in members[group])
        if best <= thresholds[group]:
            hits.append((best, group))
    hits.sort()
    return hits


def nearest_report(point, covers, members, positions, retained_grid, excluded_grid):
    lines = []
    if covers:
        best, group = min(
            (min(haversine_m(point, positions[m]) for m in members[g]), g) for g in covers
        )
        lines.append(f"       nearest covered group:  {group} at {best:.1f} m")
    d, i = retained_grid.nearest(point)
    if i is not None:
        lines.append(f"       nearest retained booth: {i} at {d:.1f} m")
    d, i = excluded_grid.nearest(point)
    if i is not None:
        lines.append(f"       nearest excluded booth: {i} at {d:.1f} m"
                     f"  (dropped by the through-road filter)")
    return lines


def describe(entry, point):
    pm = entry.get("Placemark") or {}
    return (f"{(pm.get('Tags') or {}).get('ID_PEAGE')} {pm.get('Preview')!r}"
            f" at {point[0]:.5f},{point[1]:.5f}"
            f" (abscissa {entry.get('StartAbscissa')} m, code {pm.get('Code')})")


def process_route(entry_list, route, members, positions, thresholds, booths,
                  retained_grid, excluded_grid, vinci=None, consumed=None):
    """Outcome of one route as (booth updates, matched groups).

    Nothing is applied until every placemark on the route has been matched and
    checked, so a route that aborts leaves no partial record behind.
    """
    # A two-way booth appears once per direction driven; the gare it maps to is
    # a property of the booth, so the candidate list is deduplicated.
    covers = list(dict.fromkeys(
        c["node_id"] for c in route["covers"] if c["node_id"] in members
    ))
    matched = {}
    for entry in entry_list:
        point = placemark_point(entry)
        hits = match(point, covers, members, positions, thresholds)
        if not hits and vinci:
            forced = resolve_by_override(entry, covers, vinci)
            if len(forced) == 1:
                if consumed is not None:
                    consumed.add(forced[0])
                matched[forced[0]] = dict(vinci[forced[0]])
                continue
            if len(forced) > 1:
                raise Abort(
                    f"placemark matches no covered group by position, and more "
                    f"than one covered group states it by hand\n"
                    f"       placemark: {describe(entry, point)}\n"
                    f"       route:     {route['from']} -> {route['to']}\n"
                    f"       groups:    {sorted(forced)}"
                )
        if not hits:
            detail = "\n".join(nearest_report(point, covers, members, positions,
                                              retained_grid, excluded_grid))
            raise Abort(
                f"placemark corresponds to no covered group within its threshold\n"
                f"       placemark: {describe(entry, point)}\n"
                f"       route:     {route['from']} -> {route['to']}\n{detail}"
            )
        if len(hits) > 1:
            groups = ", ".join(f"{g} at {d:.2f} m (limit {thresholds[g]:g} m)"
                               for d, g in hits)
            raise Abort(
                f"placemark corresponds to more than one covered group\n"
                f"       placemark: {describe(entry, point)}\n"
                f"       route:     {route['from']} -> {route['to']}\n"
                f"       groups:    {groups}"
            )
        distance, group = hits[0]
        pm = entry["Placemark"]
        matched[group] = {"id": (pm.get("Tags") or {}).get("ID_PEAGE"),
                          "name": pm.get("Preview")}

    booth_updates = {}
    for group, gare in matched.items():
        recorded = booths.get(group, "\0absent")
        if recorded == "\0absent":
            booth_updates[group] = gare
        elif recorded.get("id") != gare["id"]:
            raise Abort(
                f"group {group} is already recorded as gare {recorded.get('id')} "
                f"({recorded.get('name')!r}) and this route reports "
                f"{gare['id']} ({gare['name']!r})\n"
                f"       route: {route['from']} -> {route['to']}"
            )

    return booth_updates, matched


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--filtered", required=True, help="filtered extract from step 3")
    ap.add_argument("--booths", required=True, help="booth inventory YAML")
    ap.add_argument("--excluded", required=True, help="excluded booth report JSON")
    ap.add_argument("--route-set", required=True, help="route set YAML")
    ap.add_argument("--out", required=True, help="gare mapping YAML")
    ap.add_argument("--osrm", required=True, help="base URL of the OSRM instance")
    ap.add_argument("--overrides", required=True, help="hand-maintained booth overrides YAML")
    ap.add_argument("--survey", metavar="PATH",
                    help="diagnostic: on a stop condition, record it to PATH, skip "
                         "that route, and keep going. The skipped route is not "
                         "marked processed and none of its booths are recorded, so "
                         "a later strict run still meets it.")
    args = ap.parse_args()

    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        print(f"ERROR: {KEY_ENV} is unset or empty.\n"
              f"       Set it in .env; see .env.example for where to read it from.",
              file=sys.stderr)
        return 1

    members, positions = load_inventory(args.booths)
    with open(args.route_set, encoding="utf-8") as fh:
        route_set = yaml.safe_load(fh)
    places = {p["node_id"]: p for p in route_set["places"]}
    routes = route_set["routes"]

    try:
        ov = overrides.load(args.overrides)
    except overrides.OverrideError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    stale = sorted(set(ov.vinci) - set(members))
    if stale:
        print(f"ERROR: vinci override names booth(s) that are not group "
              f"representatives in the inventory: {stale}", file=sys.stderr)
        return 1

    # `type: ignore` and `parent_id` are applied by the extraction step, not
    # here. The override file is deliberately not a make prerequisite -- keying
    # an expensive step to a modification time is what the pipeline avoids -- so
    # nothing otherwise notices that the inventory predates an override edit, and
    # the booth just reappears in the report with no explanation.
    ignored_present = sorted(ov.ignored & set(positions))
    misgrouped = sorted(
        child for child, target in ov.forced.items()
        if child in positions and aliases_parent(members, child) != target)
    if ignored_present or misgrouped:
        print(f"ERROR: {args.booths} does not reflect"
              f" {args.overrides}.", file=sys.stderr)
        for booth in ignored_present:
            print(f"       booth {booth} is ignored by override but still in the"
                  f" inventory", file=sys.stderr)
        for child in misgrouped:
            print(f"       booth {child} is forced into group {ov.forced[child]}"
                  f" by override but the inventory puts it in"
                  f" {aliases_parent(members, child)}", file=sys.stderr)
        print(f"\n       Rebuild it:  rm {args.booths} && make"
              f" build_osm_toll_booths", file=sys.stderr)
        return 1

    booths, done = load_state(args.out)
    done_pairs = set(done)
    outstanding = [r for r in routes if (r["from"], r["to"]) not in done_pairs]
    print(f"==> {len(members)} booth groups, {len(routes)} routes,"
          f" {len(ov.vinci)} gare(s) stated by hand")
    print(f"    {len(done_pairs)} already processed, {len(outstanding)} outstanding")

    # The inventory is read whether or not there is routing to do: the
    # end-of-run check below reports on every processed route, and a rerun with
    # nothing outstanding still has to make that report.
    collector = BoothCollector()
    collector.apply_file(args.filtered)
    thresholds = group_thresholds(members, collector.gantry)

    violations, consumed, skipped = [], set(), set()
    client = None
    started = time.monotonic()

    if outstanding:
        gantry_groups = sum(1 for v in thresholds.values() if v == GANTRY_THRESHOLD_M)
        with open(args.excluded, encoding="utf-8") as fh:
            excluded_ids = {int(k) for k in json.load(fh)}
        retained_grid = Grid({i: p for i, p in positions.items()})
        excluded_grid = Grid({i: collector.coords[i] for i in excluded_ids
                              if i in collector.coords})
        print(f"    {len(retained_grid.points)} retained and "
              f"{len(excluded_grid.points)} excluded booths located")
        print(f"    {gantry_groups} gantry group(s) at {GANTRY_THRESHOLD_M:g} m, "
              f"{len(thresholds) - gantry_groups} booth group(s) at "
              f"{BOOTH_THRESHOLD_M:g} m")

        osrm = Osrm(args.osrm)
        print(f"==> waiting for {args.osrm}")
        osrm.wait_ready()

        client = Placemarks(key)
        matched_total = 0
        try:
            for n, route in enumerate(outstanding, 1):
                a, b = places[route["from"]], places[route["to"]]
                polyline = osrm.geometry(a["latlon"], b["latlon"])
                entry_list = client.legs(polyline)
                try:
                    booth_updates, matched = process_route(
                        entry_list, route, members, positions, thresholds, booths,
                        retained_grid, excluded_grid, ov.vinci, consumed)
                except Abort as exc:
                    if not args.survey:
                        raise
                    violations.append({"from": route["from"], "to": route["to"],
                                       "report": str(exc)})
                    skipped.add((route["from"], route["to"]))
                    print(f"    !! route {route['from']} -> {route['to']} would stop "
                          f"the run ({len(violations)} so far)")
                    continue
                booths.update(booth_updates)
                matched_total += len(matched)
                # Recorded only now: the route is processed in full, so an
                # interruption costs at most this one route.
                done.append((route["from"], route["to"]))
                write_state(args.out, booths, done)
                if n % 25 == 0 or n == len(outstanding):
                    elapsed = time.monotonic() - started
                    print(f"    {n}/{len(outstanding)} routes, {matched_total} "
                          f"placemarks, {client.requests_made} requests, "
                          f"{elapsed / 60:.1f} min")
        except Abort as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    else:
        print("    no routes to query")

    # A hand-stated gare is recorded whether or not a placemark ever needed it.
    for group, gare in ov.vinci.items():
        booths.setdefault(group, dict(gare))
    write_state(args.out, booths, done)

    gares = len({v["id"] for v in booths.values()})
    print(f"==> {len(booths)} groups recorded, mapped to {gares} gares")
    print(f"    {len(done)} routes processed"
          + (f", {client.requests_made} requests" if client else "")
          + f", {(time.monotonic() - started) / 60:.1f} min")

    if args.survey:
        with open(args.survey, "w", encoding="utf-8") as fh:
            json.dump(violations, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"    survey: {len(violations)} route(s) would have stopped the run"
              f" -- see {args.survey}")

    # An override that nothing needed is a stale override. Reported rather than
    # fatal: the booth may simply not be on any route this run covered, and on a
    # rerun with nothing outstanding nothing is consumed at all.
    if outstanding:
        unconsumed = sorted(set(ov.vinci) - consumed)
        if unconsumed:
            print(f"    {len(unconsumed)} hand-stated gare(s) never needed by a "
                  f"placemark:")
            for group in unconsumed:
                gare = ov.vinci[group]
                print(f"      booth {group} -> {gare['id']} {gare['name']!r}")

    # Every booth a processed route drove through has to end up with a gare.
    # Recording nothing for one would publish an inventory that quietly claims
    # less than the operator charges.
    done_pairs = set(done)
    # Restricted to the inventory: the route set is regenerated far less often
    # than the overrides are edited, so it still names booths a later `type:
    # ignore` has since removed. Those are not ours to map.
    covered = {c["node_id"] for r in routes
               if (r["from"], r["to"]) in done_pairs
               for c in r["covers"]} & set(members)
    # A booth the operator does not carry has nothing to map to. It stays in the
    # inventory and in the route set -- it is a real booth a route drives through
    # -- but demanding a gare for it would demand one that does not exist.
    unmapped = sorted(covered - set(booths) - set(ov.absent))
    if unmapped:
        print(f"\nERROR: {len(unmapped)} covered booth(s) have no gare.",
              file=sys.stderr)
        print(f"       Give each one a `vinci:` entry or `type: ignore` in the"
              f" override file, or find why no placemark reports it.\n",
              file=sys.stderr)
        for line in unmapped_report(unmapped, booths, members, positions,
                                    collector, routes):
            print(line, file=sys.stderr)
        return 1
    if skipped:
        print(f"    {len(skipped)} route(s) skipped by --survey; the unmapped "
              f"check above only covers the {len(done)} that were processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
