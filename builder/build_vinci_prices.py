#!/usr/bin/env python3
"""Step 6 -- price the booth inventory from the operator's rate service.

A gare code says which plaza a booth is; it does not say what it charges. The
Ulys rate service takes a list of gare passages and answers with what that
journey costs: one amount for a barrier passed in open flow, and one amount per
entrance/exit pair for a closed section. Submitting the gares of each route in
the route set therefore prices the inventory with no routing work at all.

Everything the requests need is already committed. `data/route_set.yaml` gives
the booths of each route in the order they are driven, and
`data/vinci_toll_booth.yaml` gives each one's gare. So this is the only step
that needs neither the OSRM graph nor the extract.

The inventory is read too, for one field. Most booths hold one role for good: a
barrier is always a barrier, and grouping gives an interchange's entry lanes and
exit lanes separate groups. Two kinds do not, and the inventory's `type` names
both -- a `bidirectional` booth is one group in both directions, and a `gantry`
charges per section so it starts one when another follows and is a charge of its
own when none does. Those keep the inventory's word for what they are and carry
the charges of every role they were seen in.

Passage order is load-bearing. The service pairs an entrance with the exit that
follows it in the submitted list, and every passage carries the same date, so
the order is the only thing that says which gare closed which ticket.

Answers are attributed back by walking a cursor over the submitted passages in
step with the returned items -- one passage for an item with an entrance alone,
two for an item that also carries an exit. A gare code cannot do that job: a
route may drive one gare twice, leaving and rejoining the road there.

Strict where a wrong answer would look right. A returned item that does not line
up with the passages, a booth whose role or price would change, and a covered
booth with no gare and no override are all stop conditions. A booth left without
a price is not: that means the route set offered no route to ask about, which is
a gap in the route set rather than a disagreement with the operator, so it is
reported and the step succeeds.

Outputs:
    <--out>  toll_booths (group -> {type, price | prices}), routes
"""

import argparse
import collections
import decimal
import filecmp
import json
import os
import sys
import time

import requests
import yaml


class LatLon(list):
    """A [lat, lon] pair, dumped inline rather than as two block items.

    The same representer the inventory uses, so a coordinate reads the same
    wherever it appears in the pipeline's outputs.
    """


yaml.SafeDumper.add_representer(
    LatLon,
    lambda dumper, data: dumper.represent_sequence(
        "tag:yaml.org,2002:seq", data, flow_style=True),
)

import overrides

RATE_URL = "https://api-ulys.azure-api.net/tollstation/v1/rate"

