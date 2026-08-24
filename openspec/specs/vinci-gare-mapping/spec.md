# vinci-gare-mapping Specification

## Purpose
Defines how each OSM toll booth group in the inventory is resolved to the toll operator's own gare identifier, by replaying the generated route set against the VINCI Ulys placemark service, and defines the format and resume contract of `data/vinci_toll_booth.yaml`.

## Requirements

### Requirement: Gare lookup is driven by the generated route set

The system SHALL obtain gare identifiers by submitting the driving geometry of each route in `data/route_set.yaml` to the Ulys placemark service, and SHALL NOT synthesise routes of its own. Route geometry SHALL be obtained from the project's own OSRM instance, as a full-overview encoded polyline at precision 6.

A simplified overview SHALL NOT be used: it discards vertices and displaces the line from the carriageway, which costs matches.

#### Scenario: Every route is submitted

- **WHEN** the step runs against a route set it has not processed
- **THEN** it submits one request per route entry, using that route's `from` and `to` endpoints

#### Scenario: Geometry comes from the project instance

- **WHEN** a route's geometry is requested
- **THEN** it is obtained from the project's own OSRM instance, so the traversed booths agree with that route's recorded `covers`

#### Scenario: Full overview is used

- **WHEN** a route geometry is requested for submission
- **THEN** it is the full-overview geometry, not a simplified one

### Requirement: Response geometry decodes at precision 5

Placemark point geometry in the response SHALL be decoded as an encoded polyline at precision 5, even though the submitted geometry is at precision 6. The `precision` request parameter governs the request body only.

#### Scenario: Response point decodes to a French coordinate

- **WHEN** a placemark's point geometry is decoded
- **THEN** the result lies in metropolitan France, rather than the several-degree offset that decoding at precision 6 produces

### Requirement: Correspondence between a placemark and a booth group

A placemark SHALL be said to correspond to a booth group when a node belonging to that group lies within that group's match threshold of the placemark's decoded position, and that group appears in the `covers` list of the route the placemark was returned for.

The threshold SHALL be **2.5 metres** for a group whose booths are `barrier=toll_booth`, and **10 metres** for a group whose booths are `highway=toll_gantry`. A gantry is a portal spanning the carriageway with no lane node for either dataset to anchor on, so the two disagree by several metres where a barrier lane agrees to within two. No group mixes the two kinds.

Distance SHALL be measured against **every** member of the group, representatives and aliases alike. The representative is the numerically smallest node id and is an arbitrary lane, so the nearest member is frequently an alias.

Correspondence SHALL NOT be decided by the gare's name. Operator names and OSM names disagree routinely.

When no covered group corresponds by position, the system SHALL fall back to the gares stated by hand in the override file: a covered group whose `vinci` entry carries the placemark's operator number corresponds to it. Some operators place a gare tens of metres from any lane a route drives, which no threshold can reach without reaching a wrong answer first. Exactly one such group SHALL match; two or more SHALL stop the step.

#### Scenario: A displaced gare is resolved by hand

- **WHEN** a placemark corresponds to no covered group by position, and exactly one covered group states that operator number in the override file
- **THEN** it corresponds to that group

#### Scenario: Two groups state the same gare

- **WHEN** a placemark corresponds to no covered group by position, and two covered groups state that operator number
- **THEN** the step stops and names both

#### Scenario: A placemark corresponds to a covered group

- **WHEN** a placemark's position lies within that group's threshold of a node belonging to a group in that route's `covers`
- **THEN** that placemark corresponds to that group

#### Scenario: The nearest member is an alias

- **WHEN** the nearest node to a placemark is an alias rather than its group's representative
- **THEN** the placemark still corresponds to that alias's group

#### Scenario: A group beyond the threshold does not correspond

- **WHEN** the nearest node of a covered booth group lies more than 2.5 metres from a placemark
- **THEN** that group does not correspond to that placemark

#### Scenario: A gantry matches at a distance a booth would not

- **WHEN** a placemark lies 7 metres from a covered group whose booth is a toll gantry
- **THEN** it corresponds to that group, because the gantry threshold is 10 metres

