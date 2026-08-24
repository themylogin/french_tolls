## Context

See proposal.md — Why.

The inputs already exist. `data/route_set.yaml` holds 781 routes over 1287 booth groups. `data/vinci_toll_booth.yaml` maps 1275 of those groups to an operator gare code, and `map-booths-to-vinci-gares` established that mapping by matching every placemark the operator reported on each route to a group in that route's `covers`. The 12 groups with no gare are the ones the override file marks `absent_*`.

The Ulys `tollstation/v1/rate` service supplies the missing piece. It takes a list of gare passages and returns what the journey costs. It is the service the VINCI Autoroutes route planner calls, reached with the same subscription key `build_vinci_toll_booths` already uses.

The whole design follows from one measured response. Nine passages submitted:

```
801  358  355  456  459  401  407  05055  05601
```

Five items returned:

| item | entranceToll | exitToll | price | passages consumed |
|---|---|---|---|---|
| 1 | `04801` | — | 7.80 | 1 |
| 2 | `04358` | `04355` | 6.80 | 2 |
| 3 | `04456` | `04459` | 3.90 | 2 |
| 4 | `04401` | `04407` | 15.90 | 2 |
| 5 | `05055` | `05601` | 21.80 | 2 |

Nine sent, nine consumed, strictly in order. Everything below rests on that.

## Goals / Non-Goals

**Goals:**

- Classify every reachable booth group as `passthrough`, `enter`, or `exit`, and record what the operator charges for it.
- Attribute every returned amount to the booth group that earned it, with no ambiguity a gare code alone could create.
- Make the step resumable at route granularity, and free of the routing and placemark services entirely.

**Non-Goals:**

- A complete price matrix. The route set covers every booth; it does not cover every entrance/exit pair. The output is sparse by construction and that is accepted.
- Vehicle classes other than category 1, and payment options other than 2.
- Improving coverage. The booths left unpriced stay unpriced and are reported.
- Correcting the route set or the inventory.

## Decisions

### Key the file by OSM booth group, not by gare code

A gare code has no direction. 669 gares span 1275 groups: 94 gares hold one group, 556 hold two, 19 hold three or more. The two-group case is one plaza with an entry side and an exit side, or one barrier with two carriageways. Only 4 gare names of 669 contain `SORTIE` and 2 contain `ENTREE` — the operator names the plaza, not the role.

So a gare is an entrance for one direction and an exit for the other, and a file keyed by gare code could not hold `type` at all. The first southbound route would contradict the first northbound one.

A booth group does have a direction. `booth_groups.py` groups two booths only when they share a common predecessor **P** and a common successor **S**. The exit lanes of an interchange run motorway → local road; the entry lanes run local road → motorway. They share neither, so they never group. A group is therefore one role in one direction, and `type` is a stable property of it.

`prices` stays keyed by the exit's **gare code** rather than by its group. At lookup time the consumer knows which exit group it drives and can resolve it to a code; carrying the code is the smaller key and matches what the service returns.

Alternatives considered:

- **Key by gare code, drop `type`, record a bare pair matrix.** Loses the passthrough/closed distinction that a consumer needs to know whether a lone booth is chargeable.
- **Key by gare code and make `type` a per-direction sub-key.** Invents a direction the operator does not publish.

### A two-way booth is one group in two directions, and gets its own type

The argument above holds for a group whose lanes are one-way. It does not hold for all of them, and the full run found that out at route 87 of 769:

```
ERROR: booth 289635259 is recorded as enter and this route reports exit
       route: 432499741 -> 8852061292
```

`booth_groups.py` never groups a booth on a two-way through road: the (P, S) rule separates opposite directions by way of one-way restrictions, and a two-way lane has none. So one group serves both directions of travel, and which role it plays depends on which way the car came:

```
   approach 1917665765 ──▶ [ 289635259 ] ──▶   an ENTRANCE this way
   approach 1393570707 ──▶ [ 289635259 ] ──▶   an EXIT this way
```

This is the same fact `route_set.yaml` already carries. A `covers` entry for such a booth records `prev_node_id`, and `coverage_targets` makes each one **two** targets, because passing the gare northbound does not pay the southbound toll.

| | count |
|---|---|
| covered booth groups | 1287 |
| of them `bidirectional` | 48 |
| met from both approaches by the route set | 47 |
| met from one approach only | 1 |

Of the 286 booths priced before the stop, 10 were two-way: 6 reported as an exit, 3 as an entrance, 1 as a barrier.

