#!/usr/bin/env python3
"""Step 7 -- tell the toll side of a two-way booth from the free side.

`type: bidirectional` records one fact: the booth sits on a way OSM tags
two-way. Every consumer that has to decide whether such a booth can be one end
of a ticket needs a different fact -- which side of it is the toll network:

    inside      a vehicle passing here is holding a ticket it will have to pay
    outside     a vehicle passing here circulates freely

Direction of travel does not answer that, however tempting it looks. An
ordinary interchange ramp is driven both ways, so classifying by the node a
route arrived from against the node it departed to puts most booths in a
both-ways bucket and says nothing.

What answers it is the operator's own verdict on the *neighbouring* booths.
Routing away from a two-way booth until the first other booth is met:

    arriving at an exit booth       you were holding a ticket   -> inside
    arriving at an entrance         you were about to take one  -> outside
    departing from an entrance      you had just taken one      -> inside
    departing from an exit          you had just surrendered it -> outside
    reaching a place, no booth      you were never ticketed     -> outside

The two directions are opposites, and using the arrival rule for both makes
every side collect both labels, so nothing can ever settle.

Both kinds of target are needed. Booths sit on the motorway, so the router
leaves by a ramp to reach any of them and the free side is never exercised --
booth targets alone leave a third of the inventory unresolved with `outside`
empty. Places are off the motorway, and are what reach it.

A side with evidence both ways stops the step. The minority is almost never
noise: it is a route over a connection that is not there, or a target whose
recorded role is wrong. Naming it is how those are found, and outvoting it
would bury them.

Outputs:
    <--out>  booth -> {inside_nodes, outside_nodes}
"""

import argparse
import collections
import concurrent.futures
import math
import os
import sys
import threading
import time

import osmium
import requests
import yaml

import build_vinci_prices as bp

INSIDE, OUTSIDE = "inside", "outside"

# Places are drawn one per bearing sector so that every side of a booth is
# offered a destination. A sector's nearest place is taken: the question is
# which way the router leaves, and the nearest answer settles it as well as a
# distant one while crossing less of the network on the way.
SECTORS = 12
PLACE_MIN_KM, PLACE_MAX_KM = 1.0, 60.0

ROUTE_WORKERS = 16
CONNECT_TIMEOUT_S = 60
EARTH_KM = 6371.0


class Abort(Exception):
    """Evidence that contradicts itself. Never averaged over."""


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

