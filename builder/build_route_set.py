#!/usr/bin/env python3
"""Step 4 -- find a small set of routes that collectively traverse every booth.

Set cover, with one wrinkle: the universe of sets is not enumerable. ~35k place
nodes give more than a billion ordered pairs, so candidates are *generated*
rather than enumerated, in two waves:

    Wave A  ~100 geographically dispersed cities, all ordered pairs. Sweeps the
            motorway trunk, where most booths are.
    Wave C  for whatever is left, endpoints are *solved* rather than guessed:
            a route u -> v crosses booth b exactly when d(u,v) == d(u,b) + d(b,v),
            and OSRM's table service supplies all three terms. Selection is by
            travel time over the network, so it does not care which way a road
            curves -- which is what the geometric strategies get wrong on
            mountain roads and coastal motorways.

    Wave B  per still-uncovered group, places drawn from a distance band and
            spread over bearing sectors, paired so the booth lies between them.
            Several bands are tried in turn: an autoroute plaza needs a long
            trip to beat the free parallel road, while a toll bridge or a
            barrier on a minor road is only crossed by a short local one.

Coverage is read from OSRM's `annotations=nodes`, which returns raw OSM node ids
along the path -- an exact intersection with the booth inventory, with no
geometric tolerance and no false positives.

Pairs are ordered, not unordered: a plaza is usually two nodes, one per
carriageway, so A->B and B->A cover different sets.

Endpoints are places a car can actually start and finish a trip at, not merely
nodes carrying a `place` tag. A candidate the router snaps more than MAX_SNAP_M
away, or onto a road no car can join from beside it, is dropped before the
search begins: routing from such a node returns a trip that starts in motorway
traffic, leaves at the next interchange and comes back on the opposite
carriageway, paying one gare twice. The measurement is cached in --snap.

An existing route set on disk is loaded and extended rather than rebuilt, so
adding booths to the inventory costs only the search for what they need. A route
whose endpoints have since become ineligible is dropped rather than extended.

The inventory is grouped: parallel lanes of one plaza share a representative id.
Traversing any lane covers the group, so `covers` records representatives.

A booth a car can drive through either way is two tolls, not one, so it is two
coverage targets -- one per approach. `covers` records the node the route
arrived from for those booths, and the search is not done until both directions
have been driven.
"""

import argparse
import collections
import concurrent.futures
import json
import math
import multiprocessing
import os
import sys
import time

import osmium
import requests
import yaml

import booth_groups
import overrides

PLACE_VALUES = ("city", "town", "village", "hamlet", "isolated_dwelling", "locality")

# A place tag says a name belongs to a spot on the map. It does not say a car can
# start a trip there, and in France `place=locality` names fields, woods and farm
# plots: 98% of them are more than 10 m from any routable way. OSRM snaps such a
# node to whatever is nearest, and when that is the autoroute the resulting
# "trip" begins in motorway traffic, leaves at the next interchange and returns
# on the opposite carriageway -- paying both sides of one gare, which no car can
# do. So eligibility is a tag test *and* a reachability test.
#
# 50 m was tried first and lost the two MENPENTI-PRADO 2 booths in Marseille.
# The cause was not the booths but the city: Marseille's own `place=city` node
# is 71.8 m from the nearest routable way, and at 50 m it -- along with 10 of
# France's 66 cities -- stopped being an endpoint at all. Wave A seeds from
# place=city, so the threshold was starving the backbone sweep as well.
#
# 100 m admits every city and 99% of towns and villages while still dropping
# two thirds of localities. It is also the ceiling: at 200 m the Gros Speck ->
# Le Mazet pair comes back, which is one of the nine routes this rule exists to
# remove. The measurement is cached with distances rather than verdicts so that
# moving between these values costs nothing.
MAX_SNAP_M = 100.0

# The sweep is the whole catalogue, and a Python client decoding two million JSON
# responses is bound by the interpreter lock long before OSRM is bound by
# anything. Processes step around that; threads inside each one keep the socket
# busy while it parses.
SNAP_PROCESSES = max(1, (os.cpu_count() or 4) - 4)
SNAP_THREADS = 16          # per process
SNAP_CHUNK = 5000          # ids handed to a worker at a time
SNAP_ANCHOR_TRIES = 3      # nearest cities tried before giving up on a candidate

WAVE_A_SIZE = 100          # dispersed cities seeding the backbone sweep
WAVE_B_MIN_BEARING = 120.0 # degrees; pairs must bracket the booth
WAVE_B_BATCH = 400         # uncovered booths worked per round
MAX_ROUNDS = 40            # backstop; the loop normally ends when a round is dry

