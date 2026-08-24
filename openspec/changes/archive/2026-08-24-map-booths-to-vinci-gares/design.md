## Context

See proposal.md — Why.

The inputs already exist. After `fix-booth-grouping-and-direction`, `data/route_set.yaml` holds 786 routes covering 1340 of 1354 coverage targets over 1303 booth groups, and its `covers` lists are reproducible against the project's own OSRM instance. `data/filtered.osm.pbf` holds every booth node with its location. The only missing piece is a link from an OSM booth group to the operator's own gare code.

The Ulys `placemark/v2/legs` service supplies that link. It takes an encoded route geometry and returns the toll gares that route passes, each carrying an operator code and a position. The service is undocumented and reached with a subscription key lifted from the VINCI Autoroutes web client.

Every quantity quoted below was measured against the live service and the current inventory, not assumed.

## Goals / Non-Goals

**Goals:**

- Resolve every reachable OSM booth group to the operator gare a route through it actually reports.
- Make the step resumable at route granularity, so an interrupted run costs no repeated requests.
- Fail loudly on any disagreement between the inventory and the service, rather than recording a guess.

**Non-Goals:**

- Tariffs, vehicle classes, or toll cost. `Targets: ["VL","PL"]` is present in the response and is not consumed.
- Any layer other than `GaresPeage`.
- Improving coverage. The thirteen uncovered targets stay uncovered and receive no entry.
- Correcting the inventory. Where grouping split one physical plaza, this step records what the service returned and does not merge.

## Decisions

### Match on coordinates, against this route's `covers`, at 2.5 m for booths and 10 m for gantries

A placemark corresponds to the booth group with a member node closest to it, provided that distance is inside the group's threshold and the group appears in that route's `covers`.

Measured over a full replay of the previous route set — 747 routes, 3524 matched placemarks:

| quantity | value |
|---|---|
| placemark → nearest member of the winning covered group | p50 0.75 m, p99 1.30 m, **max 2.21 m** |
| nearest **co-covered** group, over 9390 co-covered pairs | 2.5 m (one anomaly), then 1464 m |
| the two `highway=toll_gantry` outliers | 4.62 m and 7.35 m, next candidate 189 m and 248 m away |

**2.5 m for `barrier=toll_booth` groups.** No observed match falls in `(2.5, 3.0]`, so nothing is lost, and it resolves the one ambiguous placemark in the run: Orange Centre offered candidates at 0.89 m and 2.56 m, and the second now falls outside.

**10 m for `highway=toll_gantry` groups.** A gantry is a portal over the carriageway with no lane node for either dataset to anchor on. The Cagny offset is 7.35 m and is almost entirely *along* the road — 0.21 m north, 7.35 m east on an east–west carriageway. All 3524 barrier matches were within 2.21 m; the only two outliers are both gantries.

The inventory separates cleanly: 1509 booth nodes, 56 gantry nodes, all 56 gantries singleton groups, and no group mixes the two. So which threshold applies is never in doubt.

The 10 m figure looks unsafe globally — 14 of 56 gantries have another group's node within 10 m, the closest at 5.02 m. It is safe because matching is restricted to the route's own `covers`, and those pairs are opposite carriageways of one free-flow point:

```
 the five close gantry pairs, co-covered by one route:   0, 0, 0, 0, 0
 min co-covered distance involving a gantry group:       1842.8 m
```

**That margin comes from the `covers` restriction, not from the threshold.** Relaxing the restriction later would remove it.

Alternatives considered:

- **A single 3 m threshold.** Rejected: it fails both gantries and leaves Orange Centre ambiguous.
- **A relative rule** — accept the nearest when the runner-up is ≥10× further. Works on the same data, but the type split is simpler and says why the numbers differ instead of just that they do.
- **Match on `StartAbscissa`**, the placemark's position in metres along the submitted polyline. Same information, plus a projection of every booth onto the geometry. Rejected as more work for no gain; still available as a cross-check.
- **Match on name.** Rejected on evidence: `04903 BIARRITZ` corresponds to OSM `Péage de La Négresse`, and `04801 PYRENEES ORIENTALES` corresponds to a group with no `name` tag at all.

### Match against every group member, not the representative

The representative is the numerically smallest node id in its group, which is an arbitrary lane. Group members span a median of 14.8 m and up to 735 m. Matching against all members — representatives and aliases — is what holds the worst case at 2.21 m.

The per-alias coordinate this relies on is published by `fix-booth-grouping-and-direction`, not by this change.

### `ID_PEAGE` is the recorded value; `Code` is not

