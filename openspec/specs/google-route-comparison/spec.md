# google-route-comparison Specification

## Purpose
Measures whether the waypoints this project emits actually make Google drive the optimal route — a set of test cities, a bought-once corpus of Google routes through those waypoints, and a report saying how faithfully Google followed and how far its travel times sit from OSRM's.

## Requirements

### Requirement: The measurement is never part of a routine run

No target of this capability SHALL be a prerequisite of `all`, of `test`, or of any other target that a person runs without meaning to run this one.

Every request it makes to Google is paid for. A measurement that can be triggered by habit is a measurement that will be paid for by habit.

`make test` SHALL continue to run the unit suite, and only the unit suite. The two are different questions — whether the algorithm is correct, and whether Google agrees with it — and only one of them costs money.

#### Scenario: The pipeline does not run it

- **WHEN** `make all` is run
- **THEN** no city set is generated, no Google request is made, and no report is printed

#### Scenario: The unit suite does not run it

- **WHEN** `make test` is run
- **THEN** the 47 unit tests run and nothing contacts Google

#### Scenario: It runs when it is named

- **WHEN** `make test_google` is run
- **THEN** the measurement proceeds

### Requirement: Fifty cities, spread over mainland France

`data/test_cities.yaml` SHALL hold a list under the key `cities`, each entry carrying `osm_id`, `name`, and `latlon`:

```yaml
cities:
  - osm_id: 20524
    name: Paris
    latlon: [48.8566, 2.3522]
```

Candidates SHALL be OSM nodes tagged `place=city`, taken from the France extract the pipeline already downloads. Where fifty such nodes cannot be spread acceptably, `place=town` SHALL be admitted as well, and the step SHALL say that it did.

The fifty SHALL be chosen to cover the territory rather than to be the largest: repeatedly taking the candidate furthest from every city already chosen produces a spread that a population ranking does not, because population clusters and the road network does not. The choice SHALL be deterministic, so that two runs of the same extract produce the same file.

#### Scenario: The file's shape

- **WHEN** `data/test_cities.yaml` is read
- **THEN** it parses as YAML with a `cities` list of fifty entries, each carrying `osm_id`, `name`, and `latlon`

#### Scenario: The spread is not a population ranking

- **WHEN** the fifty are chosen
- **THEN** they are chosen by distance from one another, and the set is not simply the fifty largest cities

#### Scenario: The choice is reproducible

- **WHEN** the step is run twice against the same extract with no existing file
- **THEN** it produces the same fifty cities in the same order

### Requirement: Mainland is decided by the road network, not by a box

A candidate SHALL be admitted only if this project's own routing graph can drive to it from a mainland reference point **without taking a ferry**.

A latitude and longitude box has to be drawn by hand, has to be redrawn when it is found to clip somewhere real, and states as geography something the network states as fact. But the unqualified question — can the router reach it? — admits Corsica, because the car profile is content to board a ferry. Measured, Bastia is 21.3 hours from Paris by road and ferry, and unreachable when ferries are excluded, while Lyon is 5.0 hours either way.

The exclusion SHALL be asked of the router rather than applied afterwards. The routing profile declares `ferry` an excludable class, so the router can answer the question actually meant instead of being asked a different one and then argued out of the answer.

The overseas departments SHALL need no handling. The France extract this project downloads does not carry them: measured, it holds no city or town node outside mainland Europe and Corsica.

A candidate the router cannot reach SHALL be excluded, and the step SHALL report how many were excluded for that reason.

#### Scenario: Corsica is excluded

- **WHEN** the city set is built
- **THEN** no city on Corsica appears in it, because no ferry-free route reaches one

#### Scenario: A ferry-free route is what is asked for

- **WHEN** reachability is tested
- **THEN** the request excludes the ferry class, and a candidate reachable only by ferry is reported unreachable

#### Scenario: The mainland is unaffected by the exclusion

- **WHEN** a mainland candidate is tested
- **THEN** its reachability and duration are the same with ferries excluded as without

#### Scenario: The exclusions are reported

- **WHEN** the step completes
- **THEN** it states how many candidates were unreachable

### Requirement: The city set is built incrementally

An existing `data/test_cities.yaml` SHALL be read, its cities kept, and only the shortfall to fifty chosen afresh. A file already holding fifty SHALL leave the step with nothing to do.

A city already in the file SHALL NOT be dropped or reordered by a later run. The Google routes are stored under the ids in this file, so a city that changes place invalidates every route that named it.

#### Scenario: A complete file is left alone

- **WHEN** the step runs against a file of fifty cities
- **THEN** the file is unchanged and no route is invalidated