# Wave B endpoint selection, tried in order until a group is covered.
#
# No single distance works for every booth. A plaza on a tolled autoroute needs
# a long trip, because between two nearby towns the fastest route takes the free
# parallel road and never touches the toll road. But an isolated booth on a toll
# bridge, tunnel, or minor road is the opposite: a short local trip crosses it,
# and a long-haul pair routes around it entirely. So the bands escalate rather
# than assuming one shape of trip.
# Each strategy is (band for endpoint A, band for endpoint B) in km.
#
# The asymmetric near x far strategy is what reaches interchange ramp tolls. On
# a closed toll system the barrier sits on the slip road, so a route only
# touches it when it enters or leaves the autoroute at exactly that interchange.
# Drawing both endpoints from one band can never arrange that: what is needed is
# one endpoint in the town the ramp serves (forcing that interchange) and one
# far away (forcing the autoroute to beat the free road).
WAVE_B_STRATEGIES = (
    ((40.0, 260.0), (40.0, 260.0)),   # autoroute mainline plazas
    ((3.0, 40.0),   (3.0, 40.0)),     # toll bridges, tunnels, minor roads
    ((0.0, 25.0),   (80.0, 400.0)),   # interchange ramp tolls: near x far
    ((200.0, 600.0), (200.0, 600.0)), # segments only long-haul routes use
)
WAVE_B_NEAR_ENDPOINTS = 8  # candidates taken from the near side of a near x far pair

# Wave C solves for endpoints instead of guessing them.
SOLVE_CANDIDATES = 400     # places offered to the table calls, nearest first
SOLVE_SHORTLIST = 40       # best upstream / downstream places kept per booth
SOLVE_TOLERANCE_S = 5.0    # slack when comparing d(u,v) against d(u,b)+d(b,v)
SOLVE_KEEP = 40            # solved pairs routed per booth
WAVE_B_SECTORS = 12        # bearing sectors around the booth
WAVE_B_PER_SECTOR = 2      # endpoints kept per sector

REQUEST_WORKERS = 24
CONNECT_TIMEOUT_S = 60     # osrm-routed must finish loading before the first query
EARTH_RADIUS_M = 6371000.0


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------
class PlaceCollector(osmium.SimpleHandler):
    """Endpoint candidates from the filtered extract produced by step 3."""

    def __init__(self):
        super().__init__()
        self.places = {}  # node id -> dict(lat, lon, name, place)

    def node(self, n):
        value = n.tags.get("place")
        if value in PLACE_VALUES and n.location.valid():
            self.places[n.id] = {
                "lat": n.location.lat,
                "lon": n.location.lon,
                "name": n.tags.get("name"),
                "place": value,
            }


class BoothCollector(osmium.SimpleHandler):
    """Booth coordinates, needed to find each booth's nearest places."""

    def __init__(self, wanted):
        super().__init__()
        self.wanted = wanted
        self.coords = {}

    def node(self, n):
        if n.id in self.wanted and n.location.valid():
            self.coords[n.id] = (n.location.lat, n.location.lon)


class NoAccessNodes(osmium.SimpleHandler):
    """Node ids belonging to a way a car cannot join from the land beside it.

    Step 3 carved these ways out of the source extract because /nearest reports
    the snapped segment's name and node ids but never its class, and a large
    share of the segments involved carry no name at all.
    """

    def __init__(self):
        super().__init__()
        self.nodes = set()

    def way(self, w):
        for n in w.nodes:
            self.nodes.add(n.ref)


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------
def haversine_m(a, b):
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def bearing_deg(origin, target):
    lat1, lat2 = math.radians(origin[0]), math.radians(target[0])
    dlon = math.radians(target[1] - origin[1])
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return math.degrees(math.atan2(y, x)) % 360.0


def angle_between(a, b):
    return min((a - b) % 360.0, (b - a) % 360.0)


