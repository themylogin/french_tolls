#!/usr/bin/env python3
"""Step 7 -- price the entrance/exit pairs no route in the route set drove.

Step 6 prices what the route set happens to cross. The route set is built to
cover every booth once, not to exercise every pair, so it leaves each entrance
with about two of its exits priced. A closed section sells a ticket for every
entrance/exit combination its roads allow.

Those combinations do not need a route set. A tariff exists for an entrance and
an exit when a vehicle can drive from one to the other without passing a third
booth -- passing one is what closes the ticket. So the grid of every source
against every target is askable directly, and the router settles each cell.

    for every source booth
        route it to each target it has no answer for      (local, batched)
        a booth in between      -> a rejection, recorded and never revisited
        nothing in between      -> a tariff, asked for and recorded

Coverage is decided by node identity. `data/osm_toll_booths.yaml` carries the
representatives and the aliases, so a route's raw node ids map onto booth groups
with no geometric tolerance and no false positives -- the same test step 4 uses.
It needs no extract and no grouping run, only the router.

Endpoints are booths, so they are queried by their own coordinates. Step 4's
snapping hint exists for `place` nodes, which sit off the road; a booth node
sits on its lane, and hinting was measured to change no verdict.

Strict where a wrong answer would look right, and the strictness is the point.
A pair the router calls clean and the operator will not price is not a gap: it
means the route really does pass a booth the inventory does not carry. The step
stops so that the data can be fixed, rather than recording a plausible absence.

Rejections outnumber prices ten to one, so they go to SQLite rather than YAML.
Rewriting a whole file per rejection would cost longer than the run.

Outputs:
    <--out>        prices folded into the price file's own `prices` mappings
    <--rejected>   one row per rejected pair, with the booth in the way
"""

import argparse
import collections
import concurrent.futures
import math
import os
import sqlite3
import sys
import threading
import time

import requests
import yaml

import build_vinci_prices as bp
import overrides

Abort = bp.Abort


def stop(kind, message):
    """An Abort the survey can file under a heading.

    A stop the step anticipates carries a `kind`; one it does not -- the rate
    service failing every retry, say -- carries none, and --survey lets those
    through rather than filing a transport failure among the tariff findings.
    """
    exc = Abort(message)
    exc.kind = kind
    return exc

ENTER, EXIT = bp.ENTER, bp.EXIT
BIDIRECTIONAL, GANTRY = bp.BIDIRECTIONAL, bp.GANTRY

# A booth's role decides which end of a ticket it can be. `bidirectional` is
# both: it is one group in both directions, so a journey enters there driven one
# way and leaves there driven the other. `gantry` and `passthrough` are neither
# -- they charge for themselves rather than closing someone else's ticket.
SOURCE_TYPES = (ENTER, BIDIRECTIONAL)
TARGET_TYPES = (EXIT, BIDIRECTIONAL)

# The price file is rewritten this often. Every price costs a second of the
# operator's time, so losing a few to an interruption is the thing being bought;
# rewriting per price would cost two hours over a full run.
FLUSH_EVERY = 25

ROUTE_WORKERS = 16          # measured: throughput plateaus here
CONNECT_TIMEOUT_S = 60      # osrm-routed must finish loading before the first query
PROGRESS_EVERY = 10         # source booths


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

def load_inventory(path):
    """(node ids that are a booth, alias -> representative, group -> latlon).

    A route crosses a plaza by one of its lanes, and any lane counts. The
    inventory names the representatives under `toll_booths` and the other lanes
    under `aliases` with the representative they belong to, which is the whole
    map from a traversed node to a booth group.
    """
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    booths = doc.get("toll_booths") or {}
    aliases = doc.get("aliases") or {}
    resolve = {int(a): int(e["parent_id"]) for a, e in aliases.items()}
    traversable = {int(g) for g in booths} | set(resolve)
    position = {int(g): tuple(e["latlon"]) for g, e in booths.items()}
    return traversable, resolve, position


