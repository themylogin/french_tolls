# build-pipeline Specification

## Purpose
Defines the six-step build pipeline that turns a Geofabrik extract into a toll booth inventory, a covering route set, and a priced inventory, including how the steps are invoked, when they are skipped or resumed, and how the project is laid out and configured.

## Requirements

### Requirement: All work runs in containers

Every step SHALL perform its work inside Docker containers, so that the pipeline requires no OSM, routing, or language toolchain installed on the host beyond Docker and Compose.

#### Scenario: Host has no OSM tooling

- **WHEN** the pipeline runs on a host with Docker and Compose but without osmium, pyosmium, or OSRM installed
- **THEN** every step completes successfully

### Requirement: Project layout

The repository root SHALL hold only the pipeline's entry points — `Makefile` and `docker-compose.yml` — together with configuration dotfiles such as `.gitignore` and `.env.example`. No source file SHALL sit at the root.

The container image definition and all pipeline scripts SHALL live under `builder/`. Generated artifacts SHALL live under `data/`.

The artifacts the pipeline is asked to produce — the booth inventory, the route set, and the gare mapping — SHALL be committed, so a consumer can read them without running the pipeline. Regenerable intermediates, OSM extracts, and the per-run diagnostic reports SHALL NOT be committed.

The exclusion report and the uncovered report SHALL still be produced on every run: they describe what one run of the pipeline decided, and the gare mapping step reads the exclusion report to name the nearest excluded booth when a placemark matches nothing. They are diagnostics about a run rather than published outputs, so they are not carried in the repository.

#### Scenario: Scripts are located together

- **WHEN** the repository is inspected
- **THEN** the Dockerfile and the pipeline scripts are under `builder/`, and no pipeline script sits at the repository root

#### Scenario: Root holds only entry points and configuration

- **WHEN** the tracked files at the repository root are listed
- **THEN** they are `Makefile`, `docker-compose.yml`, and configuration dotfiles, and nothing else

#### Scenario: Deliverables are committed

- **WHEN** the repository is checked out without running the pipeline
- **THEN** the booth inventory, the route set, and the gare mapping are present under `data/`

#### Scenario: Reports are produced but not committed

- **WHEN** the pipeline has run
- **THEN** the exclusion report and the uncovered report exist under `data/` and are untracked

#### Scenario: Extracts and intermediates are not committed

- **WHEN** the pipeline has run
- **THEN** the OSM extracts and the regenerable intermediates it produced are untracked

### Requirement: OSRM data location is configured via .env

The location of the OSRM graph SHALL be read from an `.env` file as `OSRM_OPTIMAL_PATH` and SHALL be mounted into the OSRM containers. `./data` SHALL be mounted alongside it. The pipeline SHALL fail with a clear message when `OSRM_OPTIMAL_PATH` is unset rather than operating on an unintended path.

Where that directory lives is deliberately unconstrained: it is local configuration, and the graph is excluded from version control wherever it sits.

#### Scenario: Configured path is used

- **WHEN** `.env` sets `OSRM_OPTIMAL_PATH` to a directory
- **THEN** the OSRM graph files are produced in that directory

#### Scenario: Path is not configured

- **WHEN** `OSRM_OPTIMAL_PATH` is unset or empty and any step needing it is run
- **THEN** the pipeline stops with a message naming the missing variable

### Requirement: The extract is not duplicated permanently

The downloaded extract SHALL be retained under `data/`. The copy placed alongside the OSRM graph for preprocessing SHALL be removed once preprocessing is complete, so the extract is duplicated only for the duration of that step.

#### Scenario: Copy is released after preprocessing

- **WHEN** the OSRM preprocessing step completes successfully
- **THEN** no `.osm.pbf` file remains under `OSRM_OPTIMAL_PATH`, while `data/france-latest.osm.pbf` is still present

#### Scenario: Stale copy from a failed run

