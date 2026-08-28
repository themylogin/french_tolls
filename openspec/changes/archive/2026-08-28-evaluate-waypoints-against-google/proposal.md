## Why

The waypoint search has one job: make a general-purpose navigation application drive the optimal route. Nothing has ever checked whether it does.

What is checked today is that each leg is the fastest route **on this project's own untouched graph**. That is the honest contract the specs state, and it is verified — by 47 unit tests against a hand-built graph, and, while it existed, by a suite that re-queried every leg against the France extract. None of it asks the question the driver cares about: paste these waypoints into Google Maps, and does Google drive the road we promised?

It cannot be answered by reasoning. Google's road network is not OSM's, its speeds are not OSRM's, and its routing engine is not OSRM's. The only way to know is to ask Google and compare.

That answer is worth money — literally. Google charges per request, so this is deliberately not part of any routine run: not `make all`, not `make test`, not anything that happens by accident. It is an explicit, occasional, paid measurement whose results are kept forever so they are never paid for twice.

## What Changes

### A committed set of test cities

- `data/test_cities.yaml` holds 50 cities on mainland France, spread as evenly over the territory as the OSM `place=city` nodes allow, each with its OSM node id, name, and coordinates.
- `make test_cities` produces it from the France extract. Mainland is decided by road connectivity on this project's own graph rather than by a hand-drawn box: Corsica and the overseas departments are in the extract and are not reachable by road from the mainland, which is exactly what disqualifies them.
- The step is incremental. An existing file is kept and topped up to 50; a full file costs nothing to re-run.

### A committed set of Google routes

- `make test_google_routes` asks this project for the optimal route between every ordered pair of cities — **2 450 journeys**, both directions of all 1 225 pairs, because A→B and B→A cross different barriers and get different waypoints — and then asks Google to drive each one through those waypoints.
- Requests go to the **Routes API** with `routingPreference: TRAFFIC_UNAWARE`, which is Google's own phrase for routing as though the road were empty. That is what OSRM computes, so it is what makes the two comparable. No departure time, no traffic model, no fuel-efficient alternative, no waypoint reordering, and tolls emphatically not avoided.
- Every field Google will return is requested and stored, along with the request that produced it, under `data/google_routes/{osm_id}-{osm_id}.json`. A paid answer is kept whole; a field not saved today is a field that has to be bought again.
- The step is incremental and resumable at the granularity of one journey. A pair with a file is never requested again, and a request that fails writes nothing, so it is simply outstanding next time.
- **Nothing is spent without saying so first.** The step counts the outstanding journeys, states the cost, and stops unless told to proceed. It refuses to start at all without a key.

### A report that says how well it works

`make test_google` asks this project for the same 2 450 routes, compares them with what Google drove, and prints three things:

1. **The ten journeys Google drove least faithfully**, ranked by how much of Google's route falls outside a corridor around ours — with a link to this project's own map and a link to Google's, for both routes, so a disagreement can be looked at rather than guessed at.
2. **The ten largest time deviations**, in minutes and as a proportion, listed separately because they disagree: the largest in minutes are long journeys, the largest in proportion are short ones.
3. **The average multiplier between OSRM's travel time and Google's**, which is the single number saying how far this project's idea of how long a drive takes sits from Google's.

### Where it lives

- A new `evaluation/` directory holds the three scripts and their own container image, beside `builder/`, `french_tolls/`, and `www/`. It is a fourth kind of thing: not a pipeline step, not the application, not the page.
- `make test` is untouched and still runs the 47 unit tests in 0.15 s. `make all` is untouched. Nothing here runs unless it is named.

## Capabilities

### New Capabilities

- `google-route-comparison`: the city set and how it is chosen, the Routes API request and what makes it comparable to OSRM, the storage and incremental contracts, the spending guard, the overlap measure, and the three parts of the report.

### Modified Capabilities

- `build-pipeline`: the project layout requirement places the pipeline under `builder/`, the application under `french_tolls/`, and the page under `www/`. It does not account for `evaluation/`, nor say that its outputs are committed while the pipeline's intermediates are not.
- `route-service`: the requirement listing the Compose services says the file defines four further services. There is now a fifth, which is neither the application nor the front end.

## Impact

- New: `data/test_cities.yaml` (committed), `data/google_routes/` (2 450 files, committed — a paid answer bought once).
- New: `evaluation/Dockerfile`, and the scripts that build the cities, fetch the Google routes, and print the report.
- Modified: `docker-compose.yml` (an `evaluation` service under its own profile), `Makefile` (`test_cities`, `test_google_routes`, `test_google`), `.env.example` (the Google key).
- Unchanged: every Python module of the application, the page, the pipeline's eleven steps, `make all`, and `make test`.
- Cost: roughly **$25** for a full sweep at the Advanced tier that intermediate waypoints put every request into, paid once. Re-runs cost nothing.
- Runtime: about ten minutes for the Google sweep, dominated by being polite to the API rather than by the work.
- Depends on the `web` service running, because the routes and waypoints under test are fetched through `/api/calculate` — the same path a user gets, rather than a private copy of the algorithm that could differ from it.