**Such a group is recorded as `bidirectional`, whatever role a route reports.** The entry carries `prices` for the exits a route reached from it and `price` for a pass in open flow, and may carry both.

The alternative is to key those entries on the coverage target `(node_id, prev_node_id)` rather than the group. Rejected: it buys nothing. An exit records no amount at all, so the only per-approach content is `prices`, and an exit gare in `prices` already says which approach the car used — only one of the two can reach it. The cost is a second key shape in the file and a special case in every consumer.

The contradiction check narrows accordingly: a role that changes is a stop condition for a one-way group only. For a one-way group it still means what it meant — that grouping merged an entry side with an exit side — and that is worth stopping for.

### Attribute by a cursor over the submitted passages, not by gare code

A gare code does not identify a group even within one route: a route can drive one gare twice, once as an exit and once as an entrance. `04210 ORANGE` does exactly that in the current route set, and the override file lists it under `duplicate_gares` because the road that would let a driver carry on is under construction.

The cursor walks the submitted passages in step with the returned items — one passage for an item with `entranceToll` alone, two for an item with `exitToll`. It cannot confuse a gare with itself, and it stops the run when the response does not line up.

Alternatives considered:

- **A gare → group dictionary per route.** Ambiguous for `04210`, and silently wrong rather than loudly wrong when a response drops an item.
- **Match by name.** The gare mapping change already rejected names on evidence.

### `code`, not `operatorId` and `tollId`

The response reports `operatorId: 5, tollId: 55, code: "05055"`. The first two are integers and have lost their leading zeros; the request, `data/vinci_toll_booth.yaml`, and `data/vinci_price.yaml` all use the five-character padded form. Reading `code` avoids reconstructing what the response already states.

The **request** still needs the split form, and the sample sends it as strings: `operatorId: "04"`, `tollId: "801"`. So the request splits the code at two characters and the response is read whole.

### Compare amounts in whole cents

The service returns `7.80` and `6.80`. Parsed as binary floating point and re-added, those stop comparing equal for reasons that have nothing to do with tolls, and the contradiction check would fire on a file that is perfectly consistent. Amounts are parsed as decimals and compared as integer cents.

### Skip a route only for an absent entrance or exit

A booth the override file marks `absent_*` has no gare, so its passage cannot be sent. What happens next depends on which kind it is.

```
   absent entrance:   drive   ... ──▶ [enter C] ──▶ [exit Y] ──▶ ...
                      send    ... ──▶ [       ] ──▶ [  Y   ] ──▶ ...
                      paired  ... ─────────────────────▶ Y          wrong pair, real price

   absent barrier:    drive   ... ──▶ [ pass B ] ──▶ [enter C] ──▶ [exit Y] ...
                      send    ... ──▶ [        ] ──▶ [  C   ] ──▶ [  Y  ] ...
                      paired  ...                     C ─────────────▶ Y     unaffected
```

A barrier forms its own single-passage item, so removing it disturbs nothing. An entrance or an exit is half a pair, and removing it hands the other half to the wrong partner. The service would answer, and the answer would be a real tariff for a journey nobody drove — the worst kind of wrong, because nothing in the output would look odd.

Measured on the current data:

| rule | routes skipped | groups left unpriced |
|---|---|---|
| skip for any absent booth | 38 of 781 | 47 |
| skip for `absent_enter` / `absent_exit` only | **7 of 781** | **6** |

The five booths that trigger it are `16567653` and `28128388` (Chanas), `469982848` and `14040228495` (Bernay), and `1838205657` (Hochfelden). The six groups it costs are `143224` (03070), `14790565` (04347), `130221205` (04216), `393881364` (08311), `410650377` (09138), and `720736848` (08311).

### An unpriced booth is reported, not fatal

`build_vinci_toll_booths` fails when a covered booth has no gare, and that is right: it means the inventory and the operator disagree, and each case needed a decision that the override file now records.

A missing price is a different thing. It means the route set gave no submittable route through that booth. The evidence is in the route set, the remedy is a route, and stopping the pipeline over it would block a file that is correct as far as it goes. The step reports each one with why.

### `covers` becomes traversal-ordered

The service pairs by position, so the driven order is now load-bearing. Step 4 already has it and throws it away twice:

| file:line | what it does |
|---|---|
| `builder/build_route_set.py:288` | `hits = set()` — traversal order lost |
| `builder/build_route_set.py:579` | `sorted(cov, key=target_key)` — rewritten by node id |

Three call sites consume `covers` as a set and need an unordered view kept alongside the ordered one: `:685` (`uncovered -= covered`), `:512` (`greedy_select`), `:773` (`union.update`).