# Sent by the VINCI Autoroutes route planner. The service rejects a bare request.
RATE_HEADERS = {
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

# One class and one payment option, so the output describes one tariff and needs
# no dimension for either. Category 1 is the ordinary light vehicle.
VEHICLE_CATEGORY = 1
PAYMENT_OPTION = 2

MIN_REQUEST_INTERVAL_S = 1.0
MAX_ATTEMPTS = 5
KEY_ENV = "ULYS_SUBSCRIPTION_KEY"
DATE_ENV = "ULYS_PASSAGE_DATE"
PROGRESS_EVERY = 25

PASSTHROUGH, ENTER, EXIT = "passthrough", "enter", "exit"

# Two kinds of booth hold no single role, and the inventory names both.
#
# A `bidirectional` booth is one group in both directions -- grouping separates
# opposite directions by way of one-way restrictions, and a two-way lane has
# none. It is an entrance to a journey driven one way and an exit to the same
# journey driven the other.
#
# A `gantry` is a free-flow point charging per section travelled. It starts a
# section when another gantry follows on the same journey, and is a charge of
# its own when none does -- so the same gantry is an entrance on one route and a
# standalone charge on the next.
#
# Either way the role belongs to the journey, not to the booth, so the entry
# keeps the inventory's own word for what the booth is and carries the charges
# of every role it was seen in.
BIDIRECTIONAL, GANTRY = "bidirectional", "gantry"
ROLE_FREE = (BIDIRECTIONAL, GANTRY)
TYPES = (PASSTHROUGH, ENTER, EXIT, *ROLE_FREE)

# The two that make a route unaskable, defined beside the other override values
# because the route search reads them too: it will not select a route that
# crosses one, so the guard below should never fire. It stays as the check that
# the two steps agree.
BLOCKING_ABSENT = overrides.BLOCKING

CENTS = decimal.Decimal(100)


class Abort(Exception):
    """A response that does not line up, or a booth that changed. Never guessed past."""


# --------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------

def to_cents(value, where):
    """Whole cents from a decimal amount.

    Amounts are compared, and binary floating point would make 6.80 differ from
    itself for reasons that have nothing to do with tolls.
    """
    try:
        amount = decimal.Decimal(str(value))
    except (decimal.InvalidOperation, TypeError):
        raise Abort(f"{where}: {value!r} is not an amount")
    cents = amount * CENTS
    if cents != cents.to_integral_value():
        raise Abort(f"{where}: {value!r} is finer than a cent")
    return int(cents)


def to_euros(cents):
    """The number written to the file. 680 -> 6.8, never 6.800000000000001."""
    return float(decimal.Decimal(cents) / CENTS)


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------

def check_code(code, where):
    """Gare codes are five digits, leading zeros included."""
    code = str(code)
    if len(code) != 5 or not code.isdigit():
        raise Abort(f"{where}: {code!r} is not a five-digit gare code")
    return code


def split_code(code):
    """('04', '801') from '04801'. The request wants the halves, the response the whole."""
    return code[:2], code[2:]


def load_gares(path):
    """group -> gare code, from the gare mapping."""
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return {int(group): check_code(entry["id"], f"gare of booth {group}")
            for group, entry in (doc.get("toll_booths") or {}).items()}


def load_inventory_types(path):
    """Group -> the inventory's `type`, for the groups that carry one.

    A one-way lane carries none. The two that exist -- `bidirectional` and
    `gantry` -- are the two kinds of booth whose role is a property of the
    journey rather than of the booth, and they name the price file's type
    directly.
    """
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    out = {}
    for group, entry in (doc.get("toll_booths") or {}).items():
        kind = (entry or {}).get("type")
        if kind is None:
            continue
        if kind not in ROLE_FREE:
            raise Abort(f"{path}: booth {group} carries unknown type {kind!r};"
                        f" expected one of {', '.join(ROLE_FREE)}")
        out[int(group)] = kind
    return out


def load_routes(path):
    """The route set's routes, `covers` order preserved."""
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return doc.get("routes") or []


# The two fields build_toll_extent writes into this file. Named here because
# this step's loader and writer are what every other step reads and writes the
# file through, and a field they do not know about is a field the next write
# deletes. Order matters: it is the order the entry is written in.
# Each node is written with its coordinates: a node id alone cannot be routed
# to, so an extent without them is one no consumer can measure between. The
# tuple order is the order the entry is written in.
TOLL_EXTENT_KEYS = ("first_toll_node_id", "first_toll_latlon",
                    "last_toll_node_id", "last_toll_latlon")
TOLL_EXTENT_PAIRS = (("first_toll_node_id", "first_toll_latlon"),
                     ("last_toll_node_id", "last_toll_latlon"))


def to_node_id(value, where):
    """An OSM node id out of the file. A bool is an int and is never a node."""
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise Abort(f"{where}: expected a positive integer OSM node id,"
                    f" got {value!r}")
    return value


def to_latlon(value, where):
    """A [lat, lon] pair out of the file."""
    if (not isinstance(value, list) or len(value) != 2
            or any(not isinstance(v, (int, float)) or isinstance(v, bool)
                   for v in value)):
        raise Abort(f"{where}: expected a [latitude, longitude] pair,"
                    f" got {value!r}")
    lat, lon = float(value[0]), float(value[1])
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise Abort(f"{where}: {value!r} is not a point on Earth")
    return LatLon([lat, lon])


def load_state(path):
    """Resume state: booth -> record, processed pairs."""
    if not os.path.exists(path):
        return {}, []
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    booths = {}
    for group, entry in (doc.get("toll_booths") or {}).items():
        where = f"{path}: booth {group}"
        if entry.get("type") not in TYPES:
            raise Abort(f"{where}: unknown type {entry.get('type')!r};"
                        f" expected one of {', '.join(TYPES)}")
        record = {"type": entry["type"]}
        if "price" in entry:
            record["price"] = to_cents(entry["price"], where)
        # Where the tolled road begins and ends at this booth. Produced by
        # build_toll_extent, not by this step, and carried through untouched --
        # this step and the direct pricing step both rewrite the whole file, so
        # a field either loader dropped would be lost on the next write.
        for node_key, latlon_key in TOLL_EXTENT_PAIRS:
            has_node, has_latlon = node_key in entry, latlon_key in entry
            if has_node != has_latlon:
                missing = latlon_key if has_node else node_key
                raise Abort(
                    f"{where}: carries {node_key if has_node else latlon_key}"
                    f" without {missing}.\n"
                    f"       An extent is a node and its coordinates together:"
                    f" the id names it and the point is what can be routed to.")
            if has_node:
                record[node_key] = to_node_id(entry[node_key],
                                              f"{where}: {node_key}")
                record[latlon_key] = to_latlon(entry[latlon_key],
                                               f"{where}: {latlon_key}")
        if "prices" in entry:
            record["prices"] = {
                check_code(code, where): to_cents(amount, f"{where} -> {code}")
                for code, amount in (entry["prices"] or {}).items()}
        booths[int(group)] = record
    done = [(r["from"], r["to"]) for r in (doc.get("routes") or [])]
    return booths, done


def write_state(path, booths, done):
    """Ascending group ids, ascending gare codes, so a rerun that learns nothing diffs empty."""
    out = {}
    for group in sorted(booths):
        record = booths[group]
        entry = {"type": record["type"]}
        if "price" in record:
            entry["price"] = to_euros(record["price"])
        for key in TOLL_EXTENT_KEYS:
            if key in record:
                entry[key] = record[key]
        if "prices" in record:
            entry["prices"] = {code: to_euros(record["prices"][code])
                               for code in sorted(record["prices"])}
        out[group] = entry
    doc = {"toll_booths": out,
           "routes": [{"from": a, "to": b} for a, b in sorted(done)]}
    # The temporary name carries the pid. Two runs of a resumable step against
    # one file is an operator error rather than a supported mode, but with a
    # fixed name it fails by *losing* the file: both write `.part`, one renames
    # it, and the other's rename finds nothing there. A per-process name makes
    # the loser overwrite the winner instead, which is recoverable.
    tmp = f"{path}.{os.getpid()}.part"
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            yaml.safe_dump(doc, fh, default_flow_style=False, sort_keys=False,
                           width=100, allow_unicode=True)
        # A run that learns nothing leaves the file alone, modification time
        # included. The segment weights are keyed to this file's timestamp, so
        # restamping it with identical bytes would order half an hour of graph
        # work that changes nothing -- and every `make all` would order it.
        if os.path.exists(path) and filecmp.cmp(tmp, path, shallow=False):
            os.unlink(tmp)
            return
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------
# Service
# --------------------------------------------------------------------------

class Rates:
    """Ulys rate client: one request per second, five attempts, one thread."""

    def __init__(self, key, passage_date):
        self.session = requests.Session()
        self.headers = dict(RATE_HEADERS, **{"Ocp-Apim-Subscription-Key": key})
        self.passage_date = passage_date
        self._last = 0.0
        self.requests_made = 0

    def _throttle(self):
        wait = MIN_REQUEST_INTERVAL_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)

    def body(self, codes):
        passages = []
        for code in codes:
            operator, toll = split_code(code)
            passages.append({"toll": {"operatorId": operator, "tollId": toll},
                             "passageDate": self.passage_date})
        return {"vehicleCategory": VEHICLE_CATEGORY,
                "paymentOption": PAYMENT_OPTION,
                "tollPassages": passages}

    def rate(self, codes):
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
                    RATE_URL, headers=self.headers,
                    data=json.dumps(self.body(codes)).encode("utf-8"),
                    timeout=180,
                )
                resp.raise_for_status()
                # Decimal, not float: these numbers are compared.
                payload = resp.json(parse_float=decimal.Decimal)
            except Exception as exc:  # noqa: BLE001 - retry every transport failure
                last_error = exc
                continue
            if not isinstance(payload, list):
                last_error = f"expected a list, got {type(payload).__name__}"
                continue
            return payload
        raise Abort(f"rate service failed after {MAX_ATTEMPTS} attempts: {last_error}")