- **WHEN** a previous preprocessing run failed and left a partial extract copy behind
- **THEN** the next run replaces that copy rather than treating it as usable input

### Requirement: Named routing service

The pipeline SHALL define a long-running OSRM query service named `osrm-optimal`, addressable under that name both as a container and on the Compose network, serving the graph from `OSRM_OPTIMAL_PATH`. One-shot preprocessing containers SHALL NOT be started by a plain `docker compose up`.

#### Scenario: Service is addressable by name

- **WHEN** the route set step issues routing requests
- **THEN** it reaches the query service at the host name `osrm-optimal`

#### Scenario: Plain compose up

- **WHEN** `docker compose up` is run
- **THEN** the query service starts and the one-shot preprocessing containers do not

### Requirement: Steps do not repeat completed work

No step SHALL repeat work it has already completed. A step SHALL establish that in one of two ways.

A **checkpointed** step SHALL be skipped when its output is already in place. Skipping SHALL depend on the existence of the output, not on modification times, so that refreshing an earlier step's output does not silently invalidate a later step's expensive work. A checkpointed step that fails partway SHALL leave no completion marker, and the next run SHALL re-execute it from the beginning.

A **resumable** step SHALL always execute, and SHALL read its own output to determine what remains. Such a step SHALL record each unit of work only once that unit is complete, so an interrupted run repeats at most one unit. A resumable step SHALL perform no work and SHALL contact no external service when its output is already complete.

A step SHALL be resumable only when its work divides into units that are individually cheap to repeat and expensive to lose. `build_vinci_toll_booths`, `build_vinci_prices`, and `build_vinci_direct_prices` are resumable; every other step is checkpointed.

`build_vinci_direct_prices` SHALL read two outputs to determine what remains — the price file for the pairs it has priced, and the rejection database for the pairs it has ruled out. Its unit of work is one pair, and it repeats at most 25 of them.

#### Scenario: Re-running a completed pipeline

- **WHEN** `make all` is run a second time with every output already present and complete
- **THEN** no step performs work again, and no request is issued to any external service

#### Scenario: Earlier output is touched

- **WHEN** the downloaded extract's modification time becomes newer than the OSRM graph
- **THEN** the OSRM preprocessing step is still skipped

#### Scenario: A single output is deleted

- **WHEN** `data/route_set.yaml` is deleted and `make all` is run
- **THEN** the route set step re-executes, and no earlier step does

#### Scenario: A step fails midway

- **WHEN** a checkpointed step fails partway through
- **THEN** its completion marker is not written, and the next run re-executes that step from the beginning

#### Scenario: A resumable step fails midway

- **WHEN** `build_vinci_toll_booths` fails partway through
- **THEN** the next run continues from the work its output already records, rather than starting over

#### Scenario: A resumable step with a complete output

- **WHEN** `make all` is run and `data/vinci_toll_booth.yaml` already covers every route
- **THEN** the step executes, finds nothing outstanding, and finishes without issuing a request

#### Scenario: The pricing step resumes

- **WHEN** `build_vinci_prices` fails partway through
- **THEN** the next run submits only the routes its output does not already record

#### Scenario: The direct pricing step resumes

- **WHEN** `build_vinci_direct_prices` fails partway through
- **THEN** the next run routes only the pairs its price file and its rejection database do not already record

### Requirement: The gare service subscription key is configured via .env

The subscription key for the toll operator's placemark service SHALL be read from an `.env` file as `ULYS_SUBSCRIPTION_KEY` and SHALL be passed into the builder container through the Compose service's `environment` declaration. Exporting the variable on the host is not sufficient on its own: a container receives only the variables Compose declares for it.

The key SHALL NOT be committed. `.env.example` SHALL name the variable without a value.

The pipeline SHALL fail with a clear message naming the missing variable when `ULYS_SUBSCRIPTION_KEY` is unset, before the step issues any request and before it does any routing work.

#### Scenario: Configured key reaches the container