def load_sides(path, bidirectional):
    """(booth -> inside nodes, the barriers).

    A booth whose sides all agree is a barrier: you pay passing it and your
    ticket state does not change, so no journey has it as an entrance or an
    exit. Everything else carries a toll side, and that is the side a route has
    to use for the booth to be acting as the end a pair needs.
    """
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    entries = doc.get("toll_booths") or {}
    inside, barriers = {}, set()
    missing = sorted(b for b in bidirectional if int(b) not in
                     {int(g) for g in entries})
    if missing:
        raise Abort(
            f"{path}: {len(missing)} two-way booth(s) have no sides:"
            f" {missing[:5]}\n"
            f"       Run build_booth_sides, or regenerate it if the inventory"
            f" has since changed.")
    for group, entry in entries.items():
        group = int(group)
        ins = set((entry or {}).get("inside_nodes") or [])
        out = set((entry or {}).get("outside_nodes") or [])
        if not ins or not out:
            barriers.add(group)
        else:
            inside[group] = ins
    return inside, barriers


def load_gare_names(path):
    """group -> the operator's own name for its gare, for the survey report."""
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return {int(g): str(e.get("name") or "")
            for g, e in (doc.get("toll_booths") or {}).items()}


def load_priced(path):
    """(group -> record in cents, processed route pairs), read by step 6's own loader.

    Reusing it means this step reads the file exactly as the step that wrote it
    does, and writes it back through the same function -- so a run that learns
    nothing leaves the file byte-identical.
    """
    return bp.load_state(path)


# --------------------------------------------------------------------------
# Rejections
# --------------------------------------------------------------------------

# Two reasons a routed pair is not a ticket, and they want different remedies.
# `booth` is about a third booth standing between the two and names it.
# `wrong side` is about the direction of travel at an endpoint -- a two-way booth
# used on its free side was not acting as the end the pair needs -- and names no
# booth, because none is implicated.
BY_BOOTH, WRONG_SIDE = "booth", "wrong side"

SCHEMA = """
CREATE TABLE IF NOT EXISTS rejected (
    src      INTEGER NOT NULL,   -- enter or bidirectional group
    tgt      INTEGER NOT NULL,   -- exit or bidirectional group
    code     TEXT    NOT NULL,   -- the target's gare
    reason   TEXT    NOT NULL,   -- 'booth' | 'wrong side'
    blocker  INTEGER,            -- the booth in the way; null for a wrong side
    route_m  INTEGER,            -- route length, metres
    PRIMARY KEY (src, tgt)
) WITHOUT ROWID
"""


class Rejections:
    """The pairs a booth already blocks.

    One row per rejection, durable before the next pair is routed. A quarter of
    a million of them, so the store has to append at constant cost: rewriting a
    text file per row was measured at 201 hours against this table's 56 seconds.
    """

    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        # FULL, not NORMAL: the whole point of the row-at-a-time write is that a
        # kill costs nothing, and that holds only if the row is on disk.
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute(SCHEMA)
        self.db.commit()
        # An older database records only the blocking booth, so it cannot say
        # why a pair was rejected. Rebuilding costs routing and no requests,
        # which is cheaper than guessing a reason for rows that never had one.
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(rejected)")}
        if "reason" not in columns:
            raise Abort(
                f"{path} predates the wrong-side rejection and has no `reason`"
                f" column.\n"
                f"       Delete it and run again; it rebuilds from routing alone,"
                f" with no request to the operator.")

    def load(self):
        return {(src, tgt) for src, tgt in
                self.db.execute("SELECT src, tgt FROM rejected")}

    def add(self, src, tgt, code, reason, blocker, route_m):
        self.db.execute("INSERT OR REPLACE INTO rejected VALUES (?, ?, ?, ?, ?, ?)",
                        (src, tgt, code, reason, blocker, route_m))
        self.db.commit()

    def close(self):
        self.db.close()


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------

