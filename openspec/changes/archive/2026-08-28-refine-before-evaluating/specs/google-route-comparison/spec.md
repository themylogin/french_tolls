## MODIFIED Requirements

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