# --------------------------------------------------------------------------
# Requests and answers
# --------------------------------------------------------------------------

def passages_for(route, gares, ov):
    """[(group, gare code)] in driven order, or None when the route is unaskable.

    A booth the operator does not carry has no passage to send. Which of the two
    that means depends on how a route meets it, and the override file is what
    says: half a pair makes the whole route unaskable, a barrier drops out.
    """
    passages = []
    for cover in route["covers"]:
        group = cover["node_id"]
        if group in gares:
            passages.append((group, gares[group]))
            continue
        absent = ov.absent.get(group)
        if absent in BLOCKING_ABSENT:
            return None, group
        if absent is not None or group in ov.ignored:
            continue
        raise Abort(
            f"booth {group} is covered by route {route['from']} -> {route['to']}"
            f" and has neither a gare nor an override saying why\n"
            f"       Run build_vinci_toll_booths, or regenerate the route set if"
            f" an override has since removed the booth.")
    return passages, None


def code_of(item, field, route):
    toll = item.get(field)
    if not isinstance(toll, dict) or "code" not in toll:
        raise Abort(f"rate item carries no {field}.code\n"
                    f"       route: {route['from']} -> {route['to']}\n"
                    f"       item:  {item!r}")
    # `code` and not operatorId/tollId: the response reports those as integers
    # and has already dropped the leading zeros the request and the mapping use.
    return check_code(toll["code"], f"{field} of a rate item")