**The migration costs nothing.** `load_existing` (`:607`) keeps only the `(from, to)` pairs, and `main` re-queries every existing route through `cover_many` (`:683`) precisely so `covers` stays reproducible against the inventory in hand. So `make update_route_set` rewrites all 781 routes against the local OSRM graph, with no placemark request and no new route search. The contents are unchanged, so `data/vinci_toll_booth.yaml` stays valid and step 5 is not re-run.

Alternatives considered:

- **Order at read time in step 6, by projecting each booth onto the route geometry.** Needs the OSRM graph in a step that otherwise needs nothing, and re-derives what step 4 already knew.
- **Record `StartAbscissa` from the placemark service.** Costs a second full replay of 781 placemark requests to recover information the router hands over for free.

### No routing service, no placemark service

The gares come from two committed files. The step needs the network only for the rate service. That makes it the cheapest step to re-run and the only one that works on a checkout with no OSRM graph at all.

### Politeness matches the gare mapping step

One request per second on a single thread, five attempts with exponential backoff. 781 routes less 7 skipped is 774 requests, about 13 minutes — the same shape as step 5's measured 13.1 minutes over 787 routes.

## Risks / Trade-offs

- **The response ordering is inferred from one sample.** → The cursor asserts it on every item and stops on the first mismatch. A wrong inference is loud, not silent.
- **The service may return no item for a passage it cannot price.** → The consumed-passage count is checked against the submitted count, and the difference is reported per route. Without that check a dropped item would slide the cursor and mis-attribute everything after it.
- **A booth the inventory carries and the operator does not place on a given route would mis-pair the same way an absent entrance does.** → Bounded by what step 5 established: every placemark the operator returned on each route matched a covered group, and step 5 completed with zero guardrail hits. The consumed-count check is the residual guard.
- **A pair price could depend on the path driven between two gares, not only on the pair.** → The contradiction check compares against what is already recorded, so the first disagreement stops the run and names both routes. Nothing is guessed.
- **The output is a sparse pair matrix.** → Accepted. A consumer that meets a pair the file does not carry has to ask the service; growing the matrix is a later change against a route set built for pairs rather than for booths.
- **`04210 ORANGE` is driven twice on one route and charged twice.** → Real, and whitelisted in the override file by `duplicate_gares` rather than hidden. The cursor handles it; what the service returns for it is worth reading in the first run.
- **The subscription key is a browser key and rotates.** → Unchanged from step 5. It lives in `.env` behind a guard.
- **`comments` is undocumented and empty in the one sample.** → Reported rather than discarded, so the first non-empty one is visible.

## Migration Plan

1. Change `covers` to traversal order in `builder/build_route_set.py` and run `make update_route_set`. Verify the rewritten file differs from the committed one only in the order of `covers` entries, and that `make build_vinci_toll_booths` then finds nothing outstanding.
2. Add `ULYS_PASSAGE_DATE` and its guard.
3. Add `builder/build_vinci_prices.py` and the `build_vinci_prices` step.
4. Run it, and commit `data/vinci_price.yaml`.

Rollback is deletion. The new step's output is a standalone file, and the ordering change is one commit that `make update_route_set` reverses.

### An item with no amount is an answer, not a malformed response

The `04210 ORANGE` route settled this. It submits four passages and gets two items back:

```
   sent:      04342   04210   04210   04218
   item 1:    04342 ─────▶ 04210          27.50
   item 2:                         04218   no price, comments: ["No rate found."]
   ignored:                 ^ the second 04210
```

The driver leaves the road at ORANGE, closing the ticket opened at 04342, and rejoins there. The service prices the first pair, ignores the re-entry, and reports that it has no tariff for `04218` standing alone.

So an item can arrive with `entranceToll` and no `price`. An earlier draft treated that as a malformed response and stopped the run. It is not malformed — the service answered, and `comments` says what the answer is. Such an item consumes its passages so the cursor stays in step, records nothing, and is reported with the passages it could not price.

Stopping instead would make one unpriceable gare block the whole file. Guessing a price for it would be worse.

## Open Questions

- Why the service will not price `04218` after a re-entry at `04210`. It prices `04210 -> 04218` on other routes or it does not; the per-route unpriced report says which, and either way this step records only what it was told.
- Whether the service prices every operator in the inventory. The gares span 20 operators, and the sample proves only `04` and `05`. An operator it declines shows up as an unpriced passage in the per-route report, which is the mechanism already specified.