`Code` is `<ID_PEAGE>_<uuid>`, where the uuid distinguishes the two directions of travel through one gare. An earlier draft recorded `Code`, because one OSM group was receiving two different codes at St-Maximin. That was a symptom of over-merged grouping, not of an ambiguous gare — and both codes were `06004 ST.MAXIMIN`, so the operator number alone would have sufficed even then.

`fix-booth-grouping-and-direction` removed the over-merges. Replaying the recorded run against the new grouping:

```
 groups with more than one distinct Code:       1     (Pyrénées Orientales, both 04801)
 groups with more than one distinct ID_PEAGE:   0
```

One operator number legitimately covers several groups — 535 of 663 observed gares do, which is the ordinary two-carriageway case. So the file records `{id, name}` per group and drops both the `code` field and the `codes` block. A tariff is a property of the gare; the direction instance is not something a consumer needs, and carrying it manufactured the only conflict left in the data.

`Code` was verified stable before it was dropped: three identical requests returned byte-identical values, and the same gare reached from a different origin returned the same value.

### Response points decode at precision 5

The request body is a precision-6 polyline, as the `precision=6` query parameter states. `Placemark.Geometry.Points` comes back at precision **5**. Decoding a response point at precision 6 places it in the Gulf of Guinea. This asymmetry is the single easiest thing to get wrong and never notice, since a wrong decode simply produces no match.

### No booth is recorded as having no gare

An earlier draft recorded `null` for a booth no placemark matched, and made that sticky so the first observation stood. Both are gone. A booth either has a gare or the run fails, and the failure tabulates every booth that lacks one.

The reason is what `null` turned out to mean in practice. Seventeen booths carried it, and they were four different problems wearing one label: private site tolls the operator has no reason to carry, lanes tens of metres from a gare that was mapped, opposite carriageways of a free-flow gantry, and a pair at Rosny-sur-Seine crossed twenty-nine times that the operator never reports at all. A single null said none of that. The table says all of it, and each column points at a different remedy.

Two exemptions keep the rule honest rather than merely strict. A booth the override file marks `absent_*` has no gare to find. A booth an override has since removed from the inventory is not the mapping's to resolve — the route set is regenerated far less often than the overrides are edited, so it goes on naming booths that no longer exist.

The check runs on every invocation, including one with nothing outstanding. An earlier version returned early in that case and would have reported success over a mapping known to be incomplete.

### A gare the operator misplaces is stated by hand

Positional matching cannot reach `12010 SEES`: the operator puts it 45 m from the lane the route drives and 7 m from a booth named `Argentan` that the route does not touch. No threshold reaches the first without reaching the second.

So when no covered group matches by position, the step falls back to the override file and matches by operator number instead. Exactly one covered group may claim it; two stop the run. That closed the only guardrail hit in 787 routes.

The predicted consequence was the split-plaza case: Orange Centre is one row of eight lanes that grouping splits into `448451541` and `656795`, and one route covers both, so one half looked destined to be permanently null. **The full run falsified that.** Different routes return different placemarks for that plaza, each matched its own half, and both groups recorded `04210 ORANGE`. Keying on the operator number rather than the per-direction `Code` is what makes that agreement rather than a conflict.

Four groups sit within 160 m of a mapped gare and get no placemark of their own — Hochfelden 20.8 m from `07706 SCHWINDRATZHEIM`, Cholet Sud 19.2 m from a gare of the same name, and two Péage de Vienne lanes at 57.8 m and 159.9 m from `04201 VIENNE`. Each is covered by exactly one route that returns no corresponding placemark, and each is now stated `absent_*` in the override file.

### An empty response means the route has no tolls

An empty array is a valid answer, not a failure. Nothing is recorded for that route's booths; whether they ever get a gare is settled by the other routes that drive through them, and by the end-of-run check.

### Strict on everything else

A placemark with no covered group inside its threshold aborts the run. So does a second covered group inside its threshold, and so does an attempt to write a different operator number over one already recorded for that group.

The most likely trigger is the through-road filter: 282 booths were excluded from the inventory, and 272 of them lie more than 100 m from any retained booth. A route past one of those gares has no candidate to match. Aborting is correct — it means the filter dropped something real — so the abort message must carry the placemark's `ID_PEAGE`, `Preview`, decoded position, the route, and the nearest retained and nearest excluded booths with their distances.

### Geometry comes from the project's own OSRM instance

`overview=full&geometries=polyline6` against `osrm-optimal`. `overview=simplified` drops vertices and shifts the line off the carriageway, which would cost matches. Full geometry reached 58757 characters for a 1069 km route and the service accepted it; the longest route in the set is of that order.

