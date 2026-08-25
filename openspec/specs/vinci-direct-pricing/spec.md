# vinci-direct-pricing Specification

## Purpose
Defines how the pipeline prices the entrance/exit tariffs that no route in the route set happened to drive — how the grid of candidate pairs is enumerated, how a route between two booths is judged to have a third booth in the way, what is recorded for a pair that does, how a pair that does not is priced, and the abort and resume contract of the step.

## Requirements

### Requirement: The grid is enumerated from the price file, not from routes

The system SHALL take its source booths and its target booths from `data/vinci_price.yaml` alone, and SHALL NOT read `data/route_set.yaml`.

Source booths SHALL be the groups recorded as `enter` or `bidirectional`. Target booths SHALL be the groups recorded as `exit` or `bidirectional`. A `passthrough` or `gantry` group SHALL never be a source or a target.

A pair SHALL be excluded from the grid when its source and its target are the same group, when they carry the same gare code, and when the override file prohibits that ordered gare pair. Two groups sharing a gare code are the two carriageways of one plaza, and a ticket from a gare to itself is not a journey.

An excluded pair SHALL be dropped before it is routed, and SHALL be recorded in neither output. Exclusion says there is nothing to ask; a rejection says a booth lies between. They are different facts and the outputs keep them apart.

#### Scenario: A gantry is never an endpoint

- **WHEN** the grid is enumerated
- **THEN** no pair has a `gantry` group as its source or its target

#### Scenario: The two carriageways of one plaza are not a pair

- **WHEN** an `enter` group and an `exit` group both carry gare code `03087`
- **THEN** no pair is formed between them

#### Scenario: A bidirectional booth is both a source and a target

- **WHEN** a group is recorded as `bidirectional`
- **THEN** it appears in the grid as a source and as a target, and never paired with itself

#### Scenario: A prohibited gare pair is never asked about

- **WHEN** the override file prohibits the ordered pair `04355` to `04354`
- **THEN** no route is requested and no rate request is issued for a source carrying `04355` and a target carrying `04354`

#### Scenario: A prohibition is directional

- **WHEN** the override file prohibits `04355` to `04354` and not the reverse
- **THEN** a source carrying `04354` and a target carrying `04355` remain in the grid

#### Scenario: The route set is not read

- **WHEN** the step runs with `data/route_set.yaml` absent
- **THEN** it completes normally

### Requirement: A booth in the way is any booth in the inventory

The system SHALL route each pair with the routing service and SHALL read the OSM node ids the route traverses. Each traversed node SHALL be resolved to its booth group through `data/osm_toll_booths.yaml` — a `toll_booths` key resolves to itself, an `aliases` key resolves to its `parent_id`.

A booth lies in the way when a resolved group is neither the pair's source nor its target. Booths with no gare, `gantry` groups, and `passthrough` groups SHALL all count, so a pair whose route crosses one is rejected.

Coverage SHALL be decided by node identity alone. No geometric tolerance and no distance threshold SHALL take part.

The routing service SHALL be queried with the booths' own coordinates. No snapping hint SHALL be required: a booth node lies on the lane it belongs to.

#### Scenario: A barrier between two booths rejects the pair

- **WHEN** the route from a source to a target traverses a `passthrough` group
- **THEN** the pair is rejected

#### Scenario: A gantry between two booths rejects the pair

- **WHEN** the route from a source to a target traverses a `gantry` group
- **THEN** the pair is rejected

#### Scenario: A booth with no gare rejects the pair

- **WHEN** the route traverses a booth group that `data/vinci_toll_booth.yaml` does not carry
- **THEN** the pair is rejected

#### Scenario: A parallel lane counts as its group

- **WHEN** the route traverses a node listed under `aliases`
- **THEN** the group named by that alias's `parent_id` is treated as traversed

#### Scenario: The endpoints do not reject their own pair

- **WHEN** the route traverses the source booth and the target booth and no other
- **THEN** the pair is not rejected

### Requirement: A rejected pair is recorded with the first booth in the way

A rejected pair SHALL be recorded in `data/vinci_routes_rejected.sqlite3` with its source group, its target group, the target's gare code, and the booth group that lies in the way.