def describe(passages, start=0):
    return ", ".join(f"{code}({group})" for group, code in passages[start:]) or "none"


def describe_comments(items):
    """What the service said about an answer it gave no amount for."""
    said = [c for item in items for c in (item.get("comments") or [])]
    return f"service said: {'; '.join(said)}" if said else "service gave no reason"


def attribute(items, passages, route):
    """(charges, unpriced passages) for one route.

    The cursor walks the submitted passages in step with the returned items. It
    is what lets one gare be driven twice on one route without either passage
    being mistaken for the other.
    """
    charges, unpriced, cursor = [], [], 0
    for item in items:
        entrance = code_of(item, "entranceToll", route)
        start = cursor
        while cursor < len(passages) and passages[cursor][1] != entrance:
            cursor += 1
        if cursor >= len(passages):
            raise Abort(
                f"rate item names an entrance no remaining passage carries\n"
                f"       route:     {route['from']} -> {route['to']}\n"
                f"       entrance:  {entrance}\n"
                f"       remaining: {describe(passages, start)}")
        # Passages the cursor stepped over were sent and not priced.
        unpriced.extend(passages[start:cursor])
        consumed = [passages[cursor]]
        cursor += 1

        exit_passage = None
        if item.get("exitToll") is not None:
            exit_code = code_of(item, "exitToll", route)
            if cursor >= len(passages) or passages[cursor][1] != exit_code:
                following = (describe(passages, cursor) if cursor < len(passages)
                             else "none")
                raise Abort(
                    f"rate item's exit does not follow its entrance\n"
                    f"       route:     {route['from']} -> {route['to']}\n"
                    f"       entrance:  {entrance}\n"
                    f"       exit:      {exit_code}\n"
                    f"       remaining: {following}")
            exit_passage = passages[cursor]
            consumed.append(exit_passage)
            cursor += 1

        # An item with no amount is the service saying it has no tariff for that
        # passage -- `comments` carries "No rate found." It answers, so it is not
        # a malformed response; there is simply nothing to record. The passages
        # it consumed are reported alongside the ones it stepped over.
        if item.get("price") is None:
            unpriced.extend(consumed)
            continue

        cents = to_cents(item["price"], f"price of {entrance} on route "
                                        f"{route['from']} -> {route['to']}")
        if exit_passage is None:
            charges.append((PASSTHROUGH, consumed[0][0], None, cents))
        else:
            charges.append((ENTER, consumed[0][0],
                            (exit_passage[0], exit_passage[1]), cents))

    unpriced.extend(passages[cursor:])
    return charges, unpriced


