## ADDED Requirements

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

### Requirement: Editing the blacklist invalidates the graph

The OSRM setup stamp SHALL depend on `data/nodes_blacklist.yaml`. Editing the list SHALL cause the next run to re-run extract, partition and customize.

The dependency is on content rather than existence, unlike every other prerequisite of that step. The graph *is* the blacklist once it is compiled in, so a stale graph would silently keep routing over a node the file says is impassable — which is worse than the thirty to forty minutes the rebuild costs.

The step SHALL state, before it begins, that the blacklist changed and that preprocessing will take that long, so the cost is never a surprise.

Because the step is now re-runnable, it SHALL restart the routing service after building, and SHALL remove every file of any previous graph before building.

`osrm-routed` maps the graph at startup and a running container is left alone by `compose up -d`, so replacing the files beneath a live server leaves it answering from the old graph — with answers that look entirely normal. That is not a hypothetical: it is how a blacklisted node kept appearing in routes after it had been compiled out.

 `osrm-extract` and `osrm-partition` write some files and reuse others, so a survivor from an earlier graph would be silently mixed into the new one — a case that did not arise while the step ran once and never again.

#### Scenario: A changed blacklist rebuilds the graph

- **WHEN** `data/nodes_blacklist.yaml` is edited and `make` is run
- **THEN** extract, partition and customize run again

#### Scenario: An unchanged blacklist rebuilds nothing

- **WHEN** the blacklist is untouched and `make` is run against a complete graph
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

- **WHEN** the setup step re-runs because the blacklist changed
- **THEN** it says so, and states the expected duration, before starting