When a route crosses several booths, the recorded booth SHALL be the first one in driving order. That is where the ticket would close, so it is the one that explains the rejection.

The record SHALL also carry the route's length in metres.

#### Scenario: A pair crossing several booths names the first

- **WHEN** a route crosses booths B then C between its source and its target
- **THEN** the record names B

#### Scenario: A rejected pair is not priced

- **WHEN** a pair is rejected
- **THEN** no request is issued to the rate service for it, and `data/vinci_price.yaml` gains no entry for it

### Requirement: A gare code is rejected only when every one of its groups is

A target gare code may be carried by more than one booth group. The system SHALL route each of those groups, and SHALL treat the code as unreachable from a given source only when every group carrying it is rejected.

A source and a target code with a price already in `data/vinci_price.yaml` SHALL NOT be routed again.

#### Scenario: One group of a code is reachable

- **WHEN** gare code `04205` is carried by two groups, and the route to the first crosses a booth while the route to the second does not
- **THEN** the pair is priced

#### Scenario: A priced code is not revisited

- **WHEN** a source's `prices` already carries a target's gare code
- **THEN** no route is requested for that pair

### Requirement: A pair with nothing in the way is priced

A pair whose route crosses no other booth SHALL be submitted to the rate service as exactly two passages — the source's gare code followed by the target's gare code — carrying the same tariff date, vehicle category, and payment option that the pricing step uses.

The returned amount SHALL be recorded on the source group under the target's gare code, in the `prices` mapping the price file already defines. The target group SHALL gain no amount, as an exit records none.

#### Scenario: A clean pair is priced

- **WHEN** the route from source group 27174404 to a target carrying gare `03086` crosses no other booth and the service answers 6.80
- **THEN** `data/vinci_price.yaml` records 6.8 on group 27174404 under the key `"03086"`

#### Scenario: The target gains nothing

- **WHEN** a pair is priced
- **THEN** the target group's entry is unchanged

#### Scenario: Exactly two passages are submitted

- **WHEN** any request is issued
- **THEN** it carries the source's gare code and the target's gare code, in that order, and no other passage

### Requirement: A clean pair the operator will not price stops the step

The system SHALL stop, naming the pair and both gare codes, when the rate service returns no amount for a pair the routing service found clean, or returns an answer that does not name the two submitted gares.

A route with no booth in the way describes a ticket the operator must sell. When it does not, the inventory is missing a booth that the route really passes, and the remedy is in the data rather than in the step. Recording the pair as unpriced would bury that.

The stopping pair SHALL be recorded neither as priced nor as rejected, so a later run meets it again.

#### Scenario: The service returns no amount

- **WHEN** the service answers a clean pair with a null price and the comment `No rate found.`
- **THEN** the step stops and names the source group, the target group, and both gare codes

#### Scenario: The answer names a different gare

- **WHEN** a returned item's entrance or exit is not the gare that was submitted
- **THEN** the step stops and names the pair and the item

#### Scenario: Nothing is recorded for the stopping pair

- **WHEN** the step stops on a pair
- **THEN** that pair is absent from `data/vinci_price.yaml` and from the rejection database

### Requirement: An unroutable pair stops the step

The system SHALL stop, naming the pair, when the routing service returns no route between a source and a target. Every booth in the inventory sits on the French road network, so an unroutable pair is a defect in the graph or the inventory rather than a fact about tolls.

#### Scenario: No route exists

- **WHEN** the routing service answers a pair with a code other than `Ok`
- **THEN** the step stops and names the source group and the target group

### Requirement: A price that would change stops the step

The system SHALL stop, naming the pair and both amounts, when the amount returned for a pair differs from one `data/vinci_price.yaml` already records for it. Amounts SHALL be compared exactly, in whole cents.

#### Scenario: A recorded price changes

- **WHEN** a pair already recorded at 6.80 is answered with 7.10
- **THEN** the step stops and names the source group, the target gare, and both amounts

### Requirement: A survey mode collects every stop instead of the first

The system SHALL offer a diagnostic mode that, on a stop condition, records the finding, skips that pair, and continues.

A surveyed pair SHALL be recorded neither as priced nor as rejected, so a later strict run meets it again. A surveyed run SHALL exit with a non-zero status, so a pipeline that completes one is not reported as clean.