#### Scenario: Names are not consulted

- **WHEN** a placemark's name and the OSM `name` tag of the corresponding booth differ entirely
- **THEN** correspondence is unaffected, because it rests on position alone

#### Scenario: A group not on this route does not correspond

- **WHEN** a booth group lies within its threshold of a placemark but is absent from that route's `covers`
- **THEN** it does not correspond to that placemark

### Requirement: A placemark that corresponds to nothing is an error

When a placemark corresponds to no group, the system SHALL stop and report the failure. It SHALL NOT record the placemark against the closest group regardless of distance, and SHALL NOT silently discard it.

The report SHALL name the placemark's operator identifier, its preview name, its decoded position, the route that produced it, and the nearest booth in the inventory and the nearest booth excluded from the inventory, each with its distance. An unmatched placemark most often means the inventory's through-road filter dropped a real gare, and the report SHALL carry enough detail to establish that without a second run.

#### Scenario: No covered group is close enough

- **WHEN** a placemark has no covered group within its threshold
- **THEN** the step stops and reports the placemark, the route, and the nearest inventory and excluded booths with their distances

#### Scenario: The gare was excluded from the inventory

- **WHEN** a route passes a gare whose OSM node the through-road filter excluded
- **THEN** the step stops rather than attributing that gare to a different booth

### Requirement: An ambiguous placemark is an error

When two or more covered groups lie within their thresholds of one placemark, the system SHALL stop and report the ambiguity rather than choose between them.

#### Scenario: Two covered groups are within the threshold

- **WHEN** a placemark has two covered groups within their thresholds
- **THEN** the step stops and names both groups and the placemark

### Requirement: Gares are identified by their operator number

The system SHALL record each booth group's gare as the operator number and preview name the placemark carries. The per-placemark `Code`, which appends an opaque identifier distinguishing the two directions of travel through one gare, SHALL NOT be recorded: a tariff is a property of the gare, not of the direction, and two groups legitimately share one gare.

#### Scenario: Opposite carriageways of one gare

- **WHEN** two routes traverse opposite directions of the same gare
- **THEN** both booth groups record the same operator number and name

#### Scenario: One gare over many groups

- **WHEN** the mapping is inspected
- **THEN** an operator number may appear against more than one booth group, which is the ordinary two-carriageway case and not an error

#### Scenario: The same gare on two routes

- **WHEN** two different routes traverse the same gare
- **THEN** the second records no change

### Requirement: Mapping output format

The system SHALL write `data/vinci_toll_booth.yaml` as a mapping with two top-level keys.

`toll_booths` SHALL map every booth group representative observed so far to a mapping carrying `id`, the gare's operator number, and `name`, its preview name. A value SHALL NEVER be null: a booth either has a gare or the run fails.

`routes` SHALL list the routes already queried, each as a mapping with `from` and `to`.