class Router:
    """OSRM route queries. One session per thread, no throttle -- it is local."""

    def __init__(self, base_url, workers=ROUTE_WORKERS):
        self.base_url = base_url.rstrip("/")
        self.workers = workers
        self._local = threading.local()
        self.routes_made = 0

    def _session(self):
        session = getattr(self._local, "session", None)
        if session is None:
            session = self._local.session = requests.Session()
        return session

    def wait_ready(self, timeout_s=CONNECT_TIMEOUT_S):
        """Retry until the server answers, then fail naming it.

        Checked before the first rate request: the routing service decides which
        pairs are askable, so a run without it would ask about nothing and look
        complete.
        """
        deadline = time.monotonic() + timeout_s
        attempt = 0
        while True:
            attempt += 1
            try:
                self._session().get(
                    f"{self.base_url}/route/v1/driving/2.3522,48.8566;4.8357,45.7640",
                    params={"overview": "false"}, timeout=30,
                ).raise_for_status()
                print(f"    osrm ready after {attempt} attempt(s)")
                return
            except Exception as exc:  # noqa: BLE001 - any failure means not ready yet
                if time.monotonic() >= deadline:
                    raise SystemExit(
                        f"ERROR: the routing service at {self.base_url} did not"
                        f" become available within {timeout_s}s"
                        f" (last error: {exc}).\n"
                        f"       Is the 'osrm-toll' service running? This step"
                        f" cannot decide which pairs are askable without it.")
                time.sleep(1.0)

    def route(self, a, b):
        """(node ids along the route, metres), or None when there is no route."""
        (a_lat, a_lon), (b_lat, b_lon) = a, b
        try:
            resp = self._session().get(
                f"{self.base_url}/route/v1/driving/"
                f"{a_lon},{a_lat};{b_lon},{b_lat}",
                params={"annotations": "nodes", "overview": "false",
                        "steps": "false"},
                timeout=120,
            )
        except requests.RequestException:
            return None
        if resp.status_code != 200:
            return None
        payload = resp.json()
        if payload.get("code") != "Ok" or not payload.get("routes"):
            return None
        found = payload["routes"][0]
        nodes = []
        for leg in found["legs"]:
            nodes.extend(leg.get("annotation", {}).get("nodes", []))
        return nodes, found["distance"]

    def route_many(self, origin, destinations):
        """{group: (nodes, metres) or None} for one source against many targets.

        Batched per source rather than issued pair by pair. It is what lets a
        source's clean pairs be ordered by their real length before any of them
        is priced, and it takes the routing from 51 minutes to about 6.
        """
        results = {}

        def work(item):
            group, position = item
            return group, self.route(origin, position)

        with concurrent.futures.ThreadPoolExecutor(self.workers) as pool:
            for group, answer in pool.map(work, destinations):
                results[group] = answer
        self.routes_made += len(destinations)
        return results


# --------------------------------------------------------------------------
# Verdicts
# --------------------------------------------------------------------------

def blockers_of(nodes, src, tgt, traversable, resolve):
    """Booth groups the route crosses between its endpoints, in driving order.

    Order matters for exactly one thing: the first booth is where the ticket
    would close, so it is the one that explains the rejection. A group met twice
    keeps its first position.
    """
    hits = {}  # ordered set: first traversal wins
    for node in nodes:
        if node in traversable:
            group = resolve.get(node, node)
            if group != src and group != tgt:
                hits.setdefault(group, None)
    return tuple(hits)


def wrong_side(nodes, src, tgt, inside):
    """Whether a two-way end of this pair was used on its free side.

    A two-way booth is an entrance driven one way and an exit driven the other,
    and which it is on a given journey is settled by the side the route uses.
    Entering the network means departing the source *into* it; leaving means
    arriving at the target *from* it. Both want the toll-side node.

    A one-way booth is not tested. Its single traffic sense already fixes its
    role, and it carries no sides.
    """
    if src in inside:
        at = nodes.index(src)
        leaves = nodes[at + 1] if at + 1 < len(nodes) else None
        if leaves not in inside[src]:
            return f"source {src} is left by {leaves}, which is not its toll side"
    if tgt in inside:
        at = len(nodes) - 1 - nodes[::-1].index(tgt)
        reached = nodes[at - 1] if at else None
        if reached not in inside[tgt]:
            return f"target {tgt} is reached from {reached}, which is not its toll side"
    return None


