## ADDED Requirements

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