# --------------------------------------------------------------------------
# OSRM
# --------------------------------------------------------------------------
class Osrm:
    def __init__(self, base_url, workers=REQUEST_WORKERS):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.mount(
            "http://", requests.adapters.HTTPAdapter(pool_maxsize=workers * 2)
        )
        self.workers = workers

    def wait_ready(self, timeout_s=CONNECT_TIMEOUT_S):
        """Retry until the server answers.

        osrm-routed loads its graph before it accepts connections, so the first
        query in a fresh `make build_route_set` reliably races it.
        """
        deadline = time.monotonic() + timeout_s
        attempt = 0
        while True:
            attempt += 1
            try:
                # Any well-formed query proves the graph is loaded and serving.
                self.session.get(
                    f"{self.base_url}/route/v1/driving/2.3522,48.8566;4.8357,45.7640",
                    params={"overview": "false"},
                    timeout=30,
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

    def route_nodes(self, a, b):
        """OSM node ids along the driving route, or None if unroutable."""
        url = (
            f"{self.base_url}/route/v1/driving/"
            f"{a['lon']},{a['lat']};{b['lon']},{b['lat']}"
        )
        try:
            resp = self.session.get(
                url,
                params={"annotations": "nodes", "overview": "false", "steps": "false"},
                timeout=120,
            )
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if payload.get("code") != "Ok" or not payload.get("routes"):
            return None
        nodes = []
        for leg in payload["routes"][0]["legs"]:
            nodes.extend(leg.get("annotation", {}).get("nodes", []))
        return nodes

    def nearest(self, lat, lon, attempts=3):
        """(metres to the snapped position, ids of the snapped segment's nodes).

        Returns None when the query fails after retrying, which is treated as a
        place with no measurement rather than a place at distance zero.
        """
        for _ in range(attempts):
            try:
                resp = self.session.get(
                    f"{self.base_url}/nearest/v1/driving/{lon},{lat}",
                    params={"number": 1}, timeout=60,
                )
            except requests.RequestException:
                continue
            if resp.status_code != 200:
                continue
            waypoints = resp.json().get("waypoints") or []
            if not waypoints:
                return None
            w = waypoints[0]
            return w["distance"], [n for n in w.get("nodes", []) if n]
        return None

    def snap_to_booth(self, booth_id, lat, lon, candidates=8):
        """Snapped position and hint for the segment that holds this booth.

        Booths sit on parallel lanes metres apart, so the *first* candidate
        OSRM returns for a booth's own coordinate is frequently a neighbouring
        way. Measuring to that instead of the booth silently solves the pair
        equation for the wrong point. The hint pins later queries to the
        segment that actually contains the booth.
        """
        try:
            resp = self.session.get(
                f"{self.base_url}/nearest/v1/driving/{lon},{lat}",
                params={"number": candidates}, timeout=60,
            )
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        for waypoint in resp.json().get("waypoints", []):
            if booth_id in waypoint.get("nodes", []):
                lon2, lat2 = waypoint["location"]
                return (lon2, lat2), waypoint.get("hint")
        return None

    def table(self, sources, destinations, hints=None):
        """Durations from each source to each destination, in seconds.

        One call replaces a source x destination grid of route queries, which is
        what makes solving for a booth's endpoints affordable.
        """
        coords = ";".join(f"{lon},{lat}" for lon, lat in sources + destinations)
        src = ";".join(str(i) for i in range(len(sources)))
        dst = ";".join(str(i + len(sources)) for i in range(len(destinations)))
        params = {"sources": src, "destinations": dst}
        if hints:
            # One entry per coordinate; blank means "snap normally".
            params["hints"] = ";".join(h or "" for h in hints)
        try:
            resp = self.session.get(
                f"{self.base_url}/table/v1/driving/{coords}",
                params=params,
                timeout=300,
            )
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if payload.get("code") != "Ok":
            return None
        return payload.get("durations")

    def cover_many(self, pairs, places, traversable, resolve, bidirectional):
        """Route each (from, to) pair; return {pair: (targets hit, in order)}.

        A target is (representative, approach). `approach` is the node the route
        arrived from for a booth a car can drive through either way, and None
        otherwise: passing such a gare northbound does not pay the southbound
        toll, so the two directions are separate things to cover.

        Targets come back in the order the route drives them. A consumer that
        charges for the journey has to know which booth came first, and the
        router already reports its nodes in order -- a set would discard that
        for nothing. A target met twice keeps its first position.

        """
        results = {}

        def work(pair):
            nodes = self.route_nodes(places[pair[0]], places[pair[1]])
            if nodes is None:
                return pair, None
            hits = {}  # ordered set: first traversal wins, insertion order kept
            prev = None
            for n in nodes:
                if n in traversable:
                    # Map every traversed lane onto its group representative.
                    rep = resolve.get(n, n)
                    if rep in bidirectional:
                        # No predecessor means the route starts on the booth, so
                        # there is no direction to record and nothing to claim.
                        if prev is not None:
                            hits.setdefault((rep, prev), None)
                    else:
                        hits.setdefault((rep, None), None)
                prev = n
            return pair, tuple(hits)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as pool:
            for pair, covered in pool.map(work, pairs):
                # None is "unroutable", () is "no booths".
                if covered:
                    results[pair] = covered
        return results


# --------------------------------------------------------------------------
# Candidate generation
# --------------------------------------------------------------------------
def dispersed_places(places, count):
    """Farthest-point sampling -- picks network extremities without needing
    population data. Restricted to place=city where possible; cities are the
    better-connected endpoints."""
    pool = [i for i, p in places.items() if p["place"] == "city"]
    if len(pool) < count:
        # Not enough cities to seed the sweep; top up with the rest rather than
        # quietly returning a smaller (and less dispersed) seed set.
        pool += [i for i, p in places.items() if p["place"] != "city"]
    if len(pool) <= count:
        return sorted(pool)

    pool.sort()  # deterministic starting point -> deterministic route set
    coords = {i: (places[i]["lat"], places[i]["lon"]) for i in pool}
    chosen = [pool[0]]
    best = {i: haversine_m(coords[i], coords[chosen[0]]) for i in pool}
    while len(chosen) < count:
        nxt = max(pool, key=lambda i: best[i])
        if best[nxt] <= 0:
            break
        chosen.append(nxt)
        for i in pool:
            best[i] = min(best[i], haversine_m(coords[i], coords[nxt]))
    return chosen


def wave_a_pairs(seeds):
    return [(a, b) for a in seeds for b in seeds if a != b]


def wave_b_pairs(booth_ids, booth_coords, places, place_index, tried, strategy):
    """Endpoint pairs for a batch of booths under one strategy.

    Symmetric strategies spread both endpoints over bearing sectors and require
    them to bracket the booth. Asymmetric (near x far) strategies instead take
    the closest places on one side -- the ones whose natural motorway access is
    this interchange -- and pair each with far places spread over sectors.
    Bracketing is not required there: the near endpoint sits essentially at the
    booth, so a bearing test would be meaningless.
    """
    band_a, band_b = strategy
    symmetric = band_a == band_b
    sector_width = 360.0 / WAVE_B_SECTORS
    pairs = []

    def spread(origin, band):
        """Farthest-first within each bearing sector: longer trips commit to the
        toll road rather than taking the free parallel route."""
        sectors = collections.defaultdict(list)
        for pid, dist_m in place_index.within_band(origin, band[0], band[1]):
            brg = bearing_deg(origin, (places[pid]["lat"], places[pid]["lon"]))
            sectors[int(brg / sector_width)].append((pid, brg, dist_m))
        chosen = []
        for entries in sectors.values():
            entries.sort(key=lambda e: -e[2])
            chosen.extend(entries[:WAVE_B_PER_SECTOR])
        return chosen

    def closest(origin, band):
        banded = place_index.within_band(origin, band[0], band[1])
        banded.sort(key=lambda e: e[1])
        return [(pid, bearing_deg(origin, (places[pid]["lat"], places[pid]["lon"])), d)
                for pid, d in banded[:WAVE_B_NEAR_ENDPOINTS]]

    for bid in booth_ids:
        if bid not in booth_coords:
            continue  # booth carries no usable location
        origin = booth_coords[bid]
        side_a = spread(origin, band_a) if symmetric else closest(origin, band_a)
        side_b = spread(origin, band_b)
        if not side_a or not side_b:
            continue
        for a, brg_a, _ in side_a:
            for b, brg_b, _ in side_b:
                if a == b:
                    continue
                if symmetric and angle_between(brg_a, brg_b) < WAVE_B_MIN_BEARING:
                    continue
                # Both directions: the entry ramp and the exit ramp of one
                # interchange are different nodes, so one order is not enough.
                for pair in ((a, b), (b, a)):
                    if pair not in tried:
                        pairs.append(pair)
    return pairs


def solve_pairs(osrm, booth_xy, candidates, places, tried, booth_hint=None):
    """Endpoint pairs whose fastest route provably crosses this booth.

    A route u -> v passes through b exactly when

        d(u, v) == d(u, b) + d(b, v)

    so three table calls -- everyone to b, b to everyone, and the shortlist
    against itself -- identify the pairs outright. Selection is by travel time
    over the network, never by straight-line geometry: on a winding mountain
    road or a coastal motorway a compass bearing says nothing about which way
    the road actually runs, which is what made the earlier sector heuristics
    miss these booths entirely.
    """
    if not candidates:
        return []
    coords = [(places[p]["lon"], places[p]["lat"]) for p in candidates]

    blanks = [None] * len(coords)
    to_b = osrm.table(coords, [booth_xy], hints=blanks + [booth_hint])
    from_b = osrm.table([booth_xy], coords, hints=[booth_hint] + blanks)
    if to_b is None or from_b is None:
        return []
    inbound = [(row[0], p) for row, p in zip(to_b, candidates) if row and row[0] is not None]
    outbound = [(d, p) for d, p in zip(from_b[0], candidates) if d is not None]
    if not inbound or not outbound:
        return []

    # Nearest by travel time: the places whose natural way onto this road is
    # through the booth.
    inbound.sort(); outbound.sort()
    ups = [p for _, p in inbound[:SOLVE_SHORTLIST]]
    downs = [p for _, p in outbound[:SOLVE_SHORTLIST]]
    up_cost = dict((p, d) for d, p in inbound[:SOLVE_SHORTLIST])
    down_cost = dict((p, d) for d, p in outbound[:SOLVE_SHORTLIST])

    grid = osrm.table([(places[p]["lon"], places[p]["lat"]) for p in ups],
                      [(places[p]["lon"], places[p]["lat"]) for p in downs])
    if grid is None:
        return []

    solved = []
    for i, u in enumerate(ups):
        for j, v in enumerate(downs):
            if u == v:
                continue
            direct = grid[i][j]
            if direct is None:
                continue
            through = up_cost[u] + down_cost[v]
            # Tolerance absorbs the difference between snapping to the booth
            # itself and to the segment the route actually uses.
            if through - direct <= SOLVE_TOLERANCE_S and (u, v) not in tried:
                solved.append((through - direct, (u, v)))
    solved.sort()
    return [pair for _, pair in solved[:SOLVE_KEEP]]


# Worker state. Set in the parent before the pool is created, so each forked
# child inherits it without any of it crossing a pipe.
_W = {}


def _snap_one(pid):
    """(id, metres the router snaps this place, whether that segment is no-access).

    Two queries, because the two questions have different answers.

    /nearest reports the geometrically closest segment whether or not a car can
    drive out of it. An `service=driveway` stub in its own little component
    answers at 26 m while the router, asked for an actual trip, starts 300 m away
    on the motorway. Measuring the first and believing it describes the second is
    what let a place beside the A89 pass a 50 m test.

    So the distance comes from a route to a real destination -- the nearest
    place=city, which is certainly in the main component -- and the class comes
    from a /nearest at the position that route actually starts from.
    """
    places, index, session, base = _W["places"], _W["index"], _W["session"], _W["base"]
    p = places[pid]
    for anchor in index.nearest((p["lat"], p["lon"]), SNAP_ANCHOR_TRIES):
        if anchor == pid:
            continue
        q = places[anchor]
        try:
            resp = session.get(
                f"{base}/route/v1/driving/"
                f"{p['lon']},{p['lat']};{q['lon']},{q['lat']}",
                params={"overview": "false"}, timeout=60,
            )
            payload = resp.json()
            if payload.get("code") != "Ok":
                continue
            waypoint = payload["waypoints"][0]
            distance = waypoint["distance"]
            lon, lat = waypoint["location"]
            near = session.get(
                f"{base}/nearest/v1/driving/{lon},{lat}",
                params={"number": 1}, timeout=60,
            ).json()["waypoints"][0]
            nodes = [n for n in near.get("nodes", []) if n]
        except Exception:  # noqa: BLE001 - any failure means try the next anchor
            continue
        return pid, round(distance, 1), 1 if any(n in _W["blocked"] for n in nodes) else 0
    return pid, None, None


def _snap_chunk(ids):
    with concurrent.futures.ThreadPoolExecutor(max_workers=SNAP_THREADS) as pool:
        return [r for r in pool.map(_snap_one, ids)]


def measure_reachability(places, no_access_pbf, path, base_url):
    """{place id: [metres, blocked]} for the whole catalogue, cached on disk.

    `metres` is how far from the place the router puts the start of a trip, not
    how far the nearest line on the map is -- see _snap_one. `blocked` marks a
    place the router starts on a road a car cannot join from beside it.

    The record holds the measurement rather than the eligibility verdict, so
    MAX_SNAP_M can be raised without repeating the sweep.

    Reused when it is already on disk, on the same reasoning as the carved
    extracts in step 3: it is derived from the source extract and the routing
    graph, and both of those are themselves governed by existence checks.
    """
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
        print(f"==> reusing {path} ({len(record)} measurement(s))")
        return {int(k): v for k, v in record.items()}

    print(f"==> reading no-access ways from {no_access_pbf}")
    na = NoAccessNodes()
    na.apply_file(no_access_pbf)
    print(f"    {len(na.nodes)} node(s) on a road a car cannot join")

    cities = {i: p for i, p in places.items() if p["place"] == "city"}
    if not cities:
        raise SystemExit("ERROR: no place=city node to anchor the reachability"
                         " sweep on")
    print(f"==> measuring reachability of {len(places)} candidate(s)"
          f" against {len(cities)} city anchor(s)")
    print(f"    {SNAP_PROCESSES} process(es) x {SNAP_THREADS} thread(s)")

    session = requests.Session()
    session.mount("http://", requests.adapters.HTTPAdapter(
        pool_maxsize=SNAP_THREADS * 2))
    _W.update(places=places, index=PlaceIndex(cities), session=session,
              base=base_url.rstrip("/"), blocked=na.nodes)

    ids = sorted(places)
    chunks = [ids[i:i + SNAP_CHUNK] for i in range(0, len(ids), SNAP_CHUNK)]
    out = {}
    unroutable = 0
    started = time.monotonic()
    # fork, so every child inherits _W -- the catalogue and the 675k-node
    # no-access set are read-only here and never cross a pipe.
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=SNAP_PROCESSES,
            mp_context=multiprocessing.get_context("fork")) as pool:
        for n, rows in enumerate(pool.map(_snap_chunk, chunks), start=1):
            for pid, distance, blocked in rows:
                if distance is None:
                    unroutable += 1
                    continue
                out[pid] = [distance, blocked]
            if n % 20 == 0 or n == len(chunks):
                done = min(n * SNAP_CHUNK, len(ids))
                rate = done / max(time.monotonic() - started, 1e-9)
                print(f"    {done}/{len(ids)} ({rate:.0f}/s)", flush=True)
    if unroutable:
        print(f"    {unroutable} candidate(s) reached no city anchor")

    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({str(k): v for k, v in sorted(out.items())}, fh)
    os.replace(tmp, path)
    return out


