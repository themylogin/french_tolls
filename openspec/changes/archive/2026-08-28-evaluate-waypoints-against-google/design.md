## Context

See `proposal.md` — Why. The facts that shape the approach:

- `make test` is taken by the unit suite; `make all` runs the eleven pipeline steps and nothing else. Neither is touched.
- `GOOGLE_DIRECTIONS_API_KEY` is already in `.env`. The name says Directions; the requests go to the Routes API, which the same key serves when the API is enabled on the project.
- `builder/build_osm_toll_booths.py` already extracts OSM nodes whose `place` is one of city, town, village, hamlet, isolated_dwelling, locality. The city extraction is the same shape of work against the same extract.
- `data/route_set.yaml` already carries 771 places as `name` / `node_id` / `latlon`, so the requested `test_cities.yaml` shape is one the project already uses.
- `/api/calculate` returns `nodes` (the route's coordinates), `waypoints`, `distance`, `duration`, and `cost` for both routes. That is everything the sweep and the report need from this side.
- The `web` service publishes no host port; it is reached at `web:8080` on the Compose network.
- The two routers answer in 2–11 ms, so the OSRM side of the report costs nothing worth managing.

## Goals / Non-Goals

**Goals:**

- One number per journey saying how faithfully Google drove the route this project computed.
- A corpus of Google answers bought once, stored whole, and never bought again.
- A run that cannot spend money by accident.

**Non-Goals:**

- Automatic pass or fail. This measures; it does not assert. What a good overlap is has never been established, and inventing a threshold before the first measurement would bake in a guess.
- Continuous integration. This is run when someone wants to know, not on a schedule.
- Comparing tolls actually paid. That needs Google's polyline map-matched back onto OSM and priced, and it is a separate piece of work with its own failure modes.
- Changing the algorithm in response to what is found. Measuring first, deciding second.

## Decisions

### Layout: a fourth directory

`evaluation/` beside `builder/`, `french_tolls/`, and `www/`, with its own image: Debian, `python3-yaml`, `python3-requests` — the same packages `builder/` takes, for the same reason.

*Alternative rejected:* putting the scripts in `builder/`. The layout requirement says `builder/` holds pipeline scripts, and the first thing this capability requires is that it never becomes part of a build. Filing it with the build steps invites exactly that.

Three scripts, one per target: build the cities, fetch the Google routes, print the report. Kept apart because their failure modes are unrelated and only one of them costs money.

### Choosing fifty cities

Candidates: nodes tagged `place=city` in the France extract. Roughly 40 in France, which is short of fifty, so `place=town` is admitted next and the step reports the mix. (The exact count is measured during implementation; the rule is stated so the outcome is not a surprise.)

Spread by **farthest-point sampling**: seed with the candidate nearest the centroid of the candidate set, then repeatedly add the candidate whose distance to the nearest already-chosen city is greatest. Deterministic, needs no random seed, and produces a set that covers the territory — where taking the fifty largest would put six in the Paris basin and none in the Massif Central.

Mainland by **road connectivity**: a candidate is admitted only if `osrm-toll` returns a route from a mainland reference to it. Corsica and the overseas departments fail, which is the fact that makes them not mainland. Cost is one routing query per candidate against our own graph — milliseconds, free.

*Alternative rejected:* a latitude/longitude box. It has to be drawn by hand, it clips somewhere real sooner or later, and it asserts as geography what the network already knows.

### The Google request

```
POST https://routes.googleapis.com/directions/v2:computeRoutes
X-Goog-Api-Key: …
X-Goog-FieldMask: *
{
  "origin":      {"location": {"latLng": {"latitude": …, "longitude": …}}},
  "destination": {"location": {"latLng": {"latitude": …, "longitude": …}}},
  "intermediates": [ … our waypoints, in order … ],
  "travelMode": "DRIVE",
  "routingPreference": "TRAFFIC_UNAWARE",
  "polylineQuality": "HIGH_QUALITY",
  "polylineEncoding": "ENCODED_POLYLINE",
  "computeAlternativeRoutes": false,
  "optimizeWaypointOrder": false,
  "routeModifiers": {"avoidTolls": false, "avoidHighways": false, "avoidFerries": false},
  "units": "METRIC",
  "regionCode": "FR"
}
```

`TRAFFIC_UNAWARE` is the decision that makes the comparison mean anything: it is Google's own name for routing on an empty road, which is what OSRM computes. Anything traffic-aware would differ from ours for reasons that have nothing to do with waypoints.

`FieldMask: *` is what "store everything" requires. Google documents `*` as a development convenience and prefers a narrow mask in production; here the whole point is to buy the answer once and never wonder later what a narrower mask left out.

The three `routeModifiers` are stated although each is the default, so that a change to Google's defaults cannot quietly change what was measured. `optimizeWaypointOrder: false` is not decoration: with it on, Google would answer a question about a journey nobody asked for.

No `departureTime` — supplying one enables traffic and would make `TRAFFIC_UNAWARE` a contradiction.

### The stored file

`data/google_routes/{origin}-{destination}.json`, holding:

```json
{"fetched_at": "…", "origin": {…}, "destination": {…},
 "waypoints": [[lon, lat], …],
 "ours": {"distance": …, "duration": …, "cost": …, "waypoints_needed": …,
          "complete": …, "nodes": [[lon, lat], …]},
 "request": { … the body sent … },
 "response": { … Google's body, unaltered … }}
```

`ours` is stored beside Google's answer rather than re-fetched at report time. The report then compares what Google was actually asked to drive against what it drove; re-fetching would compare Google's old answer against a route the algorithm computes today, and a change to the algorithm would read as Google having changed its mind.

The report additionally queries OSRM live for the current route, so it can also say how far today's algorithm has moved — but the faithfulness measure uses the stored pair.

Size, measured on the first ten rather than guessed: Google's response is a median 220 KB, which is 552 MB across 2 450. Our own route geometry was another 167 KB a journey as a JSON array of floats, so it is stored as an encoded polyline instead — 24 KB, and 61 MB rather than 420 MB across the corpus. Precision 5 rounds to about a metre against a 50 m corridor, so nothing that matters is lost, and only Google's answer is kept verbatim because only Google's answer was paid for. Corpus: **about 660 MB**, not the low hundreds of megabytes first assumed.

### Spending guard

The step counts outstanding journeys, prints the count and the estimate, and stops unless `--yes` is given. A `--limit` caps a run. No key means it refuses to start, naming the variable.

Requests are sequential with a small delay. 2 450 requests at roughly a fifth of a second is about ten minutes, which is dominated by politeness rather than by work, and it keeps the failure mode to one request rather than a burst.

A failed request writes nothing and is reported. Resumption is therefore automatic: a rerun asks for exactly what is missing.

### Overlap

Google's `encodedPolyline` decodes at precision 5. Our route's geometry is the `nodes` array from `/api/calculate`.

Naively, every Google point against every one of our segments is 5 000 × 7 000 per journey, times 2 450 journeys — far too slow in Python. So our route's segments go into a **grid index** keyed on rounded coordinates at roughly 0.005° (about 400 m), and each Google point is tested only against segments in its own cell and the eight around it.

Overlap is **length-weighted**: for each consecutive pair of Google points, the segment counts as inside when its midpoint is within the corridor, and contributes its own length. A dense cluster of points through a roundabout then weighs what a roundabout is worth, not what fifty points are worth.

Corridor half-width defaults to 50 m — wide enough for the two networks to disagree about where a carriageway sits, narrow enough that a parallel road is outside it. Settable, because the first real measurement is what will say whether 50 m was a good guess.

### The report's links

Four per journey, all of them already computable:

- ours on this project's map: the deep-link fragment `{"from": {...}, "to": {...}}` the page already accepts;
- ours on Google's map: the `url` key `/api/calculate` already returns;
- Google's on Google's map: the same URL form built from Google's own route;
- Google's route drawn on this project's map is *not* offered — the page has no way to display a foreign polyline, and inventing one is a change to the page.

That last omission is deliberate and stated, rather than a link that would not work.

## Risks / Trade-offs

- **$25 spent on a measurement nobody acts on.** → The guard makes a ten-journey run the natural first step; the report on those ten is enough to see whether the measure says anything before the rest is bought.
- **`FieldMask: *` may be refused or may change what is billed.** → Caught by the first request rather than the two-thousandth, because the guard makes a small first run the default path. If `*` is refused, an explicit list of every documented field replaces it — more work, same outcome.
- **The key may not have the Routes API enabled**, since it is named for Directions. → The first request says so plainly. Switching to the legacy endpoint would be a change to one module and to the stored shape; the report reads the stored shape through one accessor for that reason.
- **A committed corpus in the low hundreds of megabytes.** → Flagged before it is bought, not after. This repository takes no commits today in any case, so the decision remains the user's.
- **Overlap says a route differed, not why.** → Which is why the report carries the links. The measure ranks; a person diagnoses.
- **Google's network is not OSM's.** A junction that exists in one and not the other lowers overlap without the algorithm being at fault. → Unavoidable, and the reason the output is a ranking to look at rather than a threshold to fail.
- **The `web` service must be up**, and its cache means a journey fetched twice returns the stored answer. → That is wanted: the sweep and the report should see one route per journey, not two.

## Migration Plan

1. `evaluation/Dockerfile` and the three scripts.
2. The `evaluation` Compose service, behind its own profile.
3. `make test_cities` — free, run it, look at the fifty on a map.
4. `make test_google_routes --limit 10` — buy ten, inspect the stored shape, confirm `FieldMask: *` returned what was hoped and measure the file size.
5. `make test_google` on those ten — confirm the report is worth the other 2 440.
6. Buy the rest.

Rollback is deleting `evaluation/`, the two Makefile targets, and the Compose service. `data/test_cities.yaml` and `data/google_routes/` are outputs, not code, and nothing else reads them.

## Open Questions

- **What overlap counts as good** is deliberately unanswered. The first report over a real sample is what will say whether 0.95 is routine and 0.80 is alarming, or whether the whole distribution sits lower than expected. Fixing a threshold now would be inventing the answer this exists to find, and no task depends on knowing it — the report ranks, it does not judge.