- **WHEN** `.env` sets `ULYS_SUBSCRIPTION_KEY` and the gare mapping step runs
- **THEN** the value is visible inside the builder container and authenticates its requests

#### Scenario: Key is not configured

- **WHEN** `ULYS_SUBSCRIPTION_KEY` is unset or empty and the gare mapping step is run
- **THEN** the pipeline stops with a message naming the missing variable, before any request is issued

#### Scenario: Key is not configured for direct pricing

- **WHEN** `ULYS_SUBSCRIPTION_KEY` is unset or empty and `build_vinci_direct_prices` is run
- **THEN** the pipeline stops with a message naming the missing variable, before any pair is routed

#### Scenario: Key is not in version control

- **WHEN** the tracked files are inspected
- **THEN** no subscription key value appears in them, and `.env.example` names the variable with no value

### Requirement: The tariff date is configured via .env

The timestamp submitted with every toll passage SHALL be read from an `.env` file as `ULYS_PASSAGE_DATE` and SHALL be passed into the builder container through the Compose service's `environment` declaration.

`.env.example` SHALL name the variable with a value, since it is a configuration choice rather than a secret.

The pipeline SHALL fail with a clear message naming the missing variable when `ULYS_PASSAGE_DATE` is unset or empty, before the pricing step or the direct pricing step issues any request.

Both steps SHALL submit the same date, so every amount in `data/vinci_price.yaml` describes one tariff schedule whichever step recorded it.

#### Scenario: Configured date reaches the container

- **WHEN** `.env` sets `ULYS_PASSAGE_DATE` and the pricing step runs
- **THEN** the value is visible inside the builder container and appears on every submitted passage

#### Scenario: Date is not configured

- **WHEN** `ULYS_PASSAGE_DATE` is unset or empty and the pricing step is run
- **THEN** the pipeline stops with a message naming the missing variable, before any request is issued

#### Scenario: Date is not configured for direct pricing

- **WHEN** `ULYS_PASSAGE_DATE` is unset or empty and `build_vinci_direct_prices` is run
- **THEN** the pipeline stops with a message naming the missing variable, before any pair is routed

### Requirement: Three steps require network access at run time

The gare mapping step, the pricing step, and the direct pricing step SHALL be the only steps other than `download_pbf` that require network access. Every other step SHALL continue to run offline once the extract is present.

The pricing step SHALL NOT require the routing service. It derives its input from `data/route_set.yaml` and `data/vinci_toll_booth.yaml`, so it runs with the OSRM graph absent.

The direct pricing step SHALL require the routing service as well as the network. It decides which pairs are askable by routing between booths, so it cannot proceed with the OSRM graph absent.

#### Scenario: Offline run of the derivation steps

- **WHEN** `build_osm_toll_booths` and `build_route_set` are run with the extract and the graph present and no network available
- **THEN** both complete successfully

#### Scenario: Gare mapping without network

- **WHEN** `build_vinci_toll_booths` is run with outstanding routes and no network available
- **THEN** it fails with a message naming the unreachable service, and leaves its output valid for a later resume

#### Scenario: Pricing without network

- **WHEN** `build_vinci_prices` is run with outstanding routes and no network available
- **THEN** it fails with a message naming the unreachable service, and leaves its output valid for a later resume

#### Scenario: Pricing without the routing service

- **WHEN** `build_vinci_prices` is run with outstanding routes and the OSRM instance stopped
- **THEN** it completes normally

#### Scenario: Direct pricing without network

- **WHEN** `build_vinci_direct_prices` is run with outstanding pairs and no network available
- **THEN** it fails with a message naming the unreachable service, and leaves both its outputs valid for a later resume

#### Scenario: Direct pricing without the routing service

- **WHEN** `build_vinci_direct_prices` is run with outstanding pairs and the OSRM instance stopped
- **THEN** it fails with a message naming the unreachable routing service, before any rate request is issued

### Requirement: Eight named build steps