def apply_charges(charges, booths, stated_types, route):
    """Fold one route's charges in, or raise having changed nothing.

    Every check runs against the committed state plus what this route has staged
    so far, and the staged values are written only once all of them pass. So an
    abort leaves `booths` exactly as it found it, which is what lets --survey
    skip a route and carry on with a state that is still true.
    """
    types, open_flow, pairs = {}, {}, {}

    def role(group, kind):
        """The role this group holds, checked against the one it already has.

        Two kinds of group hold a role a route cannot overrule, and
        `stated_types` carries both.

        The inventory names the first: a `bidirectional` or `gantry` group holds
        no role of its own -- it is an entrance one way and an exit the other, or
        a section start on one journey and a charge of its own on the next -- so
        a role that changes says nothing is wrong.

        The override file names the second: a booth at a border, whose role is
        stated by hand because no route reaches it to demonstrate one. That role
        is fixed rather than journey-dependent, and it wins for a different
        reason -- a route that met such a booth met it in the one sense it has.

        For a plain one-way lane a role that changes says grouping merged an
        entry side with an exit side, which is worth stopping for.
        """
        if group in stated_types:
            kind = stated_types[group]
        current = types.get(group) or (booths.get(group) or {}).get("type")
        if current is None:
            types[group] = kind
        elif current != kind:
            raise Abort(
                f"booth {group} is recorded as {current} and this route"
                f" reports {kind}\n"
                f"       route: {route['from']} -> {route['to']}")

    for kind, entrance, exit_pair, cents in charges:
        if kind is PASSTHROUGH:
            role(entrance, PASSTHROUGH)
            recorded = (booths.get(entrance) or {}).get(
                "price", open_flow.get(entrance))
            if recorded is not None and recorded != cents:
                raise Abort(
                    f"booth {entrance} is recorded at {to_euros(recorded)} and"
                    f" this route reports {to_euros(cents)}\n"
                    f"       route: {route['from']} -> {route['to']}")
            open_flow[entrance] = cents
            continue

        exit_group, exit_code = exit_pair
        role(entrance, ENTER)
        role(exit_group, EXIT)
        key = (entrance, exit_code)
        recorded = ((booths.get(entrance) or {}).get("prices") or {}).get(
            exit_code, pairs.get(key))
        if recorded is not None and recorded != cents:
            raise Abort(
                f"booth {entrance} -> gare {exit_code} is recorded at"
                f" {to_euros(recorded)} and this route reports"
                f" {to_euros(cents)}\n"
                f"       route: {route['from']} -> {route['to']}")
        pairs[key] = cents

    # Every check passed, so the route is recorded in one go.
    for group, kind in types.items():
        booths.setdefault(group, {"type": kind})
    for group, cents in open_flow.items():
        booths[group]["price"] = cents
    for (entrance, exit_code), cents in pairs.items():
        booths[entrance].setdefault("prices", {})[exit_code] = cents


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def table(head, rows, right=()):
    """The bordered table the rest of the pipeline prints its reports as."""
    if not rows:
        return []
    width = [max(len(r[i]) for r in (*rows, head)) for i in range(len(head))]

    def rule(left, mid, sep):
        return "  " + left + mid.join("─" * (w + 2) for w in width) + sep

    def row(cells):
        return "  │ " + " │ ".join(
            cell.rjust(width[i]) if i in right else cell.ljust(width[i])
            for i, cell in enumerate(cells)) + " │"

    return [rule("┌", "┬", "┐"), row(head),
            rule("├", "┼", "┤"),
            *(row(r) for r in rows), rule("└", "┴", "┘")]