def eligible_places(places, snap):
    """The candidates a car can actually start and finish a trip at."""
    kept, far, blocked, unmeasured = {}, 0, 0, 0
    for pid, p in places.items():
        record = snap.get(pid)
        if record is None:
            unmeasured += 1
            continue
        distance, is_blocked = record
        if is_blocked:
            blocked += 1
        elif distance > MAX_SNAP_M:
            far += 1
        else:
            kept[pid] = p
    print(f"    {len(kept)}/{len(places)} eligible"
          f" ({100.0 * len(kept) / max(len(places), 1):.1f}%);"
          f" dropped {far} beyond {MAX_SNAP_M:.0f} m,"
          f" {blocked} on a road a car cannot join,"
          f" {unmeasured} unmeasured")
    return kept


class PlaceIndex:
    """Grid index over place nodes for nearest-neighbour lookups."""

    CELL_DEG = 0.25  # ~28 km of latitude

    def __init__(self, places):
        self.places = places
        self.cells = collections.defaultdict(list)
        for i, p in places.items():
            self.cells[self._cell(p["lat"], p["lon"])].append(i)

    def _cell(self, lat, lon):
        return int(lat / self.CELL_DEG), int(lon / self.CELL_DEG)

    def nearest(self, point, count):
        cx, cy = self._cell(point[0], point[1])
        ring = 1
        found = []
        # Widen the search ring until enough candidates are in hand; sparse
        # regions (mountains, coastline) need more than the immediate cells.
        while ring <= 12:
            found = [
                i
                for dx in range(-ring, ring + 1)
                for dy in range(-ring, ring + 1)
                for i in self.cells.get((cx + dx, cy + dy), ())
            ]
            if len(found) >= count:
                break
            ring += 1
        found.sort(
            key=lambda i: haversine_m(
                point, (self.places[i]["lat"], self.places[i]["lon"])
            )
        )
        return found[:count]

    def within_band(self, point, min_km, max_km):
        """[(place id, metres)] for places whose distance falls in the band."""
        rings = int(max_km / (self.CELL_DEG * 111.0)) + 1
        cx, cy = self._cell(point[0], point[1])
        out = []
        for dx in range(-rings, rings + 1):
            for dy in range(-rings, rings + 1):
                for i in self.cells.get((cx + dx, cy + dy), ()):
                    d = haversine_m(point, (self.places[i]["lat"], self.places[i]["lon"]))
                    if min_km * 1000.0 <= d <= max_km * 1000.0:
                        out.append((i, d))
        return out