The pipeline SHALL expose exactly eight named steps — `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, `build_vinci_prices`, `build_booth_sides`, and `build_vinci_direct_prices` — each individually invocable, and SHALL provide an `all` target that runs them in that order.

The seventh step SHALL run after the sixth, and the eighth after the seventh. The seventh reads the `enter`/`exit` roles the sixth records, and the eighth reads both the price file and the sides the seventh settles.

#### Scenario: Running the whole pipeline

- **WHEN** `make all` is run in a clean checkout
- **THEN** the eight steps execute in the order `download_pbf`, `setup_osrm`, `build_osm_toll_booths`, `build_route_set`, `build_vinci_toll_booths`, `build_vinci_prices`, `build_booth_sides`, `build_vinci_direct_prices`

#### Scenario: Running a single step

- **WHEN** `make build_osm_toll_booths` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the gare mapping step alone

- **WHEN** `make build_vinci_toll_booths` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the pricing step alone

- **WHEN** `make build_vinci_prices` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the booth sides step alone

- **WHEN** `make build_booth_sides` is run
- **THEN** that step runs, along with any earlier step whose output is missing

#### Scenario: Running the direct pricing step alone

- **WHEN** `make build_vinci_direct_prices` is run
- **THEN** that step runs, along with any earlier step whose output is missing

### Requirement: The booth sides step needs the graph and not the key

Its position in the order is forced rather than chosen. The step reads the `enter` and `exit` roles from `data/vinci_price.yaml`, which the pricing step produces, so it cannot run before it. It issues no request to the operator, only to the routing service, so it needs the graph and not the subscription key.

The step SHALL be checkpointed on `data/bidirectional_booth_sides.yaml`: its work divides into no resumable units, and a complete run costs about two minutes of local routing.

#### Scenario: The step needs the routing service

- **WHEN** `build_booth_sides` is run with the OSRM instance stopped
- **THEN** it fails with a message naming the unreachable routing service

#### Scenario: The step contacts no operator service

- **WHEN** `build_booth_sides` runs with no network access and the routing service available
- **THEN** it completes normally

#### Scenario: A complete output is skipped

- **WHEN** `data/bidirectional_booth_sides.yaml` is already present
- **THEN** the step is skipped

### Requirement: The booth sides are a published artefact

`data/bidirectional_booth_sides.yaml` SHALL be committed, alongside the booth inventory, the route set, the gare mapping and the price file.

It is derived from the routing graph, which is not in the repository, so a consumer who has only the checkout cannot rebuild it however cheap the step is. That is the same reason the inventory and the route set are carried rather than regenerated, and the opposite of the rejection database, which any consumer with the graph rebuilds in minutes and which no consumer outside the pipeline reads.

#### Scenario: The file is present in a fresh checkout

- **WHEN** the repository is checked out without running the pipeline
- **THEN** `data/bidirectional_booth_sides.yaml` is present under `data/`

#### Scenario: No ignore rule matches it

- **WHEN** the ignore rules are inspected
- **THEN** none of them matches `data/bidirectional_booth_sides.yaml`

### Requirement: Blacklisted nodes are impassable in the routing graph

The OSRM setup step SHALL copy the car profile out of the routing image, patch it so that every node listed in `data/nodes_blacklist.yaml` is an impassable barrier, and run `osrm-extract` against the patched copy.

Enforcing it in the profile rather than afterwards is the point. A filter applied to a returned route establishes only that the fastest route is undrivable; it does not ask what the fastest drivable route is, so a booth whose only approach crosses a defect becomes unreachable rather than reached another way. An impassable node makes the router answer the question that was actually being asked.

The unpatched profile SHALL NOT be used. The patch SHALL be applied to a copy, leaving the image untouched.

#### Scenario: A route never uses a blacklisted node

- **WHEN** the graph is built and any route is requested
- **THEN** no returned route traverses a node listed in `data/nodes_blacklist.yaml`

#### Scenario: A destination beyond a blacklisted node is still reached

- **WHEN** a destination's shortest approach crosses a blacklisted node and another approach exists
- **THEN** a route to it is returned by the other approach

#### Scenario: The patch is applied to a copy

- **WHEN** the setup step runs
- **THEN** the profile inside the routing image is unmodified

### Requirement: The blacklist is configuration in its own file

`data/nodes_blacklist.yaml` SHALL hold the node ids, as a list under a single `nodes_blacklist` key, and SHALL be the only file that carries them. A missing file SHALL be treated as an empty list.

Each entry states that the map is wrong at that node — a connection that is not there on the ground. It is a bridge until the extract carries the upstream fix, not a routing preference, and each entry SHALL record what is wrong and be removed once the fix lands.

It SHALL be read by the OSRM setup step alone. It is a fact about the road graph rather than about toll booths, and no step that reasons about booths has any use for it once the graph enforces it.

The file SHALL be committed, so that a graph built from this repository is the graph its outputs were produced against.

#### Scenario: The file is read by the setup step

- **WHEN** the pipeline runs
- **THEN** only the OSRM setup step reads `data/nodes_blacklist.yaml`

#### Scenario: A missing file is empty, not an error

- **WHEN** `data/nodes_blacklist.yaml` is absent and the setup step runs
- **THEN** it completes, patching nothing

#### Scenario: A malformed entry stops the step

- **WHEN** the file carries a value that is not an integer node id
- **THEN** the setup step stops and names the value, before any preprocessing begins

### Requirement: A gate is passable only where a through-road carries it

The patched routing profile SHALL treat a `barrier=gate` or `barrier=lift_gate` node as an impassable barrier unless at least one OSM way carrying that node has a `highway` value in the allowed set:

- `motorway`, `motorway_link`
- `trunk`, `trunk_link`
- `primary`, `primary_link`
- `secondary`, `secondary_link`
- `tertiary`, `tertiary_link`
- `unclassified`
- `residential`
- `living_street`

Where an allowed class carries the node, the gate SHALL keep the profile's configured barrier penalty, exactly as before.

Such a gate is locked on the ground. The stock profile lets any vehicle through one for a fixed penalty, so the router leaves a toll road by an access track and returns a route nobody can drive. Every step downstream trusts the router, so an undrivable route is priced, probed and published as a real one.

Any way is enough, rather than every way. A gate tagged on the node where a driveway meets a residential street would otherwise cut the street, which is a worse error than leaving the driveway open — and the driveway is already discouraged by its class and usually closed by its access tag.

The rule SHALL apply to the barrier penalty path alone. A node whose access tag resolves SHALL keep stock behaviour, so `access=no` closes it and `access=yes` opens it whatever class carries it.

The set of gate values the rule governs SHALL be taken from the pristine profile's own barrier penalty table rather than restated, so a profile that penalises a different set announces itself instead of being patched wrongly.

#### Scenario: A gate on a service road is impassable

- **WHEN** the graph is built and a route would pass a `barrier=gate` node carried only by `highway=service` ways
- **THEN** no returned route traverses that node

#### Scenario: A gate on a through-road still costs only the penalty

- **WHEN** a `barrier=gate` node is carried by a `highway=residential` way and a route passes it
- **THEN** the route traverses the node and is charged the profile's barrier penalty

#### Scenario: A gate on a link road is open

- **WHEN** a `barrier=lift_gate` node is carried by a `highway=motorway_link` way
- **THEN** a route may traverse it

#### Scenario: A gate on a junction of an allowed and a disallowed way is open

- **WHEN** a gate node is carried by both a `highway=residential` way and a `highway=service` + `service=driveway` way
- **THEN** a route may traverse it, and the residential street stays routable through that node

#### Scenario: An access tag still decides on its own

- **WHEN** a `barrier=gate` node carried only by `highway=service` ways also carries `access=yes`
- **THEN** the class rule does not apply to it and stock behaviour decides

#### Scenario: A route off the toll network through a locked gate no longer exists

- **WHEN** a route between two points whose fastest path left a toll road through a gated service road is requested
- **THEN** the returned route does not use that gate, and is the fastest path that avoids it

#### Scenario: The gate values come from the profile

- **WHEN** the pristine profile carries no barrier penalty table
- **THEN** the setup step stops and says so, before any preprocessing begins

### Requirement: The gate classes are derived from the extract

The setup step SHALL determine which gate nodes an allowed class carries by reading `data/france-latest.osm.pbf`, the same extract the graph is built from.

It SHALL NOT be a file in the repository. The answer is a fact about the extract, not a decision anyone makes, and an extract and a committed list of node ids drift apart silently.

The step SHALL report how many gate nodes it found and how many an allowed class carries, so a scan that read nothing is visible before forty minutes of preprocessing follow it.

#### Scenario: The set is derived, not stored

- **WHEN** the repository is inspected after a graph is built
- **THEN** no file under `data/` holds the gate node ids

#### Scenario: The scan is reported

- **WHEN** the setup step runs
- **THEN** it prints the number of gate nodes seen and the number an allowed class carries, before `osrm-extract` starts

#### Scenario: The scan and the graph read one extract

- **WHEN** the setup step runs
- **THEN** the file it scans is the file `osrm-extract` is given

### Requirement: Editing the blacklist invalidates the graph

The OSRM setup stamp SHALL depend on `data/nodes_blacklist.yaml` and on `builder/patch_car_profile.py`. Editing either SHALL cause the next run to re-run extract, partition and customize.

The dependency is on content rather than existence, unlike every other prerequisite of that step. The graph *is* the blacklist and the gate rule once they are compiled in, so a stale graph would silently keep routing over a node the profile says is impassable — which is worse than the thirty to forty minutes the rebuild costs.

The step SHALL state, before it begins, which of the two changed and that preprocessing will take that long, so the cost is never a surprise.

Because the step is now re-runnable, it SHALL restart the routing service after building, and SHALL remove every file of any previous graph before building.

`osrm-routed` maps the graph at startup and a running container is left alone by `compose up -d`, so replacing the files beneath a live server leaves it answering from the old graph — with answers that look entirely normal. That is not a hypothetical: it is how a blacklisted node kept appearing in routes after it had been compiled out.

 `osrm-extract` and `osrm-partition` write some files and reuse others, so a survivor from an earlier graph would be silently mixed into the new one — a case that did not arise while the step ran once and never again.

#### Scenario: A changed blacklist rebuilds the graph

- **WHEN** `data/nodes_blacklist.yaml` is edited and `make` is run
- **THEN** extract, partition and customize run again

#### Scenario: A changed patch script rebuilds the graph

- **WHEN** `builder/patch_car_profile.py` is edited and `make` is run
- **THEN** extract, partition and customize run again

#### Scenario: An unchanged blacklist rebuilds nothing

- **WHEN** the blacklist and the patch script are untouched and `make` is run against a complete graph
- **THEN** the setup step is skipped

#### Scenario: A previous graph is cleared before rebuilding

- **WHEN** the setup step runs and `$(OSRM_OPTIMAL_PATH)` holds files from an earlier graph
- **THEN** every `france-latest.osrm*` file and the patched profile are removed before anything is built

#### Scenario: A killed run leaves nothing usable behind

- **WHEN** a previous run was killed partway and left some graph files
- **THEN** the next run removes them rather than reusing any

#### Scenario: A live routing service is restarted onto the new graph

- **WHEN** the setup step rebuilds the graph while `osrm-optimal` is running
- **THEN** it restarts that service, so no later step queries the old graph

#### Scenario: The cost is announced

- **WHEN** the setup step re-runs because the blacklist or the patch script changed
- **THEN** it says so, and states the expected duration, before starting