#### Scenario: A partial file is topped up

- **WHEN** the step runs against a file of twenty cities
- **THEN** those twenty are kept in place and thirty more are added

### Requirement: Google is asked to drive the route this project computed

For each ordered pair of cities, the system SHALL obtain this project's optimal route and its waypoints, ask Google for a driving route through exactly those waypoints, **refine them against what Google drove**, and then ask Google again for a driving route through the refined set.

The second route is what the journey is measured on. It is the route a driver is sent down: a link carries the refined waypoints, so the unrefined route describes a link nobody receives. Measured on Bayeux to Apt, the difference is 74.4% faithful against 91.8%.

The first request cannot be skipped. The refined waypoints are placed in the stretches where Google left our route, and nothing but Google's answer says where those are. Two requests per journey is therefore the floor, not a choice.

Refinement SHALL use the same drift-measuring and waypoint-placing code the application uses, imported rather than reimplemented. A second copy could disagree with the first, and the evaluation would then be measuring something no user is given.

Both directions of every pair SHALL be requested. A→B and B→A cross different barriers, are priced differently, and get different waypoints, so one direction says nothing about the other.

The route and the waypoints SHALL be obtained from the running application's `/api/calculate`, not from a private copy of the algorithm. What is under measurement is what a user is given.

#### Scenario: Every ordered pair

- **WHEN** the sweep is complete for fifty cities
- **THEN** 2 450 journeys have been fetched, being both directions of all 1 225 pairs, at two Google requests each

#### Scenario: The measured route is the refined one

- **WHEN** a journey is fetched
- **THEN** the route stored for analysis is Google's route through the refined waypoints, and every one of those waypoints lies on it

#### Scenario: A journey Google already followed

- **WHEN** the first request finds no stretch outside the corridor
- **THEN** no waypoint is added, no second request is made, and the route already obtained is the one measured

#### Scenario: The waypoints are the ones under test

- **WHEN** a journey is submitted to Google
- **THEN** its intermediate waypoints are exactly those `/api/calculate` returned for that journey, in the order it returned them

#### Scenario: A journey needing no waypoint

- **WHEN** this project emits no waypoint for a journey
- **THEN** Google is asked for that journey with no intermediates, and the answer is stored like any other

### Requirement: The request describes an empty road

Requests SHALL go to the Routes API's `computeRoutes`, with `travelMode: DRIVE` and `routingPreference: TRAFFIC_UNAWARE`.

`TRAFFIC_UNAWARE` is Google routing as though the road were empty. That is what OSRM computes from its profile's speeds, and it is the only setting under which the two durations are answers to the same question. A traffic-aware route would differ from ours for a reason that has nothing to do with the waypoints.

The request SHALL NOT carry a departure time, SHALL NOT request a fuel-efficient or eco alternative, SHALL NOT request alternative routes, and SHALL NOT permit the waypoint order to be optimised. Reordering the waypoints would answer a question about a journey nobody asked for.

Tolls SHALL NOT be avoided. The whole subject is a route that uses toll roads deliberately.

Every route modifier that has a default SHALL be stated rather than left to it, so that a change to Google's defaults cannot silently change what was measured.

#### Scenario: Traffic takes no part

- **WHEN** a request is built
- **THEN** it sets `routingPreference: TRAFFIC_UNAWARE` and carries no departure time

#### Scenario: The waypoints are not reordered

- **WHEN** a request carries intermediates
- **THEN** waypoint order optimisation is off, and Google's answer visits them in the order given

#### Scenario: Tolls are not avoided

- **WHEN** a request is built
- **THEN** it does not ask to avoid tolls, and says so explicitly rather than relying on the default

### Requirement: A paid answer is stored whole and never bought twice

Each journey's answer SHALL be written to `data/google_routes/{origin osm_id}-{destination osm_id}.json`.

The system SHALL request every field the API will return, and SHALL store the response body unaltered. A field not stored today is a field that has to be paid for again to obtain.

The file SHALL also carry the request that produced it, the waypoints that were sent, this project's own route for that journey, and when it was fetched. An answer whose question is not recorded cannot be interpreted later, and the waypoints are the subject of the measurement.

Both phases SHALL be recorded, and told apart. The refined route is stored whole, because it is what the report ranks and draws. Of the unrefined route only its **measurements** are kept — its faithfulness, its drift, its distance and duration — because they are why the refinement happened and what the improvement is measured against, while its geometry is never drawn and would double a corpus already in the hundreds of megabytes.