def judge_source(src, targets, answers, gares, traversable, resolve, inside):
    """(rejects, clean, problems) for one source.

    One source's whole batch is judged before any of it is priced, so its clean
    pairs can be taken shortest first -- a short pair is near-certainly a real
    ticket, and the long tail is where a stop comes from.

    `rejects` is [(target, reason, blocker, metres)], `clean` is {gare: (target, metres)},
    and `problems` is [(target, kind, metres, message)] for the two answers that
    are not a verdict at all: a pair with no route, and a route over a connection
    that is not there. They are returned rather than raised so the caller decides
    whether one pair ends the run.
    """
    rejects, clean, problems = [], {}, []
    for tgt in targets:
        answer = answers[tgt]
        if answer is None:
            problems.append((tgt, "no route", None,
                f"no route from booth {src} ({gares[src]}) to booth"
                f" {tgt} ({gares[tgt]})\n"
                f"       Every booth in the inventory sits on the road network,"
                f" so this is a defect in the graph or the inventory rather"
                f" than a fact about tolls."))
            continue
        nodes, metres = answer
        blockers = blockers_of(nodes, src, tgt, traversable, resolve)
        if blockers:
            rejects.append((tgt, BY_BOOTH, blockers[0], round(metres)))
            continue
        # Nothing lies between, which is necessary and not sufficient: the pair
        # is still not a ticket if either two-way end was driven on its free
        # side, because the booth was not acting as the end the pair needs.
        if wrong_side(nodes, src, tgt, inside):
            rejects.append((tgt, WRONG_SIDE, None, round(metres)))
            continue
        # A gare carried by several groups is one tariff. Whichever of its
        # groups the router reaches most directly is the one asked about; the
        # others need no question.
        code = gares[tgt]
        if code not in clean or metres < clean[code][1]:
            clean[code] = (tgt, metres)
    return rejects, clean, problems


def no_tariff(src, src_code, tgt, tgt_code, items):
    """The message for a pair the router found clean and the operator will not price."""
    comments = [c for item in items for c in (item.get("comments") or [])]
    return (
        f"the operator has no tariff for a pair nothing lies between\n"
        f"       pair:     {src} ({src_code}) -> {tgt} ({tgt_code})\n"
        f"       comments: {comments!r}\n"
        f"       A route crossing no booth is usually a ticket the operator\n"
        f"       sells. Two reasons it may not be, and they want different\n"
        f"       remedies:\n"
        f"         - the route passes a booth the inventory does not carry.\n"
        f"           Add it, in data/osm_toll_booths_overrides.yaml or in OSM.\n"
        f"         - the two gares are one interchange under two codes, so\n"
        f"           there is no journey between them to charge for. Check\n"
        f"           how far apart they are before looking for a booth.")


def price_pair(client, booths, src, src_code, tgt, tgt_code):
    """Ask for one pair and record it, or stop having recorded nothing.

    Exactly two passages, so exactly one item is expected and every field of it
    is checked. Step 6 has to walk a cursor over a whole route's passages; here
    an answer that does not name both submitted gares has nowhere to hide.
    """
    where = {"from": src, "to": tgt}
    items = client.rate([src_code, tgt_code])

    # The service says "these two gares are not a ticket" in two shapes. One
    # paired item with no amount is the obvious one. The other is two unpaired
    # items, each naming one gare on its own: asked for a section it does not
    # sell, the service stops pairing and prices each passage as a barrier,
    # finding no tariff for either. Both mean the same thing, and reporting the
    # second as a malformed response would send the reader looking for a bug in
    # the request.
    if not any(item.get("price") is not None for item in items):
        raise stop("no tariff", no_tariff(src, src_code, tgt, tgt_code, items))
    if len(items) != 1:
        raise stop("unexpected answer",
            f"rate service answered a two-passage request with"
            f" {len(items)} item(s), and at least one carries an amount\n"
            f"       pair:  {src} ({src_code}) -> {tgt} ({tgt_code})\n"
            f"       items: {items!r}")
    item = items[0]

    entrance = bp.code_of(item, "entranceToll", where)
    if entrance != src_code:
        raise stop("unexpected answer",
            f"rate item names entrance {entrance}, which was not submitted\n"
            f"       pair: {src} ({src_code}) -> {tgt} ({tgt_code})")
    if item.get("exitToll") is None:
        raise stop("unexpected answer",
            f"rate item carries no exit for a pair that submitted one\n"
            f"       pair: {src} ({src_code}) -> {tgt} ({tgt_code})\n"
            f"       item: {item!r}")
    leaving = bp.code_of(item, "exitToll", where)
    if leaving != tgt_code:
        raise stop("unexpected answer",
            f"rate item names exit {leaving}, which was not submitted\n"
            f"       pair: {src} ({src_code}) -> {tgt} ({tgt_code})")

    if item.get("price") is None:
        raise stop("no tariff", no_tariff(src, src_code, tgt, tgt_code, items))

    cents = bp.to_cents(item["price"],
                        f"price of {src_code} -> {tgt_code}")
    record = booths[src]
    recorded = (record.get("prices") or {}).get(tgt_code)
    if recorded is not None and recorded != cents:
        raise stop("price changed",
            f"booth {src} -> gare {tgt_code} is recorded at"
            f" {bp.to_euros(recorded)} and this pair reports"
            f" {bp.to_euros(cents)}")
    record.setdefault("prices", {})[tgt_code] = cents