```yaml
toll_booths:
  26410440:
    id: "04220"
    name: "LANCON"
routes:
  - from: 547958
    to: 26692263
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

#### Scenario: A completed run is stable

- **WHEN** the step runs a second time against an unchanged route set and a complete mapping
- **THEN** the file is unchanged

### Requirement: The step resumes from its own output

The system SHALL skip any route already listed under `routes` and SHALL issue no request for it. A route SHALL be added to `routes` only after its response has been processed in full, so an interrupted run repeats at most one route.

A run against a complete mapping SHALL issue no requests at all.

#### Scenario: An interrupted run continues

- **WHEN** the step is interrupted partway and started again
- **THEN** it queries only the routes absent from `routes`

#### Scenario: A completed run is a no-op

- **WHEN** the step runs with every route already listed under `routes`
- **THEN** it issues no requests to the placemark service

#### Scenario: A route is recorded only once processed

- **WHEN** the step fails while handling a route's response
- **THEN** that route is absent from `routes`, and the next run queries it again

### Requirement: A recorded gare is never revised

Once a booth group has a gare recorded, the system SHALL NOT write a different operator number for it, and SHALL stop and report the conflict instead. Recording the same operator number again SHALL succeed and change nothing.

#### Scenario: The same gare is seen again

- **WHEN** a later route reports the same operator number for a group already recorded with it
- **THEN** the mapping is unchanged and the run continues

#### Scenario: A conflicting gare

- **WHEN** a later route reports a different operator number for a group already recorded
- **THEN** the step stops and reports both values and the routes that produced them

### Requirement: Every covered booth must have a gare

When every route has been processed, every booth group that a processed route drove through SHALL have a gare recorded, or the step SHALL fail. Recording nothing for such a booth would publish a mapping that quietly claims less than the operator charges.

Two kinds of booth SHALL be exempt: one the override file marks with an `absent_*` type, because the operator does not carry it and there is no gare to find; and one that is no longer in the inventory, because the route set names booths that a later `type: ignore` has since removed and those are not the mapping's to resolve.

The check SHALL run on every invocation, including one that finds no outstanding routes. A run that skipped the check when there was no work would report success over a mapping known to be incomplete.

The failure SHALL name every unmapped booth in a table carrying its node page, its name, whether it is a booth or a gantry, how many routes drive through it, and the nearest gare that was mapped with the distance to it. Each column points at a different remedy, and without them the reader cannot tell a private site from a displaced gare from an operator that reports nothing at all.

#### Scenario: A covered booth with no gare

- **WHEN** every route has been processed and some booth a route drove through has no gare
- **THEN** the step fails and tabulates every such booth

#### Scenario: A booth the operator does not carry

- **WHEN** an unmapped booth is marked with an `absent_*` type in the override file
- **THEN** it is not reported and does not fail the run

#### Scenario: A booth removed since the route set was built

- **WHEN** the route set names a booth that an override has since removed from the inventory
- **THEN** it is not reported, and the route set need not be regenerated for the mapping to be correct

#### Scenario: The check runs with nothing outstanding

- **WHEN** the step is re-run with every route already processed
- **THEN** it issues no request and still reports any unmapped booth

### Requirement: The inventory must reflect the overrides

The step SHALL verify that `data/osm_toll_booths.yaml` reflects the override file, and SHALL stop and name the drifted entries when it does not.

`type: ignore` and `parent_id` are applied by the extraction step, and the override file is deliberately not a prerequisite of the inventory. Nothing else would notice that the inventory predates an override edit, and the booth would reappear in the report with no explanation.

The failure SHALL name each drifted entry and the command that rebuilds the inventory.

#### Scenario: An ignored booth is still in the inventory

- **WHEN** the override file ignores a booth that the inventory still carries
- **THEN** the step stops, names that booth, and gives the command to rebuild the inventory

#### Scenario: A forced booth is in the wrong group

- **WHEN** the override file forces a booth into a group and the inventory puts it in another
- **THEN** the step stops and names both groups

### Requirement: An empty response means the route has no tolls

An empty placemark list SHALL be treated as a valid answer and not as a failure. Nothing SHALL be recorded for that route's booths, and the route SHALL be added to `routes`. Whether those booths ever get a gare is settled by the other routes that drive through them, and by the end-of-run check.

#### Scenario: Route with no gares

- **WHEN** the service returns an empty list for a route
- **THEN** the route is marked as processed and nothing is recorded for its booths

### Requirement: Request rate and retries

The system SHALL issue no more than one request per second to the placemark service, and SHALL issue requests on a single thread.

A failed request SHALL be retried up to five times with exponential backoff. When every attempt for a route fails, the step SHALL stop and report the route; it SHALL NOT record that route's groups as `null` and SHALL NOT mark the route as processed.

#### Scenario: Requests are spaced

- **WHEN** two consecutive requests are issued
- **THEN** at least one second separates them

#### Scenario: A transient failure recovers

- **WHEN** a request fails and a later attempt succeeds
- **THEN** the response is processed normally and the run continues

#### Scenario: Retries are exhausted

- **WHEN** all five attempts for one route fail
- **THEN** the step stops, names the route, and leaves that route absent from `routes`

### Requirement: The override file is an input to this step

The step SHALL read `data/osm_toll_booths_overrides.yaml` and consume the `vinci` entries and the `absent_*` types from it. A `vinci` entry SHALL be recorded for its booth whether or not any placemark ever needed it.

A `vinci` entry that no placemark needed SHALL be reported, and SHALL NOT fail the run: the booth may simply not lie on any route this run covered. It SHALL NOT be reported on a run that had no outstanding routes, where nothing is consumed by definition.

#### Scenario: A hand-stated gare is recorded regardless

- **WHEN** a `vinci` entry names a booth and no placemark ever falls back to it
- **THEN** that booth still carries the stated gare in the mapping

#### Scenario: An unneeded hand-stated gare is reported

- **WHEN** a run processes every route and some `vinci` entry was never needed
- **THEN** the step reports it and still succeeds

### Requirement: The subscription key is configuration

The subscription key for the placemark service SHALL be read from the environment and SHALL NOT be embedded in the pipeline scripts or the container image. The step SHALL fail with a message naming the missing variable before issuing any request when the key is unset.

#### Scenario: Key is configured

- **WHEN** the key is set in the environment
- **THEN** the step authenticates its requests with it

#### Scenario: Key is missing

- **WHEN** the key is unset or empty
- **THEN** the step stops with a message naming the variable, before any request and before any routing work

### Requirement: A route paying one gare twice is an error unless it is stated to be legitimate

A route SHALL NOT have two booth groups in its `covers` list that resolve to the same operator gare, unless that gare is named in the override file as one a route may legitimately pay twice. When an unnamed gare is paid twice, the step SHALL fail.

A gare's booths are its carriageways, so reaching two of them usually means the trip left the road and returned on the opposite side. That is what an endpoint the router places on the carriageway itself produces, and the toll such a route reports is charged once and recorded twice.

It is not always wrong. Where the road that would let a driver carry on does not exist yet, coming back through the same gare is the fastest route there is, and the operator charges it twice. Such a gare SHALL be nameable in the override file, and a route paying it twice SHALL then pass.

The exemption SHALL be stated per gare rather than per route. A route is identified by its endpoints, which are re-derived on every rebuild of the route set, so a route-keyed exemption would go stale almost immediately; the gare is stable.

An exemption that no route actually exercises SHALL be reported, so that a case which has since stopped occurring is visible rather than silently carried. It SHALL NOT fail the run.

The check SHALL run on every invocation, including one that finds no outstanding routes, for the same reason the unmapped-booth check does: a run that skipped it would report success over a mapping known to be wrong.

The failure SHALL name every offending route by its `from` and `to` endpoints, the gare paid twice by its operator number and name, and each booth group involved by its node page, so the reader can tell which endpoint put the route on the wrong road.

#### Scenario: A route traverses both carriageways of one gare

- **WHEN** a route's `covers` list holds two booth groups that map to the same gare, and that gare is not named as payable twice
- **THEN** the step fails and names the route, the gare, and both booth groups

#### Scenario: A gare that a route may legitimately pay twice

- **WHEN** a route pays a gare twice because the road that would let it carry on is not built, and that gare is named in the override file
- **THEN** the check passes and the step reports its mapping as usual

#### Scenario: A route paying each gare once

- **WHEN** every route's `covers` list maps each gare it meets to exactly one booth group
- **THEN** the check passes and the step reports its mapping as usual

#### Scenario: An exemption nothing exercises

- **WHEN** a gare is named as payable twice but no route pays it twice
- **THEN** the step reports that exemption and still succeeds

#### Scenario: Operator numbers keep their leading zeros

- **WHEN** an exemption names a gare whose operator number begins with a zero
- **THEN** it matches that gare, and is not read as a smaller number with the zero dropped

#### Scenario: The check runs with nothing outstanding

- **WHEN** the step is re-run with every route already processed
- **THEN** it issues no request and still fails on any route that pays one gare twice

#### Scenario: Booths without a gare are not compared

- **WHEN** a route covers booths that have no gare recorded because an override marks them absent
- **THEN** those booths take no part in the comparison and do not trigger a failure
