## ADDED Requirements

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

## MODIFIED Requirements

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