Each phase SHALL be stored as it completes, so a journey interrupted between the two is resumed rather than re-bought, and the twenty journeys already holding an unrefined answer need only the second request.

A journey whose file already exists SHALL NOT be requested again. A request that fails SHALL write no file, so that it is simply outstanding on the next run.

#### Scenario: Everything is kept

- **WHEN** a journey is fetched
- **THEN** its file holds the whole response body, the request sent, the waypoints, this project's route, and a timestamp

#### Scenario: A second run costs nothing

- **WHEN** the step is run again with every file present
- **THEN** no request is made to Google

#### Scenario: An answer bought before refinement existed

- **WHEN** the step meets a journey holding only an unrefined answer
- **THEN** it makes one request rather than two, keeping the unrefined measurements it already has

#### Scenario: The before and the after are both readable

- **WHEN** a stored answer is read
- **THEN** it carries the refined route's geometry, and the unrefined route's faithfulness and drift, and the two cannot be confused

#### Scenario: A failure stays outstanding

- **WHEN** a request fails
- **THEN** no file is written for it, the failure is reported, and the sweep continues with the rest

### Requirement: Nothing is spent without saying so first

Before issuing any request, the step SHALL count the journeys it would fetch, state how many Google requests that is and what share of the month's free allowance it consumes, and stop unless it has been told to proceed.

It SHALL count requests against the free monthly cap rather than quote a price. Google's pricing page states a cap of 10 000 requests a month and names Essentials and Pro tiers without saying which a route request with intermediate waypoints falls into — so a figure in dollars cannot be derived from it, and the figure this step used to print was not derived from it either. A full fifty-city sweep is 4 900 requests, inside the cap, and what an operator needs before starting is how much of the allowance will be left.

The application shares the API key and therefore the same allowance. The step SHALL say what it is about to consume and what that leaves.

The system SHALL refuse to start when no API key is configured, naming the variable, rather than issuing requests that fail one at a time.

A limit SHALL be settable, so that a first run can buy ten answers and be looked at before the remaining two thousand are bought.

A limited run SHALL be able to choose *which* journeys it buys, not merely how many. Outstanding pairs are enumerated origin-major, so the first ten are ten destinations from one city: a sample of that city's surroundings rather than of the country. Selecting the longest journeys that share no city with one another SHALL be available, because a long journey crosses more of the toll network and a repeated city makes two results share whatever is peculiar about it.

#### Scenario: The cost is stated before it is incurred

- **WHEN** the step is run with 2 450 journeys outstanding
- **THEN** it reports that this is 4 900 Google requests against a monthly cap of 10 000, and makes no request until it is told to go ahead

#### Scenario: No price is invented

- **WHEN** the step reports what a run will consume
- **THEN** it states requests and the share of the free cap, and quotes no price per request

#### Scenario: No key

- **WHEN** the step is run with no API key configured
- **THEN** it stops naming the variable, and issues no request

#### Scenario: A limited first run

- **WHEN** the step is run with a limit of ten
- **THEN** at most ten journeys are fetched and the rest remain outstanding

#### Scenario: A limited run can be a spread rather than a prefix

- **WHEN** a limited run is asked for the longest independent journeys
- **THEN** the ten it buys share no city with one another, and it names them before spending

### Requirement: Faithfulness is how much of Google's route ran along ours

For each journey the system SHALL compute an **overlap**: the proportion of the length of Google's route that lies within a corridor of this project's optimal route.

The corridor half-width SHALL default to 50 m and SHALL be settable. It is wide enough to absorb the two networks disagreeing about where a carriageway lies, and narrow enough that a parallel road is outside it.

The measure SHALL be weighted by length rather than by number of points. Google's geometry is denser through bends than along a motorway, so counting points would let a roundabout outweigh fifty kilometres of autoroute.

Comparing totals alone SHALL NOT be used as the measure of faithfulness. A detour of similar length reads as agreement, and that is the failure this exists to catch.

#### Scenario: Google drove our route

- **WHEN** Google's route runs along the optimal route throughout
- **THEN** its overlap is at or near 1.0

#### Scenario: Google took a different road

- **WHEN** Google leaves the optimal route for a third of its length
- **THEN** the overlap is about 0.67, however similar the totals are

#### Scenario: Length, not points

- **WHEN** Google's geometry is dense in one place and sparse in another
- **THEN** each contributes to the overlap in proportion to its length

### Requirement: The report answers three questions

`make test_google` SHALL print, from the stored answers and freshly obtained OSRM routes for the same journeys:

1. **The ten least faithful journeys**, ranked by ascending overlap. Each SHALL name its two cities, its overlap, both routes' distance and duration, and four links: this project's map and Google's map, for this project's route and for Google's.
2. **The ten largest time deviations in minutes, and the ten largest in proportion**, as two separate lists. They disagree — the largest in minutes are long journeys, the largest in proportion are short ones — and a report giving only one of the two misreads the data.
3. **The average multiplier from OSRM's travel time to Google's, reported separately for two populations**, each with its count and its spread:
   - journeys Google drove **faithfully after refining**, where the ratio compares OSRM's clock with Google's on the same road;
   - journeys that **still diverge**, where it compares our time on one road with Google's on another.

   Both SHALL be reported as results. The second is not a residue to be discarded: it measures how much time Google believes it saves by ignoring the route, which is what a driver gives up by following the link.

   The mixed average over all journeys SHALL still be printed, labelled as mixing the two, so that the change to a number previously reported alone is visible rather than silent.

   One number over both populations cannot be read as either. Measured over the twenty journeys bought before refinement existed, the ratio rises monotonically with faithfulness — x0.9087 below 80% overlap, x0.9174 between 80 and 90, x0.9447 above 90 — so the mixed x0.9239 is an artefact of the mixture.

A journey whose optimal route **is** its fast route SHALL be excluded from the report entirely, and the exclusions counted and stated.

Such a journey had no toll worth avoiding, so no waypoint was ever needed to steer Google away from anything and it would have driven the route unprompted. Counting it as faithfully driven measures nothing about the waypoints and inflates the very population that is supposed to say whether they work. Measured over the first thirty journeys, one is excluded by this rule.

The population a journey belongs to SHALL be decided by its overlap against a stated threshold, and the threshold SHALL be printed with the result. It SHALL be settable, because it is a judgement rather than a fact.

A journey in the diverging population SHALL be reported with why it is there — in particular whether the nine-waypoint ceiling left drift it had no slot to correct. Of the five journeys predicted to remain divergent, four are ones whose budget could not cover their drift; naming that turns a listing into a diagnosis.

The report SHALL state how many journeys it covered and how many are missing, so that a report over a partial corpus is never mistaken for a report over all of it.

The report SHALL NOT contact Google. It reads what was bought.

#### Scenario: A journey can be looked at

- **WHEN** a journey appears among the ten least faithful
- **THEN** the report carries links that open this project's route and Google's route on a map

#### Scenario: A journey with nothing to steer is excluded

- **WHEN** a journey's optimal route and fast route are the same route
- **THEN** it appears in neither population, and the report states how many were excluded for that reason

#### Scenario: The multiplier is reported per population

- **WHEN** the third section is printed
- **THEN** it carries one figure for the faithful journeys and one for the diverging ones, each with its count and spread, and the threshold that separated them

#### Scenario: The mixed average is still visible

- **WHEN** the third section is printed
- **THEN** the average over all journeys appears too, labelled as mixing the two populations

#### Scenario: A diverging journey is diagnosed

- **WHEN** a journey is reported as still diverging
- **THEN** the report says whether its waypoint budget could have covered its drift

#### Scenario: The two time rankings are separate

- **WHEN** the time deviations are reported
- **THEN** the largest in minutes and the largest in proportion appear as two lists

#### Scenario: Coverage is stated

- **WHEN** the report runs with 300 of 2 450 answers stored
- **THEN** it says so, and its averages are labelled as being over those 300

#### Scenario: The report is free

- **WHEN** the report is run
- **THEN** no request is made to Google, whatever is missing

### Requirement: The evaluation is a Compose service of its own

`docker-compose.yml` SHALL define an `evaluation` service, built from an image under `evaluation/`, behind its own profile so that neither `docker compose up` nor the application's profile starts it.

It SHALL mount `./data` writable, because what it produces is kept there, and SHALL reach the application and the routers by service name over the Compose network.

It is not the only service that makes a paid outbound request: the web application refines a journey's waypoints against Google, under a monthly ceiling of its own. The two are separate spenders with separate purposes — the evaluation buys a corpus once to measure against, the application buys one answer to improve one link — and neither reads the other's budget.

#### Scenario: It is not started by anything else

- **WHEN** `docker compose up` or `docker compose --profile app up` is run
- **THEN** the evaluation service does not start

#### Scenario: The two spenders are independent

- **WHEN** the evaluation runs a sweep
- **THEN** the application's monthly refinement budget is unaffected by it, and the evaluation's spending is not counted against it

#### Scenario: It reaches the application by name

- **WHEN** the sweep asks for a route
- **THEN** it calls the web service over the Compose network, not a published host port