# --------------------------------------------------------------------------
# Greedy selection
# --------------------------------------------------------------------------
def greedy_select(candidates, uncovered, selected):
    """Take the candidate with the largest marginal gain until none gains.

    Lazy: the cached gain is an upper bound (marginal gain only shrinks as
    booths get covered), so a candidate whose recomputed gain still tops the
    heap is genuinely the best.
    """
    added = 0
    # Candidate covers are ordered sequences; which one to take is a set
    # question, so each is indexed as a set once rather than on every compare.
    sets = {pair: set(cov) for pair, cov in candidates.items()}
    gains = {pair: len(sets[pair] & uncovered) for pair in candidates}
    while True:
        pair = max(gains, key=lambda p: gains[p], default=None)
        if pair is None or gains[pair] == 0:
            break
        actual = len(sets[pair] & uncovered)
        if actual < gains[pair]:
            gains[pair] = actual  # stale bound; re-compete
            continue
        selected[pair] = candidates[pair]
        uncovered -= sets[pair]
        del gains[pair]
        added += 1
    return added


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------
def yaml_scalar(value):
    """JSON encoding is valid YAML and handles quoting, unicode, and null."""
    return json.dumps(value, ensure_ascii=False)


def coverage_targets(booths, bidirectional, plaza_pbf):
    """Every (representative, approach) pair the route set has to cover.

    A one-way booth is one target. A booth a car can drive through either way is
    one target per approach, because each direction is a separate toll. The
    approaches come from the same through-road graph the grouping step uses, so
    the targets and the `prev_node_id` values a route reports are drawn from one
    definition of the road network.
    """
    targets = {(b, None) for b in booths if b not in bidirectional}
    if not bidirectional:
        return targets
    print(f"==> reading approaches for {len(bidirectional)} two-way booth(s)")
    graph = booth_groups.GraphBuilder(bidirectional)
    graph.apply_file(plaza_pbf, locations=True, idx="flex_mem")
    counts = collections.Counter()
    for b in sorted(bidirectional):
        approaches = sorted(graph.rev.get(b, {}))
        counts[len(approaches)] += 1
        # A booth with no approach at all is still a target, so it is reported
        # as uncovered rather than silently dropped from the universe.
        for approach in approaches or [None]:
            targets.add((b, approach))
    print(f"    approaches per two-way booth: {dict(sorted(counts.items()))}")
    return targets