Only the stops the step anticipates SHALL be surveyed. A rate request that fails every retry is a transport failure rather than a finding about tolls, and SHALL stop the run in survey mode as in strict mode.

#### Scenario: A survey run continues past a stop

- **WHEN** a pair the router found clean has no tariff and the survey mode is on
- **THEN** the finding is recorded, the pair is skipped, and the next pair is routed

#### Scenario: A surveyed pair is recorded nowhere

- **WHEN** a survey run finishes
- **THEN** every surveyed pair is absent from `data/vinci_price.yaml` and from the rejection database

#### Scenario: A survey run fails

- **WHEN** a survey run records at least one finding
- **THEN** the step exits with a non-zero status

#### Scenario: A transport failure still stops a survey run

- **WHEN** a rate request fails every retry during a survey run
- **THEN** the step stops rather than recording it as a finding

### Requirement: The survey report names both booths, their separation, and the route

The findings SHALL be reported at the end of the run, grouped by kind, each group as a bordered table of the same form the other steps print.

Each row SHALL carry, for both booths, the gare code, the operator's name for it, and a link to the OSM node; the straight-line distance between the two booths; and the length of the route between them.

Rows SHALL be ordered by that straight-line distance, nearest first. Two findings look alike in every other column and want opposite remedies — a pair the operator will not sell because the inventory is missing a booth, and a pair it will not sell because both gares are one interchange — and the separation is what tells them apart.

#### Scenario: A finding is reported with both links

- **WHEN** a pair is surveyed
- **THEN** its row carries a link to the source node and a link to the target node

#### Scenario: Findings are grouped by kind

- **WHEN** a run surveys both a pair with no tariff and a pair with no route
- **THEN** each kind is reported under its own heading in its own table

#### Scenario: The nearest pair is reported first

- **WHEN** a table holds a pair 124 m apart and a pair 374 km apart
- **THEN** the 124 m pair is the first row

### Requirement: Rejections are recorded in a database, not a text file

Rejections SHALL be written to `data/vinci_routes_rejected.sqlite3` one row at a time, each row durable before the next pair is routed.

The step rejects on the order of 237 000 pairs. A format that rewrites its whole content per row would spend far longer writing than the step spends working, so the store SHALL support appending a single row at constant cost and reading the whole set back at startup.

#### Scenario: A rejection survives a kill

- **WHEN** the process is killed immediately after a pair is rejected
- **THEN** the next run finds that pair already rejected

#### Scenario: The store is read once at startup

- **WHEN** the step starts against a full rejection database
- **THEN** it reads every recorded pair and issues no route request for any of them

### Requirement: The step is resumable from its two outputs

The system SHALL determine what remains from `data/vinci_price.yaml` and `data/vinci_routes_rejected.sqlite3` alone, and SHALL keep no cursor, marker, or processed-pair list of its own.

A pair SHALL be skipped when the source's `prices` carries the target's gare code, or when the rejection database carries the pair.

`data/vinci_price.yaml` SHALL be rewritten at least once every 25 prices, and once when the step ends for any reason. An interruption SHALL therefore cost at most 25 rate answers.

A run with nothing outstanding SHALL issue no route request and no rate request.

#### Scenario: Resuming after an interruption

- **WHEN** a run is interrupted and the step is run again
- **THEN** it routes only the pairs neither output records, repeating at most 25 rate requests

#### Scenario: A complete run costs nothing

- **WHEN** the step runs against outputs that already cover every pair in the grid
- **THEN** it issues no request and exits successfully

#### Scenario: No state lives outside the two outputs

- **WHEN** every file the step wrote other than those two is deleted
- **THEN** the next run resumes exactly as it would have

### Requirement: Request politeness and retries

The system SHALL issue at most one rate request per second, measured from the previous request, on a single thread. A failed rate request SHALL be retried up to five times with exponential backoff. A pair whose attempts are exhausted SHALL stop the step, and SHALL be recorded neither as priced nor as rejected.

Routing requests SHALL carry no such limit. The routing service is local.

#### Scenario: Exhausted retries stop the step

- **WHEN** a pair's rate request fails five times
- **THEN** the step stops, and the pair is absent from both outputs

### Requirement: The step reports what it did