The step consequently depends on the routing service the same way `build_route_set` does, and inherits the same reproducibility guarantee for `covers`.

### Always execute, resume from the file

The step is a no-op on a complete file: it makes no requests and performs one set lookup per route. Making it a file target instead would leave a partial run permanently unfinished, since the pipeline skips on existence rather than content.

`(from, to)` is a sound resume key — no two routes in the set share a pair, though 348 routes have their reverse also present, and those are distinct routes with distinct booths.

### Politeness and retries

One request per second to the Ulys service, measured from the previous request, on a single thread. Five attempts with exponential backoff. Backoff delays exceed one second, so a retry satisfies the rate limit on its own. A route whose attempts are all exhausted aborts the run; it never records nulls.

A cold run is about 13 minutes. The 63-route sample took 84 seconds.

## Risks / Trade-offs

- **The threshold has 0.79 m of headroom, measured on 314 of roughly 3560 placemark slots.** → The full run may find a worse legitimate match and abort. That is the intended behaviour under a strict policy: the abort names the placemark and its distance, so the value can be revisited on evidence rather than guessed upward.
- **The subscription key is a browser key and will rotate.** → It lives in `.env`, not in the image or the script, and a guard fails the step before any work when it is unset.
- **The service is undocumented and may change shape or disappear.** → The step is resumable and separate from the rest of the pipeline, so a failure costs no re-derivation of the inventory or the route set. `data/vinci_toll_booth.yaml` is committed, so a consumer keeps the last good mapping.
- **Forbidding a booth without a gare turns a report into a blocker.** → That is the intent: seventeen booths were silently null, and each needed a decision. It is only workable because the override file can record those decisions, and because the exemptions cover the two cases where no decision is owed.
- **A gare present in the service but excluded from the inventory aborts the run.** → Accepted deliberately, as the abort is the discovery mechanism. It fired once in 787 routes, at Sées, and a hand-stated gare closed it.
- **The step now depends on the override file as well as the inventory, and the two can drift.** → The step compares them and stops with the rebuild command rather than reporting a booth whose override was never applied.

## Migration Plan

1. Land `fix-booth-grouping-and-direction` first: it owns the inventory format, the grouping rules, and the direction-carrying `covers` shape this step reads.
2. Add the new step against the regenerated route set.
3. Run it, and commit `data/vinci_toll_booth.yaml`.

Rollback is deletion: the new step's output is a standalone file, and the inventory format change is one commit.

## Outcome

787 routes, 3850 placemarks, 13.1 minutes, **zero guardrail hits**. 1274 groups recorded, mapped to 669 gares. 574 gares span more than one booth group, up to five — the ordinary carriageway case.

Getting there took two passes and the override file:

**`12010 SEES` was the only guardrail hit.** Sées and Argentan share one plaza on the A88, and the placemark lies 7.3 m from an OSM node named `Argentan` — already recorded as `12210 ARGENTAN` — and 45.3 m from the `Sées` lane the route drove. No threshold reaches the right answer without reaching the wrong one first, and the `covers` restriction was the only thing that prevented a wrong write. A `vinci` entry on `14061571392` resolved it by operator number.

**Seventeen booths had no gare**, and forbidding `null` forced each to be classified. Five were private and nature-site tolls the operator has no reason to carry, now `type: ignore`. Twelve are real booths the operator does not carry, now `absent_*`: Chanas and Bernay on the A7 and A28 with nothing mapped within 7 km, four lanes 19–160 m from a gare that was mapped, and four free-flow gantries. Of those, `12636038010` and `12636038011` at Rosny-sur-Seine are crossed by 14 and 15 routes and never reported once, with the nearest mapped gare 3.2 km away — still unexplained, and now recorded as such rather than hidden behind a null.

## Archived incomplete

Two tasks were not done, and the change was archived anyway by explicit decision.

- **`make all` was never run end to end.** The fifth step is wired into `all` and exits 0 on its own, and every step has been run individually, but the requirement that a complete tree produces no work and no requests is untested as a whole.
- **Nothing is committed.** `data/vinci_toll_booth.yaml` is on disk and trackable but untracked, along with every other change from this and the two changes before it.

## Open Questions

- How to resolve `12010 SEES`. Until it is resolved the step exits non-zero and `make all` fails at step 5. It is the same class as the cases deferred by `fix-booth-grouping-and-direction`, and it may be an OSM naming problem at the Sées/Argentan plaza rather than anything this step can fix.
- Why Rosny-sur-Seine yields no placemark across 29 route-crossings.
- Whether a booth group can legitimately receive two different operator numbers. None does in the recorded data; the strict conflict abort exists to surface it if one appears.