def target_key(target):
    """Sort key for (representative, approach); None sorts before any node id."""
    node_id, approach = target
    return node_id, -1 if approach is None else approach


def write_route_set(path, selected, places):
    # Routes are ordered by endpoint for a stable diff; `covers` is not, because
    # its order is the order the route drives them and is part of the contract.
    routes = [
        {"from": a, "to": b, "covers": list(cov)}
        for (a, b), cov in sorted(selected.items())
    ]
    referenced = sorted({r["from"] for r in routes} | {r["to"] for r in routes})

    lines = ["places:"]
    for nid in referenced:
        p = places[nid]
        lines.append(f"  - name: {yaml_scalar(p['name'])}")
        lines.append(f"    node_id: {nid}")
        lines.append(f"    latlon: [{p['lat']:.7f}, {p['lon']:.7f}]")
    lines.append("routes:")
    for r in routes:
        lines.append(f"  - from: {r['from']}")
        lines.append(f"    to: {r['to']}")
        lines.append("    covers:")
        for node_id, approach in r["covers"]:
            lines.append(f"      - node_id: {node_id}")
            if approach is not None:
                lines.append(f"        prev_node_id: {approach}")

    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, path)
    return routes, referenced


def load_existing(path, places):
    """(from, to) pairs from a previous route set, if one is on disk.

    `places` is the *eligible* catalogue, so a route written before the
    reachability rule tightened is dropped here rather than carried forward. It
    has to go at this point: the greedy pass never revisits a route it has
    already accepted, so one kept now because it still covers something would
    survive every rebuild -- which is what the rule exists to stop.
    """
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    pairs = []
    for route in doc.get("routes") or []:
        a, b = route.get("from"), route.get("to")
        # An endpoint can also vanish when the extract is refreshed; either way
        # skip rather than fail, and the search covers that ground again.
        if a in places and b in places and a != b:
            pairs.append((a, b))
    total = len(doc.get("routes") or [])
    if total != len(pairs):
        print(f"==> {total - len(pairs)} of {total} route(s) on disk have an"
              f" endpoint that is no longer eligible; dropping them")
    return pairs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--filtered", required=True, help="filtered extract from step 3")
    ap.add_argument("--booths", required=True, help="booth inventory YAML")
    ap.add_argument("--plazas", required=True, help="carved plaza-neighbourhood extract")
    ap.add_argument("--no-access", required=True,
                    help="extract of ways a car cannot join, from step 3")
    ap.add_argument("--snap", required=True,
                    help="cached endpoint reachability measurement")
    ap.add_argument("--out", required=True, help="route set YAML")
    ap.add_argument("--uncovered", required=True, help="uncovered booth report JSON")
    ap.add_argument("--osrm", required=True, help="base URL of the OSRM instance")
    ap.add_argument("--overrides", required=True,
                    help="hand-maintained booth overrides YAML")
    args = ap.parse_args()

    try:
        ov = overrides.load(args.overrides)
    except overrides.OverrideError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    with open(args.booths, encoding="utf-8") as fh:
        inventory = yaml.safe_load(fh)
    booth_ids = list(inventory["toll_booths"])
    aliases = dict(inventory.get("aliases") or {})
    booths = set(booth_ids)
    # A route traversing any lane of a plaza covers that plaza, so alias members
    # resolve to their group representative before coverage is recorded. The
    # inventory carries a per-node entry rather than a bare parent id; only the
    # parent is needed here, the positions serve the gare mapping step.
    resolve = {alias: entry["parent_id"] for alias, entry in aliases.items()}
    traversable = booths | set(aliases)
    bidirectional = {b for b, entry in inventory["toll_booths"].items()
                     if entry.get("type") == "bidirectional"}
    print(f"==> {len(booths)} booth groups ({len(aliases)} aliases) in the inventory,"
          f" {len(bidirectional)} of them two-way")

    print("==> loading endpoint candidates")
    pc = PlaceCollector()
    pc.apply_file(args.filtered)
    places = pc.places
    if not places:
        print("ERROR: no endpoint candidates in the filtered extract", file=sys.stderr)
        return 1
    bc = BoothCollector(traversable)
    bc.apply_file(args.filtered)
    print(f"    {len(places)} candidates, {len(bc.coords)} booths located")

    osrm = Osrm(args.osrm)
    print(f"==> waiting for {args.osrm}")
    osrm.wait_ready()

    # Eligibility narrows the pool before anything indexes or samples it.
    # Filtering after selection instead would return fewer endpoints per bearing
    # sector than wave B's strategies intend, weakening the search silently.
    snap = measure_reachability(places, args.no_access, args.snap, args.osrm)
    places = eligible_places(places, snap)
    if not places:
        print(f"ERROR: no candidate survives the reachability test at"
              f" {MAX_SNAP_M:.0f} m", file=sys.stderr)
        return 1

    targets = coverage_targets(booths, bidirectional, args.plazas)
    print(f"    {len(targets)} coverage target(s) over {len(booths)} group(s)")

    index = PlaceIndex(places)
    uncovered = set(targets)
    selected = {}
    tried = set()

    # Resume from an existing route set, so adding booths to the inventory costs
    # only the search for what those booths need rather than a full rebuild.
    #
    # Existing routes are re-queried rather than trusted: their recorded
    # `covers` was computed against whatever inventory existed at the time, and
    # group representatives shift as booths are added or excluded. Re-querying
    # is cheap next to a wave of candidate generation, and it keeps every
    # `covers` list reproducible against the inventory actually in hand.
    existing = load_existing(args.out, places)
    if existing:
        print(f"==> resuming from {len(existing)} existing route(s)")
        for pair, covered in osrm.cover_many(
                existing, places, traversable, resolve, bidirectional).items():
            selected[pair] = covered
            uncovered.difference_update(covered)
        tried.update(existing)
        dropped = len(existing) - len(selected)
        print(f"    kept {len(selected)}"
              + (f", dropped {dropped} that no longer cover anything" if dropped else "")
              + f", {len(targets) - len(uncovered)}/{len(targets)} covered")

    print(f"==> wave A: {WAVE_A_SIZE} dispersed cities")
    seeds = dispersed_places(places, WAVE_A_SIZE)
    pairs = wave_a_pairs(seeds)
    tried.update(pairs)
    print(f"    routing {len(pairs)} ordered pairs")
    candidates = osrm.cover_many(pairs, places, traversable, resolve, bidirectional)
    added = greedy_select(candidates, uncovered, selected)
    print(f"    +{added} routes, {len(targets) - len(uncovered)}/{len(targets)} covered")

    def label(st):
        (a0, a1), (b0, b1) = st
        return (f"{a0:.0f}-{a1:.0f} km" if st[0] == st[1]
                else f"near {a0:.0f}-{a1:.0f} x far {b0:.0f}-{b1:.0f} km")

    # Each strategy is a different guess at what kind of trip crosses this booth, so
    # a group only stops being retried once every strategy has been tried on it.
    for strategy in WAVE_B_STRATEGIES:
        if not uncovered:
            break
        # Booths whose neighbourhood has been explored *for this strategy*. Without
        # this the batch is always the first WAVE_B_BATCH of `uncovered`, so a
        # run whose leading booths are uncoverable regenerates the same pairs
        # every round and stops before reaching the booths behind them.
        attempted = set()
        for rnd in range(1, MAX_ROUNDS + 1):
            if not uncovered:
                break
            pending = [b for b in sorted({t[0] for t in uncovered})
                       if b not in attempted]
            if not pending:
                break
            batch = pending[:WAVE_B_BATCH]
            attempted.update(batch)
            pairs = wave_b_pairs(batch, bc.coords, places, index, tried, strategy)
            if not pairs:
                continue
            tried.update(pairs)
            print(f"==> wave B {label(strategy)} round {rnd}: "
                  f"{len(batch)} groups, {len(pairs)} pairs ({len(pending)} pending)")
            candidates = osrm.cover_many(pairs, places, traversable, resolve, bidirectional)
            added = greedy_select(candidates, uncovered, selected)
            print(f"    +{added} routes, {len(targets) - len(uncovered)}/{len(targets)} covered")
        print(f"==> wave B {label(strategy)} exhausted; "
              f"{len(uncovered)} still uncovered")

    # Wave C: solve for endpoints rather than guess them. Runs last, on whatever
    # the geometric strategies could not reach.
    if uncovered:
        print(f"==> wave C: solving endpoints for {len(uncovered)} target(s)")
        for rnd in range(1, MAX_ROUNDS + 1):
            pending = sorted(b for b in {t[0] for t in uncovered} if b in bc.coords)
            if not pending:
                break
            batch = pending[:WAVE_B_BATCH]
            pairs = []
            for bid in batch:
                lat, lon = bc.coords[bid]
                near = index.nearest((lat, lon), SOLVE_CANDIDATES)
                snapped = osrm.snap_to_booth(bid, lat, lon)
                if snapped is None:
                    continue
                xy, hint = snapped
                pairs.extend(solve_pairs(osrm, xy, near, places, tried, hint))
            pairs = [p for p in dict.fromkeys(pairs) if p not in tried]
            if not pairs:
                print("    no further pairs solved; stopping")
                break
            tried.update(pairs)
            print(f"    round {rnd}: {len(batch)} groups, {len(pairs)} solved pair(s)")
            candidates = osrm.cover_many(pairs, places, traversable, resolve, bidirectional)
            added = greedy_select(candidates, uncovered, selected)
            print(f"    +{added} routes, {len(targets) - len(uncovered)}/{len(targets)} covered")
            if added == 0:
                break

    routes, referenced = write_route_set(args.out, selected, places)

    # Verification: recompute the union from what was actually written rather
    # than trusting the running tally.
    union = set()
    for r in routes:
        union.update(r["covers"])
    missing = sorted(targets - union, key=target_key)

    tmp = args.uncovered + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(
            [{"node_id": b} if approach is None
             else {"node_id": b, "prev_node_id": approach}
             for b, approach in missing],
            fh, indent=2,
        )
        fh.write("\n")
    os.replace(tmp, args.uncovered)

    print()
    print("==> coverage")
    print(f"    routes:    {len(routes)}")
    print(f"    places:    {len(referenced)}")
    print(f"    groups:    {len(booths)} ({len(bidirectional)} two-way)")
    print(f"    covered:   {len(union)}")
    print(f"    uncovered: {len(missing)}")
    print(f"    total:     {len(targets)} target(s)")
    if missing:
        one_way = sum(1 for _, a in missing if a is None)
        print(f"    !! {len(missing)} target(s) NOT covered -- see {args.uncovered}"
              f" ({one_way} booth(s), {len(missing) - one_way} direction(s))")
        print("       Commonly per-lane mapping at a plaza (only one lane is")
        print("       reachable per route) or booths not attached to any way.")
    else:
        print("    all targets covered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