At the end of a complete run the system SHALL report the number of pairs routed, the number rejected, the number priced, the number already known, and the elapsed time.

It SHALL also report, per source booth, how many target gares remain unreachable, so a source with no reachable target at all is visible rather than silent.

#### Scenario: A run reports its totals

- **WHEN** the step completes
- **THEN** it prints the pairs routed, rejected, priced, and already known

#### Scenario: A source with no reachable target is named

- **WHEN** every pair from one source booth is rejected
- **THEN** that source is named in the report

### Requirement: A barrier is never an endpoint

A two-way booth whose sides all agree — every adjacent node inside, or every one outside — SHALL be excluded from the grid as a source and as a target.

Such a booth is a barrier. You pay passing it and your ticket state does not change, so there is no journey for which it is the entrance or the exit, and any pair naming it is not a ticket however the roads read.

The exclusion SHALL happen before routing, alongside self-pairs, same-gare pairs and prohibited pairs, and SHALL be recorded in neither output.

#### Scenario: A barrier is not a source

- **WHEN** the grid is enumerated and a `bidirectional` group has every side outside
- **THEN** no pair has it as a source

#### Scenario: A barrier is not a target

- **WHEN** the grid is enumerated and a `bidirectional` group has every side outside
- **THEN** no pair has it as a target

#### Scenario: A barrier costs no route

- **WHEN** a barrier is excluded
- **THEN** no route is requested for any pair naming it

### Requirement: A two-way end must be used on its inside side

A route SHALL additionally be rejected when a two-way booth at either end of the pair is not used on the side that gives it the role the pair requires.

- A two-way **source** SHALL be departed toward a node in its `inside_nodes`. Leaving by the free side means the vehicle was not entering the network there.
- A two-way **target** SHALL be arrived at from a node in its `inside_nodes`. Arriving from the free side means the vehicle was not leaving the network there.

Both tests use the node immediately beside the booth on the route, the same node the sides were established from.

A one-way booth SHALL NOT be tested. Its single traffic sense already fixes its role, and it carries no sides.

#### Scenario: A source departed by its free side is rejected

- **WHEN** the route leaves a two-way source by a node in its `outside_nodes`
- **THEN** the pair is rejected

#### Scenario: A source departed by its toll side is kept

- **WHEN** the route leaves a two-way source by a node in its `inside_nodes` and nothing lies between
- **THEN** the pair is priced

#### Scenario: A target arrived at from its free side is rejected

- **WHEN** the route reaches a two-way target from a node in its `outside_nodes`
- **THEN** the pair is rejected

#### Scenario: A one-way end is not tested

- **WHEN** either end of a pair is a one-way booth
- **THEN** no side test is applied to it

### Requirement: A rejection records why

A rejected pair SHALL record which of the two reasons applies: a booth lying between the two, or an end used on its free side.

Both mean "not a ticket", and they want different remedies — one is about a third booth, the other about the direction of travel at an endpoint. A record that conflates them cannot be read afterwards.

A rejection for a booth in the way SHALL name that booth. A rejection for a wrong side SHALL name none, because none is implicated.

#### Scenario: A blocked pair names its booth

- **WHEN** a route crosses a third booth
- **THEN** the record carries that booth and the reason distinguishing it

#### Scenario: A wrong-side pair names no booth

- **WHEN** a pair is rejected for using an end on its free side
- **THEN** the record carries no booth and the reason saying so

### Requirement: Prices recorded before the side rule are re-derived

Every price whose source or target is a two-way booth SHALL be discarded, so that it is asked again under the rule.

Those amounts were recorded when any `bidirectional` group could be either end. Some describe journeys the rule now rejects, and nothing in the file distinguishes them from the ones it keeps. Re-deriving is the only way to tell, and leaving them would publish tariffs for pairings the step would no longer make.

A price with a one-way booth at both ends SHALL be kept and SHALL NOT be asked again.

#### Scenario: A price touching a two-way booth is discarded

- **WHEN** a price has a `bidirectional` group as its source, or a target gare carried by one
- **THEN** it is removed from `data/vinci_price.yaml` and the pair becomes outstanding

#### Scenario: A price between one-way booths is kept

- **WHEN** a price has a one-way booth at both ends
- **THEN** it is unchanged and no request is issued for it