def km(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlat, dlon = lat2 - lat1, math.radians(b[1] - a[1])
    h = (math.sin(dlat / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
    return 2 * EARTH_KM * math.asin(math.sqrt(h))


def bearing(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(b[1] - a[1])
    y = math.sin(dlon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

def load_inventory(path):
    """(booth -> adjacency, alias -> parent, traversable nodes, booth -> latlon)."""
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    booths = doc.get("toll_booths") or {}
    aliases = doc.get("aliases") or {}
    resolve = {int(a): int(e["parent_id"]) for a, e in aliases.items()}
    traversable = {int(g) for g in booths} | set(resolve)
    position = {int(g): tuple(e["latlon"]) for g, e in booths.items()}
    adjacency = {int(g): {int(n): bool(v)
                          for n, v in (e.get("adjacent_nodes") or {}).items()}
                 for g, e in booths.items()
                 if (e or {}).get("type") == "bidirectional"}
    return adjacency, resolve, traversable, position


def load_roles(path):
    """group -> 'enter' | 'exit', for the booths the operator has answered on.

    Only one-way booths carry a role. A two-way booth is the thing being
    settled here, so it is never evidence for another one.
    """
    booths, _ = bp.load_state(path)
    return {g: r["type"] for g, r in booths.items()
            if r["type"] in (bp.ENTER, bp.EXIT)}


def load_places(path):
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return [tuple(p["latlon"]) for p in (doc.get("places") or [])]


class PlaceCatalogue(osmium.SimpleHandler):
    """Every `place=` node in the carved extract, as coordinates."""

    def __init__(self):
        super().__init__()
        self.places = []

    def node(self, n):
        if n.tags.get("place") and n.location.valid():
            self.places.append((n.location.lat, n.location.lon))


def load_catalogue(path):
    """The place catalogue, for the sides the route set's places cannot reach.

    The sweep's places are the ones the coverage search used as endpoints -- 745
    of them, chosen to cover booths rather than to sit beside any particular
    one. A side goes unobserved when nothing offered to it is best reached that
    way, and a place far enough off is beaten by the motorway however the roads
    lie: Péage de Thèze's free side is a slow local road against the A 65.

    The extract holds every `place=` node instead, which is where Lalonquette
    comes from -- a village of 257 people, 2.0 km up that local road, absent
    from the route set and enough to settle the side at once.

    Read only when a side is unobserved. On an inventory where every side
    settles, the extract is never opened.
    """
    scan = PlaceCatalogue()
    scan.apply_file(path)
    return scan.places


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

class Router:
    """OSRM route queries. One session per thread, no throttle -- it is local."""

    def __init__(self, base_url, workers=ROUTE_WORKERS):
        self.base_url = base_url.rstrip("/")
        self.workers = workers
        self._local = threading.local()
        self.made = 0

    def _session(self):
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._local.session = requests.Session()
        return session

    def wait_ready(self, timeout_s=CONNECT_TIMEOUT_S):
        deadline = time.monotonic() + timeout_s
        attempt = 0
        while True:
            attempt += 1
            try:
                self._session().get(
                    f"{self.base_url}/route/v1/driving/2.3522,48.8566;4.8357,45.7640",
                    params={"overview": "false"}, timeout=30).raise_for_status()
                print(f"    osrm ready after {attempt} attempt(s)")
                return
            except Exception as exc:  # noqa: BLE001 - any failure means not ready
                if time.monotonic() >= deadline:
                    raise SystemExit(
                        f"ERROR: the routing service at {self.base_url} did not"
                        f" become available within {timeout_s}s"
                        f" (last error: {exc}).\n"
                        f"       Is the 'osrm-toll' service running? Every"
                        f" side of every two-way booth is settled by routing.")
                time.sleep(1.0)

    def nodes(self, a, b):
        """OSM node ids along the route, or None when there is none."""
        try:
            resp = self._session().get(
                f"{self.base_url}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}",
                params={"annotations": "nodes", "overview": "false",
                        "steps": "false"},
                timeout=120)
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if payload.get("code") != "Ok" or not payload.get("routes"):
            return None
        out = []
        for leg in payload["routes"][0]["legs"]:
            out.extend(leg.get("annotation", {}).get("nodes", []))
        return out


# --------------------------------------------------------------------------
# The probe
# --------------------------------------------------------------------------

def targets_for(booth, position, roles, places):
    """[(kind, key, latlon)] -- every priced booth, and a place per sector.

    Both kinds, always. Booth targets can only exercise a booth's inside sides,
    because reaching another booth means taking the motorway; the free side is
    only ever offered by a destination that is not on it.
    """
    out = [("booth", g, position[g]) for g in sorted(roles) if g != booth]
    here = position[booth]
    nearest = {}
    for place in places:
        distance = km(here, place)
        if distance < PLACE_MIN_KM or distance > PLACE_MAX_KM:
            continue
        sector = int(bearing(here, place) // (360 / SECTORS))
        if sector not in nearest or distance < nearest[sector][0]:
            nearest[sector] = (distance, place)
    out.extend(("place", None, place) for _, place in nearest.values())
    return out


def verdict(kind, target_role, outbound):
    """Which side one admitted observation establishes.

    `outbound` is the route running away from the booth, so the target is where
    it arrives; inbound is the route running towards it, so the target is where
    it set off. The two are opposites -- an exit reached means a ticket about to
    be surrendered, an exit left behind means one already surrendered.
    """
    if kind == "place":
        return OUTSIDE
    if outbound:
        return INSIDE if target_role == bp.EXIT else OUTSIDE
    return INSIDE if target_role == bp.ENTER else OUTSIDE


def observe(nodes, booth, target_group, adjacency, resolve, traversable,
            outbound):
    """The adjacent node this route speaks about, or None when it says nothing.

    Three ways a route says nothing: it never traverses the booth, it leaves by
    something that is not an adjacent node, or another booth lies between the
    booth and the target -- in which case what the target is tells us about that
    booth rather than this one.

    Nothing is filtered against a node blacklist. The routing profile makes a
    blacklisted node impassable, so a route over one is never returned.
    """
    if not nodes or booth not in nodes:
        return None
    at = nodes.index(booth)
    if outbound:
        side = nodes[at + 1] if at + 1 < len(nodes) else None
        between = nodes[at + 1:]
    else:
        side = nodes[at - 1] if at else None
        between = nodes[:at]
    if side not in adjacency[booth]:
        return None
    ignore = {booth} if target_group is None else {booth, target_group}
    for node in between:
        if node in traversable and resolve.get(node, node) not in ignore:
            return None
    return side


def probe(router, adjacency, resolve, traversable, position, roles, places,
          progress_every=5):
    """{booth: {side: {verdict: [(kind, key, outbound, km)]}}}."""
    jobs = []
    for booth in sorted(adjacency):
        for kind, key, where in targets_for(booth, position, roles, places):
            jobs.append((booth, kind, key, where, True))
            jobs.append((booth, kind, key, where, False))
    print(f"    {len(jobs)} route(s) to issue"
          f" ({sum(1 for j in jobs if j[1] == 'booth')} to booths,"
          f" {sum(1 for j in jobs if j[1] == 'place')} to places)")

    seen = collections.defaultdict(lambda: collections.defaultdict(
        lambda: collections.defaultdict(list)))
    started = time.monotonic()

    def work(job):
        booth, kind, key, where, outbound = job
        here = position[booth]
        nodes = router.nodes(here, where) if outbound else router.nodes(where, here)
        side = observe(nodes, booth, key, adjacency, resolve, traversable, outbound)
        if side is None:
            return job, None
        length = km(here, where)
        return job, (side, verdict(kind, roles.get(key), outbound), length)

    with concurrent.futures.ThreadPoolExecutor(router.workers) as pool:
        for n, (job, found) in enumerate(pool.map(work, jobs), 1):
            router.made += 1
            if found:
                booth, kind, key, _, outbound = job
                side, which, length = found
                seen[booth][side][which].append((kind, key, outbound, length))
            if n % (len(jobs) // progress_every or 1) == 0:
                print(f"    {n}/{len(jobs)} routes,"
                      f" {(time.monotonic() - started) / 60:.1f} min")
    total = sum(len(v) for b in seen.values() for s in b.values() for v in s.values())
    print(f"    {total} admitted observation(s)")
    return seen


# --------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------

def unobserved_sides(adjacency, seen):
    """{booth: [side, ...]} for every side the sweep said nothing about."""
    out = {}
    for booth in sorted(adjacency):
        missing = [node for node in sorted(adjacency[booth])
                   if not seen.get(booth, {}).get(node)]
        if missing:
            out[booth] = missing
    return out


def retry_from_catalogue(router, booths, adjacency, resolve, traversable,
                         position, roles, catalogue, seen):
    """Offer the catalogue's places to the sides the sweep left unobserved.

    Only those sides, and only those booths. A side the sweep settled keeps the
    answer the sweep gave it, so widening the pool here cannot move anything
    already established.

    The targets are chosen by the sweep's own rule -- nearest per bearing
    sector, within the same bounds -- so a side is offered a destination in its
    own direction. Everything else is the sweep's: the same routes in both
    directions, the same `observe`, the same `verdict`.
    """
    jobs = []
    for booth in sorted(booths):
        for kind, key, where in targets_for(booth, position, {}, catalogue):
            jobs.append((booth, kind, key, where, True))
            jobs.append((booth, kind, key, where, False))
    print(f"    {len(jobs)} catalogue route(s) for"
          f" {len(booths)} booth(s) the sweep left unobserved", flush=True)
    if not jobs:
        return {}

    settled_here = collections.defaultdict(set)

    def work(job):
        booth, kind, key, where, outbound = job
        here = position[booth]
        nodes = router.nodes(here, where) if outbound else router.nodes(where, here)
        side = observe(nodes, booth, key, adjacency, resolve, traversable, outbound)
        if side is None:
            return job, None
        return job, (side, verdict(kind, roles.get(key), outbound), km(here, where))

    with concurrent.futures.ThreadPoolExecutor(router.workers) as pool:
        for job, found in pool.map(work, jobs):
            router.made += 1
            if not found:
                continue
            booth, kind, key, _, outbound = job
            side, which, length = found
            if side not in booths[booth]:
                # The sweep already settled this side; the catalogue is here for
                # the ones it did not, and must not add evidence to the rest.
                continue
            seen[booth][side][which].append((kind, key, outbound, length))
            settled_here[booth].add(side)
    return settled_here


def settle(booth, adjacency, seen, gares, names):
    """(inside, outside, unobserved) or raise on a side witnessed both ways."""
    inside, outside, unobserved = [], [], []
    for node in sorted(adjacency[booth]):
        found = seen.get(booth, {}).get(node) or {}
        if INSIDE in found and OUTSIDE in found:
            raise Abort(describe_conflict(booth, node, found, gares, names))
        if INSIDE in found:
            inside.append(node)
        elif OUTSIDE in found:
            outside.append(node)
        else:
            unobserved.append(node)
    return inside, outside, unobserved


def describe_conflict(booth, node, found, gares, names):
    """The message for a side with evidence both ways, minority routes named."""
    counts = {k: len(v) for k, v in found.items()}
    loser = min(counts, key=counts.get)
    lines = [
        f"node {node} of booth {booth} ({gares.get(booth, '-')}"
        f" {names.get(booth, '')}) is witnessed both ways:"
        f" {counts.get(INSIDE, 0)} inside, {counts.get(OUTSIDE, 0)} outside\n"
        f"       The minority is almost never noise. It is a route over a"
        f" connection that is not\n"
        f"       there -- add its nodes to data/nodes_blacklist.yaml and rebuild\n"
        f"       the graph -- or a target whose"
        f" enter/exit role\n"
        f"       is wrong. The {len(found[loser])} {loser} observation(s):"]
    for kind, key, outbound, length in sorted(found[loser], key=lambda r: r[3]):
        what = (f"{gares.get(key, '-')} {names.get(key, '?')}"
                if kind == "booth" else "place")
        lines.append(f"         {'out' if outbound else 'in ':<4}"
                     f" {what:<34} {length:5.0f} km")
    return "\n".join(lines)


def write_sides(path, settled):
    """Ascending ids throughout, so a rerun that learns nothing diffs empty."""
    out = {}
    for booth in sorted(settled):
        inside, outside = settled[booth]
        entry = {}
        if inside:
            entry["inside_nodes"] = sorted(inside)
        if outside:
            entry["outside_nodes"] = sorted(outside)
        out[booth] = entry
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"toll_booths": out}, fh, default_flow_style=False,
                       sort_keys=False, width=100)
    os.replace(tmp, path)


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--booths", required=True, help="booth inventory YAML")
    ap.add_argument("--prices", required=True,
                    help="price file YAML, read for enter/exit roles only")
    ap.add_argument("--gares", required=True, help="gare mapping YAML, for the report")
    ap.add_argument("--route-set", required=True, help="route set YAML, read for places")
    ap.add_argument("--places", required=True,
                    help="filtered extract, read for the place catalogue when a"
                         " side the route set cannot reach is left unobserved")
    ap.add_argument("--out", required=True, help="booth sides YAML")
    ap.add_argument("--osrm", required=True, help="base URL of the OSRM instance")
    args = ap.parse_args()


    adjacency, resolve, traversable, position = load_inventory(args.booths)
    roles = load_roles(args.prices)
    places = load_places(args.route_set)
    with open(args.gares, encoding="utf-8") as fh:
        mapping = (yaml.safe_load(fh) or {}).get("toll_booths") or {}
    gares = {int(g): str(e["id"]) for g, e in mapping.items()}
    names = {int(g): str(e.get("name") or "") for g, e in mapping.items()}

    print(f"==> {len(adjacency)} two-way booth(s),"
          f" {len(roles)} enter/exit target(s), {len(places)} place(s)")
    missing = [b for b, a in adjacency.items() if not a]
    if missing:
        print(f"ERROR: {len(missing)} two-way booth(s) carry no adjacent_nodes:"
              f" {missing[:5]}\n"
              f"       Regenerate {args.booths} with the step that writes it.",
              file=sys.stderr)
        return 1
    if not adjacency:
        write_sides(args.out, {})
        print("    no two-way booths")
        return 0

    router = Router(args.osrm)
    router.wait_ready()
    started = time.monotonic()
    seen = probe(router, adjacency, resolve, traversable, position, roles,
                 places)

    # A side the sweep said nothing about is offered the place catalogue. The
    # route set's places cover booths rather than sit beside any one of them,
    # and a side whose only destinations are far off loses every route to the
    # motorway. See load_catalogue.
    from_catalogue = {}
    missing = unobserved_sides(adjacency, seen)
    if missing:
        print(f"\n    {len(missing)} booth(s) have a side the route set's places"
              f" did not reach; reading {args.places}", flush=True)
        catalogue = load_catalogue(args.places)
        print(f"    {len(catalogue)} place(s) in the catalogue", flush=True)
        from_catalogue = retry_from_catalogue(
            router, missing, adjacency, resolve, traversable, position, roles,
            catalogue, seen)

    settled, unresolved, conflicts = {}, {}, []
    for booth in sorted(adjacency):
        try:
            inside, outside, unobserved = settle(booth, adjacency, seen, gares, names)
        except Abort as exc:
            conflicts.append(str(exc))
            continue
        settled[booth] = (inside, outside)
        if unobserved:
            unresolved[booth] = unobserved

    if conflicts:
        print(f"ERROR: {len(conflicts)} side(s) are witnessed both ways.",
              file=sys.stderr)
        for text in conflicts:
            print(f"       {text}", file=sys.stderr)
        return 1

    write_sides(args.out, settled)

    kinds = collections.Counter()
    for booth, (inside, outside) in settled.items():
        if booth in unresolved:
            kinds["not settled"] += 1
        elif inside and outside:
            kinds["entrance/exit"] += 1
        else:
            kinds["barrier"] += 1
    print(f"==> {len(settled)} booth(s): {kinds['entrance/exit']} entrance/exit,"
          f" {kinds['barrier']} barrier, {kinds['not settled']} not settled")
    print(f"    {router.made} route(s),"
          f" {(time.monotonic() - started) / 60:.1f} min")

    if from_catalogue:
        print(f"\n    {sum(len(v) for v in from_catalogue.values())} side(s) over"
              f" {len(from_catalogue)} booth(s) were settled from the place"
              f" catalogue, not from the route set's places:")
        rows = [(str(b), gares.get(b, "-"), names.get(b, "")[:24],
                 ", ".join(str(n) for n in sorted(sides)))
                for b, sides in sorted(from_catalogue.items())]
        for line in bp.table(("booth", "gare", "name", "side"), rows):
            print(line)

    if unresolved:
        print(f"\n    {len(unresolved)} booth(s) have a side no route reached."
              f" They are not settled and nothing may treat them as such:")
        rows = [(str(b), gares.get(b, "-"), names.get(b, "")[:24],
                 ", ".join(str(n) for n in unresolved[b]))
                for b in sorted(unresolved)]
        for line in bp.table(("booth", "gare", "name", "unobserved"), rows):
            print(line)

    barriers = [b for b, (i, o) in settled.items()
                if b not in unresolved and not (i and o)]
    if barriers:
        print(f"\n    {len(barriers)} booth(s) are a barrier -- every side"
              f" agrees, so passing changes no ticket:")
        rows = [(str(b), gares.get(b, "-"), names.get(b, "")[:24],
                 INSIDE if settled[b][0] else OUTSIDE) for b in sorted(barriers)]
        for line in bp.table(("booth", "gare", "name", "every side"), rows):
            print(line)

    return 0


if __name__ == "__main__":
    sys.exit(main())