def unpriced_report(routes, booths, gares, ov, skipped, done_pairs, crossings):
    """Every covered booth with no entry, and which of the four reasons it is.

    Each reason wants a different remedy: an override for a booth the operator
    does not carry, a route for one the skipped routes stranded, another run for
    one whose routes are still outstanding, and a look at the service for one it
    was asked about and did not price.
    """
    covered = {c["node_id"] for r in routes for c in r["covers"]}
    askable = {c["node_id"] for r in routes
               if (r["from"], r["to"]) not in skipped for c in r["covers"]}
    asked = {c["node_id"] for r in routes
             if (r["from"], r["to"]) in done_pairs for c in r["covers"]}
    rows = []
    for group in sorted(covered - set(booths) - ov.ignored):
        if group not in gares:
            reason = f"no gare ({ov.absent.get(group, 'and no override')})"
        elif group not in askable:
            reason = "covered only by skipped routes"
        elif group not in asked:
            reason = "its routes are still outstanding"
        else:
            reason = "asked about, never priced"
        rows.append((str(group), gares.get(group, "-"), str(crossings[group]),
                     reason))
    return rows


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--route-set", required=True, help="route set YAML")
    ap.add_argument("--booths", required=True,
                    help="booth inventory YAML, read for the booth `type`")
    ap.add_argument("--gares", required=True, help="gare mapping YAML from step 5")
    ap.add_argument("--overrides", required=True, help="hand-maintained booth overrides YAML")
    ap.add_argument("--out", required=True, help="price file YAML")
    ap.add_argument("--limit", type=int, metavar="N",
                    help="diagnostic: stop after N outstanding routes")
    ap.add_argument("--survey", metavar="PATH",
                    help="diagnostic: on a stop condition, record it to PATH, skip "
                         "that route, and keep going. The skipped route is not "
                         "marked processed and none of its charges are recorded, "
                         "so a later strict run still meets it.")
    args = ap.parse_args()

    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        print(f"ERROR: {KEY_ENV} is unset or empty.\n"
              f"       Set it in .env; see .env.example for where to read it from.",
              file=sys.stderr)
        return 1
    passage_date = os.environ.get(DATE_ENV, "").strip()
    if not passage_date:
        print(f"ERROR: {DATE_ENV} is unset or empty.\n"
              f"       Set it in .env; see .env.example for what the value means.",
              file=sys.stderr)
        return 1

    try:
        ov = overrides.load(args.overrides)
    except overrides.OverrideError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    routes = load_routes(args.route_set)
    inventory_types = load_inventory_types(args.booths)
    # A role no route may overrule, from either file that states one. The
    # override's entries are booths at a border that no route reaches, so the
    # two sets are disjoint in practice; the inventory is listed second so that
    # a booth somehow in both keeps the derived answer rather than the stated
    # one, and the check below reports it rather than letting it pass.
    stated_types = {**ov.one_way, **inventory_types}
    both = sorted(set(ov.one_way) & set(inventory_types))
    if both:
        print(f"ERROR: {len(both)} booth(s) are typed by both"
              f" {args.booths} and {args.overrides}: {both}", file=sys.stderr)
        return 1
    try:
        gares = load_gares(args.gares)
        booths, done = load_state(args.out)
    except Abort as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    crossings = collections.Counter(c["node_id"] for r in routes for c in r["covers"])
    print(f"==> {len(routes)} routes, {len(crossings)} covered booth group(s),"
          f" {len(gares)} with a gare,"
          f" {sum(1 for g in crossings if g in inventory_types)} typed by the"
          f" inventory, {len(ov.one_way)} stated by override")
    print(f"    passage date {passage_date}, vehicle category"
          f" {VEHICLE_CATEGORY}, payment option {PAYMENT_OPTION}")

    # Which routes are askable is settled before anything is sent, so the count
    # printed below is the count that will actually be requested.
    plans, skipped = {}, {}
    try:
        for route in routes:
            passages, blocker = passages_for(route, gares, ov)
            if passages is None:
                skipped[(route["from"], route["to"])] = blocker
            else:
                plans[(route["from"], route["to"])] = passages
    except Abort as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    done_pairs = set(done)
    outstanding = [r for r in routes
                   if (r["from"], r["to"]) in plans
                   and (r["from"], r["to"]) not in done_pairs]
    if args.limit is not None:
        outstanding = outstanding[:args.limit]

    # A booth stated `passthrough` charges for itself and no route reaches it,
    # so the smallest question the service answers -- one passage, one gare --
    # is the whole question it poses. A booth stated `enter` or `exit` is not
    # asked this way: the service answers a lone passage for a closed-section
    # end too, with an amount that is not what that gare charges. 09240
    # BEAUREPAIRE is an entrance priced at 53.90 and 54.60 against its two
    # exits, and its lone-passage answer is 14.70.
    barriers = [b for b, kind in sorted(ov.one_way.items())
                if kind == PASSTHROUGH and (b, b) not in done_pairs]
    missing_gare = [b for b in barriers if b not in gares]
    if missing_gare:
        print(f"ERROR: {len(missing_gare)} booth(s) stated `type: passthrough`"
              f" have no gare: {missing_gare}\n"
              f"       Run build_vinci_toll_booths.", file=sys.stderr)
        return 1
    print(f"    {len(skipped)} route(s) not askable, {len(done_pairs)} already"
          f" processed, {len(outstanding)} route(s) and {len(barriers)} stated"
          f" barrier(s) outstanding")

    unpriced_by_route, commented, violations = [], [], []
    started = time.monotonic()
    client = None

    if outstanding or barriers:
        client = Rates(key, passage_date)
        try:
            for n, route in enumerate(outstanding, 1):
                pair = (route["from"], route["to"])
                passages = plans[pair]
                items = client.rate([code for _, code in passages])
                try:
                    charges, unpriced = attribute(items, passages, route)
                    apply_charges(charges, booths, stated_types, route)
                except Abort as exc:
                    if not args.survey:
                        raise
                    violations.append({"from": route["from"], "to": route["to"],
                                       "report": str(exc)})
                    print(f"    !! route {route['from']} -> {route['to']} would"
                          f" stop the run ({len(violations)} so far)")
                    continue
                if unpriced:
                    unpriced_by_route.append((pair, unpriced))
                for item in items:
                    if item.get("comments"):
                        commented.append((pair, item))
                # Recorded only now: the route is processed in full, so an
                # interruption costs at most this one route.
                done.append(pair)
                write_state(args.out, booths, done)
                if n % PROGRESS_EVERY == 0 or n == len(outstanding):
                    elapsed = time.monotonic() - started
                    print(f"    {n}/{len(outstanding)} routes,"
                          f" {len(booths)} booths priced,"
                          f" {client.requests_made} requests,"
                          f" {elapsed / 60:.1f} min")

            for booth in barriers:
                passages = [(booth, gares[booth])]
                items = client.rate([gares[booth]])
                # The synthetic route names the booth at both ends, which no
                # real route can: its endpoints are two distinct place nodes.
                # It is what `attribute` and `apply_charges` report against.
                route = {"from": booth, "to": booth,
                         "covers": [{"node_id": booth}]}
                try:
                    if not items:
                        raise Abort(
                            f"the rate service returned no item for gare"
                            f" {gares[booth]} alone, which booth {booth} is"
                            f" stated to be a barrier at")
                    charges, unpriced = attribute(items, passages, route)
                    if not charges:
                        # `No rate found.` for a lone passage means the service
                        # prices this gare only against a partner, so it is one
                        # end of a closed section and not a barrier at all. The
                        # converse is not inferable: a lone passage answered
                        # with a price does not make a gare a barrier, as
                        # 09240 BEAUREPAIRE shows. Only whether any partner is
                        # reachable without crossing another booth tells the two
                        # apart, and that is the router's question, not this
                        # step's.
                        raise Abort(
                            f"booth {booth} is stated `type: passthrough` but"
                            f" the operator will not price gare"
                            f" {gares[booth]} on its own\n"
                            f"       {describe_comments(items)}\n"
                            f"       That answer means the gare is one end of a"
                            f" closed section. State the booth\n"
                            f"       `enter` or `exit` in {args.overrides}"
                            f" instead.")
                    apply_charges(charges, booths, stated_types, route)
                except Abort as exc:
                    if not args.survey:
                        raise
                    violations.append({"from": booth, "to": booth,
                                       "report": str(exc)})
                    print(f"    !! stated barrier {booth} would stop the run"
                          f" ({len(violations)} so far)")
                    continue
                for item in items:
                    if item.get("comments"):
                        commented.append(((booth, booth), item))
                # Recorded only now, for the same reason a route is.
                done.append((booth, booth))
                write_state(args.out, booths, done)
                print(f"    stated barrier {booth} -> gare {gares[booth]}"
                      f" at {to_euros(booths[booth]['price'])}")
        except Abort as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1
    else:
        print("    no routes and no stated barriers to query")

    # A price the operator does not publish but a human has measured. Written
    # here so a consumer reads one file rather than two. A booth with no stated
    # price gets no entry -- there is nothing to say about it.
    stated = 0
    for group, amount in sorted(ov.price.items()):
        if group not in crossings:
            continue
        kind = inventory_types.get(group, PASSTHROUGH)
        booths.setdefault(group, {"type": kind})["price"] = to_cents(
            amount, f"stated price of booth {group}")
        stated += 1

    # A booth stated `enter` or `exit` carries its role and nothing else. The
    # tariff depends on the partner at the other end of the ticket, and the
    # direct pricing step is what supplies it -- but only for a booth already in
    # the price file, since that is where it takes its sources and targets from.
    # So recording the role is what puts the booth into the grid at all.
    #
    # A booth stated `passthrough` is not seeded here. Its entry is its price,
    # and that comes from the answer to its own request; writing a bare entry
    # would give it a type with no tariff and satisfy the check below with a
    # record that says nothing.
    for group, kind in sorted(ov.one_way.items()):
        # `!=`, not `is not`: this string was parsed from YAML and is not the
        # interned module constant, however equal it reads.
        if kind != PASSTHROUGH:
            booths.setdefault(group, {"type": kind})
    write_state(args.out, booths, done)

    kinds = collections.Counter(r["type"] for r in booths.values())
    pairs = sum(len(r.get("prices") or {}) for r in booths.values())
    print(f"==> {len(booths)} booth group(s) priced:"
          f" {kinds[PASSTHROUGH]} passthrough, {kinds[ENTER]} enter,"
          f" {kinds[EXIT]} exit, {kinds[BIDIRECTIONAL]} bidirectional,"
          f" {kinds[GANTRY]} gantry; {pairs} pair price(s)")
    print(f"    {stated} price(s) stated by hand")
    print(f"    {len(done)} route(s) processed"
          + (f", {client.requests_made} requests" if client else "")
          + f", {(time.monotonic() - started) / 60:.1f} min")

    if skipped:
        print(f"\n    {len(skipped)} route(s) not submitted: a booth they cross"
              f" is half of a closed section the operator does not carry, and"
              f" dropping one passage would mis-pair the rest.")
        for line in table(
                ("from", "to", "booth", "override"),
                [(str(a), str(b), str(g), ov.absent[g])
                 for (a, b), g in sorted(skipped.items())]):
            print(line)

    if unpriced_by_route:
        total = sum(len(u) for _, u in unpriced_by_route)
        print(f"\n    {total} passage(s) on {len(unpriced_by_route)} route(s)"
              f" were submitted and not priced:")
        for line in table(
                ("from", "to", "passages"),
                [(str(a), str(b), describe(u))
                 for (a, b), u in unpriced_by_route]):
            print(line)

    if commented:
        print(f"\n    {len(commented)} rate item(s) carried comments:")
        for (a, b), item in commented:
            print(f"      {a} -> {b}: {item.get('comments')!r}")

    if args.survey:
        with open(args.survey, "w", encoding="utf-8") as fh:
            json.dump(violations, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"\n    survey: {len(violations)} route(s) would have stopped the"
              f" run -- see {args.survey}")

    rows = unpriced_report(routes, booths, gares, ov, set(skipped), set(done),
                           crossings)
    if rows:
        print(f"\n    {len(rows)} covered booth group(s) have no price:")
        for line in table(("booth", "gare", "routes", "reason"), rows, right=(2,)):
            print(line)

    # A booth stated by hand has to end up recorded, unlike a covered booth that
    # merely has no price. A covered booth without one is a gap in the route set,
    # which is where it is fixed; a stated booth is settled by the override file
    # and, for a barrier, by one direct question, so nothing stands between the
    # statement and the record. Runs on every invocation, including one with
    # nothing outstanding.
    surveyed = {(v["from"], v["to"]) for v in violations}
    unrecorded = []
    for booth, kind in sorted(ov.one_way.items()):
        if (booth, booth) in surveyed:
            continue
        entry = booths.get(booth)
        if entry is None:
            unrecorded.append((booth, kind, "has no entry"))
        elif kind == PASSTHROUGH and "price" not in entry:
            # A barrier's entry is its price. One without says the request was
            # never made, or its answer never applied -- and a type on its own
            # would publish a booth the operator charges for at no charge.
            unrecorded.append((booth, kind, "carries no price"))
    if unrecorded:
        print(f"\nERROR: {len(unrecorded)} booth(s) stated by override are not"
              f" recorded.", file=sys.stderr)
        print(f"       Delete their entries from {args.out} and run again, so"
              f" the request is repeated.\n", file=sys.stderr)
        for booth, kind, why in unrecorded:
            print(f"       booth {booth} stated `type: {kind}`, gare"
                  f" {gares.get(booth, '-')}, {why}"
                  f"  https://www.openstreetmap.org/node/{booth}",
                  file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
