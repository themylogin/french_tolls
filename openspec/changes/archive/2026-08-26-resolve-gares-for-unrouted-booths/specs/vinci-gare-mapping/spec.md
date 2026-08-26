## ADDED Requirements

### Requirement: A booth no route reaches is resolved by a stub leg

Some booths lie on a trip that ends outside France, so no pair of French place nodes produces a route through them and the route set cannot reach them. Such a booth is named by hand in the override file with `type: enter`, `type: exit`, or `type: passthrough`, and the inventory publishes its `passage`.

For every such booth, the system SHALL submit a three-point leg formed from the first element of its `passage`, the booth's own `latlon`, and the second element of its `passage`, in that order. The leg SHALL be encoded as a polyline at precision 6 and submitted to the placemark service in the same way a route geometry is.

The leg SHALL be built from the published positions alone. It SHALL NOT be routed, because the router is what could not reach these booths, and because the routing profile closes barriers that a leg through the booth must cross.

A stub leg SHALL be submitted for every border-typed booth, whether or not a route also covers it. Where both resolve the same booth, the existing rule that a recorded gare is never revised settles the two against each other.

#### Scenario: A stub leg is submitted for an unreachable booth

- **WHEN** the step runs and a border-typed booth has no gare recorded
- **THEN** it submits one leg of three points, formed from that booth's `passage` and its `latlon`

#### Scenario: The leg is not routed

- **WHEN** a stub leg is built
- **THEN** it is the two published passage positions with the booth's position between them, and no routing request is made for it

#### Scenario: A border-typed booth a route also covers

- **WHEN** a border-typed booth lies on a route in the route set and the stub reports a different gare
- **THEN** the step stops and reports the conflict, as it would for two routes disagreeing

### Requirement: A stub leg corresponds to exactly one booth group

A placemark returned for a stub leg SHALL correspond to the booth group that leg was built for, and to no other. Correspondence SHALL be decided by the same rules a route's placemark is decided by: position within that group's match threshold against every member of the group, with the hand-stated gare in the override file as the fallback when no member is close enough.

The group the leg was built for SHALL be the only candidate. A stub leg carries no `covers` list, because it is not a trip anyone drives and nothing computed what it crosses. Admitting any other group would let a leg record a neighbouring plaza's gare, which several of these booths sit within a few hundred metres of.

Exactly one placemark SHALL correspond to the booth. A leg that returns no placemark, and a leg whose placemarks all correspond to nothing, SHALL stop the step and name the booth: the booth was stated by hand to be real, so an operator that reports nothing for it means the statement or the passage is wrong.

A placemark that corresponds to nothing SHALL stop the step under the existing rule, with the booth named in place of a route.

#### Scenario: The stub resolves its booth

- **WHEN** a stub leg returns one placemark within the booth group's threshold
- **THEN** that group records the placemark's operator number and preview name

#### Scenario: The nearest member is an alias

- **WHEN** the placemark returned for a stub leg lies within the threshold of an alias of the group the leg was built for
- **THEN** it corresponds to that group

#### Scenario: A neighbouring plaza's gare is not accepted

- **WHEN** a stub leg returns a placemark that lies beyond the threshold of every member of its booth's group
- **THEN** the step stops rather than record that gare against the booth

#### Scenario: The operator reports nothing

- **WHEN** a stub leg returns no placemark at all
- **THEN** the step stops and names the booth

#### Scenario: A displaced gare is resolved by hand

- **WHEN** a stub leg's placemark lies beyond every threshold and the booth's `vinci` entry carries that operator number
- **THEN** it corresponds to that booth

### Requirement: Every border-typed booth must have a gare

When the step completes, every booth the override file types `enter`, `exit`, or `passthrough` SHALL have a gare recorded, or the step SHALL fail and name it.

The check SHALL run on every invocation, including one that finds no outstanding work, for the same reason the covered-booth check does: a run that skipped it would report success over a mapping known to be incomplete.

A booth typed `absent_*` is not border-typed and takes no part in this check. The two statements are different: `absent_*` says the operator does not carry the booth, and a border type says the route set cannot reach it.

#### Scenario: A border-typed booth with no gare

- **WHEN** the step completes and some border-typed booth has no gare recorded
- **THEN** the step fails and names that booth

#### Scenario: The check runs with nothing outstanding

- **WHEN** the step is re-run with every route and every stub already processed
- **THEN** it issues no request and still reports any border-typed booth without a gare

#### Scenario: Every representative is accounted for

- **WHEN** the step completes successfully
- **THEN** every group representative in the inventory either carries a gare or is typed `absent_*` in the override file

## MODIFIED Requirements

### Requirement: Gare lookup is driven by the generated route set

The system SHALL obtain gare identifiers by submitting the driving geometry of each route in `data/route_set.yaml` to the Ulys placemark service. Route geometry SHALL be obtained from the project's own OSRM instance, as a full-overview encoded polyline at precision 6.

A simplified overview SHALL NOT be used: it discards vertices and displaces the line from the carriageway, which costs matches.

The system SHALL NOT invent a trip of its own and submit it as a route. The one exception is the stub leg through a booth the route set cannot reach, which is not a trip and is governed by its own requirements: it is built from published positions rather than routed, it resolves one named booth rather than whatever it crosses, and it is never added to `data/route_set.yaml`.

#### Scenario: Every route is submitted

- **WHEN** the step runs against a route set it has not processed
- **THEN** it submits one request per route entry, using that route's `from` and `to` endpoints

#### Scenario: Geometry comes from the project instance

