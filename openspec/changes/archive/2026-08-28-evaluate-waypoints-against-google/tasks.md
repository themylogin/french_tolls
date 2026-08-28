## 1. The evaluation image and its service

- [x] 1.1 Write `evaluation/Dockerfile` on `debian:bookworm-slim` with `python3`, `python3-yaml`, `python3-requests` from Debian packages, as `builder/Dockerfile` does; verify the image builds and imports all three
- [x] 1.2 Add an `evaluation` service to `docker-compose.yml` behind its own profile, mounting `./data` writable, carrying `GOOGLE_DIRECTIONS_API_KEY` and the addresses of `web` and the two routers; verify `docker compose config` parses and that neither `up` nor `--profile app up` starts it
- [x] 1.3 Add `GOOGLE_DIRECTIONS_API_KEY` to `.env.example` with the same commented style, saying which API it is used against and that it is the only paid credential in the project; verify every variable the compose file interpolates is documented
- [x] 1.4 Add `test_cities`, `test_google_routes`, and `test_google` to the Makefile and to `.PHONY`, none of them a prerequisite of `all` or of `test`; verify `make -n all` and `make -n test` mention none of them, and `make -n test_google` shows the expected invocation

## 2. The city set

- [x] 2.1 Extract candidate cities from the France extract — `place=city`, falling back to `place=town` where fifty cannot be spread — reporting the mix it used; verify the candidate count and how many came from each tag
- [x] 2.2 Exclude candidates the router cannot reach from a mainland reference, and report how many were excluded; verify no Corsican or overseas city survives and that the count is printed
- [x] 2.3 Choose fifty by farthest-point sampling, deterministically; verify two runs from an empty state produce the same fifty in the same order, and that the set is not the fifty largest cities
- [x] 2.4 Write `data/test_cities.yaml` in the `cities: [{osm_id, name, latlon}]` shape; verify it parses and holds fifty entries each carrying all three keys
- [x] 2.5 Make the step incremental — keep and do not reorder existing entries, top up only the shortfall; verify a complete file is left byte-identical and a file of twenty gains thirty
- [x] 2.6 Run it and look at the fifty on a map; verify the spread covers the territory rather than clustering, and record what the mix of city and town turned out to be

## 3. Buying the Google routes

- [x] 3.1 Build the ordered pair list from the city file and determine which are outstanding by the presence of `data/google_routes/{osm_id}-{osm_id}.json`; verify 2 450 pairs for fifty cities and that an existing file removes its pair from the list
- [x] 3.2 Implement the spending guard — count outstanding, state the estimated cost, refuse without `--yes`, refuse with no key naming the variable, and honour `--limit`; verify each of the four behaviours, all without issuing a request
- [x] 3.3 Fetch this project's route and waypoints for a journey from the running `web` service's `/api/calculate`; verify it returns the optimal route's nodes, waypoints, distance, duration, and cost
- [x] 3.4 Build the Routes API request as designed — `TRAFFIC_UNAWARE`, no departure time, no alternatives, no waypoint optimisation, tolls not avoided, every modifier stated, `FieldMask: *`; verify the built body against the design before any request is sent
- [x] 3.5 Store each answer as `{fetched_at, origin, destination, waypoints, ours, request, response}` with the response body unaltered; verify a stored file round-trips and carries Google's polylines and legs
- [x] 3.6 Never re-request a stored journey, write nothing on failure, report failures and continue; verify by rerunning after a success and after a deliberately failed request
- [x] 3.7 Buy ten journeys with `--limit 10`; verify `FieldMask: *` returned the fields expected, record the median file size, and project the corpus size before the rest is bought
- [ ] 3.8 Buy the remaining journeys once 3.7 and 4.x have been looked at; verify the corpus is complete and report the total spent

## 4. The report

- [x] 4.1 Implement the length-weighted overlap with a grid index over our route's segments and a settable corridor defaulting to 50 m; verify on a journey Google drove faithfully (overlap near 1.0) and on one where a third was replaced by a detour (about 0.67)
- [x] 4.2 Confirm the grid index makes the measure fast enough for the whole corpus; verify by timing it over the journeys bought so far and projecting to 2 450
- [x] 4.3 Request the same journeys from OSRM live so the report can also say how far today's algorithm has moved from what was bought; verify the report distinguishes the stored route from the current one
- [x] 4.4 Print the ten least faithful journeys with both cities, the overlap, both distances and durations, and the three links the design specifies; verify each link opens the route it claims to
- [x] 4.5 Print the ten largest time deviations in minutes and the ten largest in proportion, as two separate lists; verify the two lists differ on real data
- [x] 4.6 Print the average OSRM-to-Google travel time multiplier with its spread, over the journeys with stored answers; verify the average is labelled with the count it covers
- [x] 4.7 State coverage — how many journeys were compared and how many are missing — and make no request to Google; verify by running the report with the corpus partial and with the network unavailable

## 5. Verification

- [x] 5.1 Confirm `make all` triggers none of this; verify by inspecting the target's prerequisites and by a dry run
- [x] 5.2 Confirm `make test` still runs the 47 unit tests and contacts nothing; verify the run passes and takes under a second
- [x] 5.3 Confirm the report is free and repeatable; verify two consecutive runs produce the same numbers and no request
- [x] 5.4 Record what the report says over the twenty journeys bought so far — ten from one origin and ten long independent ones. Overlap median 87.7%, mean 87.2%, range 74.4–97.7%, none at or above 99%. Travel time multiplier x0.9238, sd 0.0143. Recorded in the session and unchanged by corridor width from 20 m to 500 m. The full-corpus figure awaits 3.8 — the overlap distribution, the worst journeys, the average multiplier — as the measurement this change existed to obtain