# --------------------------------------------------------------------------
# Survey report
# --------------------------------------------------------------------------

OSM_NODE = "https://osm.org/node/{}"
EARTH_M = 6371000.0
NAME_WIDTH = 22


def apart(a, b):
    """Metres between two booths, straight over the ground.

    Not a routing distance and not used for any decision. It is in the report
    because it is what separates the two findings that look alike: a pair the
    operator does not sell because a booth is missing from the inventory, and a
    pair it does not sell because both gares are one interchange.
    """
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, math.radians(b[1] - a[1])
    h = (math.sin(dlat / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
    return 2 * EARTH_M * math.asin(math.sqrt(h))


def label(group, gares, names):
    name = names.get(group, "")
    if len(name) > NAME_WIDTH:
        name = name[:NAME_WIDTH - 1] + "\u2026"
    return f"{gares[group]} {name}".rstrip()


def survey_report(violations, gares, names, position):
    """One bordered table per kind of stop, nearest pair first.

    Grouped by kind because the remedies differ, and sorted by how far apart the
    two booths are because that is the column a reader scans first.
    """
    lines = []
    by_kind = collections.defaultdict(list)
    for kind, src, tgt, route_m, _ in violations:
        by_kind[kind].append((src, tgt, route_m))
    for kind in sorted(by_kind):
        found = sorted(by_kind[kind],
                       key=lambda v: apart(position[v[0]], position[v[1]]))
        rows = []
        for src, tgt, route_m in found:
            metres = apart(position[src], position[tgt])
            rows.append((
                label(src, gares, names), OSM_NODE.format(src),
                label(tgt, gares, names), OSM_NODE.format(tgt),
                f"{metres:,.0f} m" if metres < 1000 else f"{metres / 1000:,.1f} km",
                "-" if route_m is None else f"{route_m / 1000:,.1f} km",
            ))
        lines.append("")
        lines.append(f"    {len(rows)} pair(s): {kind}")
        lines.extend(bp.table(
            ("from", "link", "to", "link", "apart", "route"), rows,
            right=(4, 5)))
    return lines


# --------------------------------------------------------------------------
# Grid
# --------------------------------------------------------------------------

def endpoints(booths, gares, position, kinds, what):
    """Groups of the given roles that carry a gare and a position."""
    out = []
    for group in sorted(booths):
        if booths[group]["type"] not in kinds:
            continue
        if group not in gares:
            raise Abort(f"{what} booth {group} has no gare; run"
                        f" build_vinci_toll_booths")
        if group not in position:
            raise Abort(f"{what} booth {group} is not in the inventory")
        out.append(group)
    return out


def outstanding_for(src, targets, gares, priced, rejected, prohibited=(),
                    barriers=()):
    """The targets this source still has no answer for.

    Five exclusions. Two are about what has already been settled -- a price in
    hand, a rejection on record. Three are about pairs that are not a journey at
    all: two groups carrying one gare are the two carriageways of a single
    plaza, a prohibited pair is one a human has looked at and ruled out, and a
    barrier is a booth no journey ever enters or leaves at.

    Both of the latter are dropped before routing rather than rejected. A
    rejection says a booth lies between; these say there is nothing to ask.
    """
    known = (priced.get(src) or {}).get("prices") or {}
    src_code = gares[src]
    if src in barriers:
        return []
    return [tgt for tgt in targets
            if tgt not in barriers
            and tgt != src
            and gares[tgt] != src_code
            and gares[tgt] not in known
            and (src_code, gares[tgt]) not in prohibited
            and (src, tgt) not in rejected]


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--booths", required=True,
                    help="booth inventory YAML, read for blockers and positions")
    ap.add_argument("--gares", required=True, help="gare mapping YAML from step 5")
    ap.add_argument("--overrides", required=True,
                    help="hand-maintained booth overrides YAML")
    ap.add_argument("--out", required=True, help="price file YAML from step 6")
    ap.add_argument("--sides", required=True,
                    help="two-way booth sides YAML from step 7")
    ap.add_argument("--drop-two-way", action="store_true",
                    help="discard every price with a two-way booth at either end, "
                         "so it is asked again under the side rule, and exit")
    ap.add_argument("--rejected", required=True,
                    help="rejection database (SQLite, created if absent)")
    ap.add_argument("--osrm", required=True, help="base URL of the OSRM instance")
    ap.add_argument("--limit", type=int, metavar="N",
                    help="diagnostic: stop after N source booths")
    ap.add_argument("--survey", action="store_true",
                    help="diagnostic: on a stop condition, record it, skip that "
                         "pair, and keep going. The skipped pair is recorded "
                         "neither as priced nor as rejected, so a later strict "
                         "run still meets it. Every finding is reported at the "
                         "end and the step exits 1.")
    args = ap.parse_args()

    key = os.environ.get(bp.KEY_ENV, "").strip()
    if not key:
        print(f"ERROR: {bp.KEY_ENV} is unset or empty.\n"
              f"       Set it in .env; see .env.example for where to read it from.",
              file=sys.stderr)
        return 1
    passage_date = os.environ.get(bp.DATE_ENV, "").strip()
    if not passage_date:
        print(f"ERROR: {bp.DATE_ENV} is unset or empty.\n"
              f"       Set it in .env; see .env.example for what the value means.",
              file=sys.stderr)
        return 1

    try:
        ov = overrides.load(args.overrides)
    except overrides.OverrideError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        traversable, resolve, position = load_inventory(args.booths)
        gares = bp.load_gares(args.gares)
        names = load_gare_names(args.gares)
        booths, done_routes = load_priced(args.out)
        sources = endpoints(booths, gares, position, SOURCE_TYPES, "source")
        targets = endpoints(booths, gares, position, TARGET_TYPES, "target")
        two_way = {g for g, r in booths.items() if r["type"] == BIDIRECTIONAL}
        inside, barriers = load_sides(args.sides, two_way)
    except Abort as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # A price recorded before the side rule cannot be checked against it: the
    # amount survives, the journey that produced it does not. So the ones the
    # rule can have affected are discarded and asked again.
    if args.drop_two_way:
        codes = {gares[g] for g in two_way if g in gares}
        gone = 0
        for group, record in booths.items():
            prices = record.get("prices") or {}
            if not prices:
                continue
            if group in two_way:
                gone += len(prices)
                record.pop("prices")
                continue
            keep = {c: v for c, v in prices.items() if c not in codes}
            gone += len(prices) - len(keep)
            if keep:
                record["prices"] = keep
            else:
                record.pop("prices")
        bp.write_state(args.out, booths, done_routes)
        left = sum(len(r.get("prices") or {}) for r in booths.values())
        print(f"==> discarded {gone} price(s) with a two-way booth at either"
              f" end; {left} remain")
        return 0

    try:
        rejections = Rejections(args.rejected)
    except Abort as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    rejected = rejections.load()

    print(f"==> {len(sources)} source booth(s), {len(targets)} target booth(s),"
          f" {len(traversable)} blocker node(s)")
    print(f"    {len(set(gares[t] for t in targets))} target gare(s),"
          f" {sum(len(r.get('prices') or {}) for r in booths.values())} price(s)"
          f" already known, {len(rejected)} pair(s) already rejected,"
          f" {len(ov.prohibited_gare_pairs)} gare pair(s) prohibited")
    print(f"    {len(inside)} two-way booth(s) with a toll side,"
          f" {len(barriers)} barrier(s) excluded from both ends")

    plan = {src: outstanding_for(src, targets, gares, booths, rejected,
                                 ov.prohibited_gare_pairs, barriers)
            for src in sources}
    plan = {src: rest for src, rest in plan.items() if rest}
    grid = sum(len(rest) for rest in plan.values())
    print(f"    {len(plan)} source(s) outstanding, {grid} pair(s) to route")
    print(f"    passage date {passage_date}, vehicle category"
          f" {bp.VEHICLE_CATEGORY}, payment option {bp.PAYMENT_OPTION}")

    if not grid:
        print("    nothing outstanding")
        rejections.close()
        return 0

    router = Router(args.osrm)
    router.wait_ready()
    client = bp.Rates(key, passage_date)

    order = sorted(plan)
    if args.limit is not None:
        order = order[:args.limit]

    routed = blocked = priced = 0
    by_reason = collections.Counter()
    unreachable, violations = [], []
    started = time.monotonic()
    since_flush = 0
    status = 0

    try:
        for n, src in enumerate(order, 1):
            src_code = gares[src]
            answers = router.route_many(
                position[src], [(tgt, position[tgt]) for tgt in plan[src]])
            routed += len(plan[src])

            rejects, clean, problems = judge_source(
                src, plan[src], answers, gares, traversable, resolve, inside)
            for tgt, reason, blocker, metres in rejects:
                rejections.add(src, tgt, gares[tgt], reason, blocker, metres)
                rejected.add((src, tgt))
                blocked += 1
                by_reason[reason] += 1
            for tgt, kind, metres, message in problems:
                if not args.survey:
                    raise stop(kind, message)
                violations.append((kind, src, tgt, metres, message))

            for code, (tgt, metres) in sorted(clean.items(),
                                              key=lambda kv: kv[1][1]):
                try:
                    price_pair(client, booths, src, src_code, tgt, code)
                except Abort as exc:
                    # A kind is what the step anticipated. Anything without one
                    # -- the service failing every retry -- is not a finding
                    # about tolls, and surveying past it would spend hours
                    # collecting the same transport failure.
                    if not args.survey or not hasattr(exc, "kind"):
                        raise
                    violations.append((exc.kind, src, tgt, round(metres),
                                       str(exc)))
                    continue
                priced += 1
                since_flush += 1
                if since_flush >= FLUSH_EVERY:
                    bp.write_state(args.out, booths, done_routes)
                    since_flush = 0

            if not clean and plan[src]:
                unreachable.append(src)
            if n % PROGRESS_EVERY == 0 or n == len(order):
                elapsed = time.monotonic() - started
                print(f"    {n}/{len(order)} sources, {routed} routed,"
                      f" {blocked} rejected, {priced} priced,"
                      f" {len(violations)} to report,"
                      f" {client.requests_made} requests,"
                      f" {elapsed / 60:.1f} min")
    except Abort as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        status = 1
    finally:
        # Written whatever happened, including on a stop: the prices banked
        # before it are true, and the pair that stopped the run is in neither
        # output, so the next run meets it again.
        bp.write_state(args.out, booths, done_routes)
        rejections.close()

    known = sum(len(r.get("prices") or {}) for r in booths.values())
    print(f"==> {routed} pair(s) routed: {blocked} rejected"
          f" ({by_reason[BY_BOOTH]} by a booth in the way,"
          f" {by_reason[WRONG_SIDE]} by a wrong side), {priced} priced")
    print(f"    {known} enter/exit price(s) in the file,"
          f" {client.requests_made} rate request(s),"
          f" {router.routes_made} route(s),"
          f" {(time.monotonic() - started) / 60:.1f} min")

    if unreachable:
        print(f"\n    {len(unreachable)} source booth(s) reached no target"
              f" at all this run:")
        for line in bp.table(
                ("booth", "gare", "targets tried"),
                [(str(src), gares[src], str(len(plan[src])))
                 for src in unreachable], right=(2,)):
            print(line)

    if violations:
        kinds = collections.Counter(v[0] for v in violations)
        print(f"\n    {len(violations)} pair(s) would have stopped a strict run:"
              f" {', '.join(f'{n} {k}' for k, n in sorted(kinds.items()))}")
        print(f"    None is recorded, in either output, so a later run meets"
              f" every one of them again.")
        for line in survey_report(violations, gares, names, position):
            print(line)
        # Survey runs succeed at surveying and fail at pricing. Exiting 0 would
        # let `make all` report a clean pipeline over a file with known holes.
        status = 1

    return status


if __name__ == "__main__":
    sys.exit(main())