- **WHEN** a route's geometry is requested
- **THEN** it is obtained from the project's own OSRM instance, so the traversed booths agree with that route's recorded `covers`

#### Scenario: Full overview is used

- **WHEN** a route geometry is requested for submission
- **THEN** it is the full-overview geometry, not a simplified one

#### Scenario: The route set is not extended

- **WHEN** the step submits a stub leg for a booth the route set cannot reach
- **THEN** `data/route_set.yaml` is unchanged, because a stub is neither a drivable trip nor a coverage claim

### Requirement: An empty response means the route has no tolls

An empty placemark list for a **route** SHALL be treated as a valid answer and not as a failure. Nothing SHALL be recorded for that route's booths, and the route SHALL be added to `routes`. Whether those booths ever get a gare is settled by the other routes that drive through them, and by the end-of-run check.

An empty placemark list for a **stub leg** SHALL NOT be treated as a valid answer. A route may lawfully cross no toll at all, but a stub exists only because a booth was stated by hand to be there.

#### Scenario: Route with no gares

- **WHEN** the service returns an empty list for a route
- **THEN** the route is marked as processed and nothing is recorded for its booths

#### Scenario: Stub with no gares

- **WHEN** the service returns an empty list for a stub leg
- **THEN** the step stops and names the booth, and the stub is not marked as processed

### Requirement: Mapping output format

The system SHALL write `data/vinci_toll_booth.yaml` as a mapping with two top-level keys.

`toll_booths` SHALL map every booth group representative observed so far to a mapping carrying `id`, the gare's operator number, and `name`, its preview name. A value SHALL NEVER be null: a booth either has a gare or the run fails.

`routes` SHALL list the work already submitted, each as a mapping with `from` and `to`. A route is recorded as its two endpoint node ids. A stub leg is recorded as its booth's node id in both fields, which no route can produce because a route's endpoints are two distinct place nodes.

```yaml
toll_booths:
  26410440:
    id: "04220"
    name: "LANCON"
routes:
  - from: 547958
    to: 26692263
  - from: 1987610456
    to: 1987610456
```

Keys SHALL be written in a deterministic order, so that re-running a completed step produces an unchanged file.

#### Scenario: Mapping is written

- **WHEN** the step completes
- **THEN** `data/vinci_toll_booth.yaml` parses as YAML with `toll_booths` and `routes` keys

#### Scenario: Every entry carries its gare

- **WHEN** any value in `toll_booths` is inspected
- **THEN** it carries the gare's operator number as `id` and its preview name as `name`

#### Scenario: A file written under the old rule is refused

- **WHEN** an existing mapping file carries a null value
- **THEN** the step stops and says to delete it, rather than interpreting a record written under a rule that no longer holds

#### Scenario: Booth keys are group representatives

- **WHEN** any key in `toll_booths` is looked up in the booth inventory
- **THEN** it is a group representative, never an alias

#### Scenario: A stub is recorded under routes

- **WHEN** a stub leg has been processed
- **THEN** `routes` carries an entry whose `from` and `to` are both that booth's node id

#### Scenario: A completed run is stable

- **WHEN** the step runs a second time against an unchanged route set and a complete mapping
- **THEN** the file is unchanged

### Requirement: The step resumes from its own output

The system SHALL skip any route already listed under `routes` and SHALL issue no request for it. A route SHALL be added to `routes` only after its response has been processed in full, so an interrupted run repeats at most one route.

The same SHALL hold for a stub leg. A stub whose booth appears in `routes` as both `from` and `to` SHALL be skipped, and SHALL be added there only after its response has been processed in full.

A run against a complete mapping SHALL issue no requests at all.

#### Scenario: An interrupted run continues

- **WHEN** the step is interrupted partway and started again
- **THEN** it queries only the routes absent from `routes`

#### Scenario: A completed run is a no-op

- **WHEN** the step runs with every route and every stub already listed under `routes`
- **THEN** it issues no requests to the placemark service

#### Scenario: A route is recorded only once processed

- **WHEN** the step fails while handling a route's response
- **THEN** that route is absent from `routes`, and the next run queries it again

#### Scenario: A stub is recorded only once processed

- **WHEN** the step fails while handling a stub leg's response
- **THEN** that booth is absent from `routes`, and the next run submits the stub again

### Requirement: The inventory must reflect the overrides

The step SHALL verify that `data/osm_toll_booths.yaml` reflects the override file, and SHALL stop and name the drifted entries when it does not.

`type: ignore`, `parent_id`, and the border types are applied by the extraction step, and the override file is deliberately not a prerequisite of the inventory. Nothing else would notice that the inventory predates an override edit, and the booth would reappear in the report with no explanation.

A booth the override file types `enter`, `exit`, or `passthrough` SHALL carry `passage` in the inventory. One that does not is an inventory written before that entry existed, and the step SHALL stop rather than leave the booth unresolved for a reason the report cannot state.

The failure SHALL name each drifted entry and the command that rebuilds the inventory.

#### Scenario: An ignored booth is still in the inventory

- **WHEN** the override file ignores a booth that the inventory still carries
- **THEN** the step stops, names that booth, and gives the command to rebuild the inventory

#### Scenario: A forced booth is in the wrong group

- **WHEN** the override file forces a booth into a group and the inventory puts it in another
- **THEN** the step stops and names both groups

#### Scenario: A border-typed booth carries no passage

- **WHEN** the override file types a booth `enter`, `exit`, or `passthrough` and the inventory entry for it has no `passage`
- **THEN** the step stops, names that booth, and gives the command to rebuild the inventory
