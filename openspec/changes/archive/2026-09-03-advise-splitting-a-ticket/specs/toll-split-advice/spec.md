## Purpose
Defines which stop sequences make a sold ticket cheaper, how a candidate is proved to be a real re-entry rather than a drive across country, the format and rebuild contract of `data/cost-cutting.yaml`, and when the advice is offered to a driver.

## ADDED Requirements

### Requirement: A split is a sequence of sold tickets

For a sold pair `(A, Z)` the system SHALL consider every sequence of gares `A -> G1 -> ... -> Gk -> Z` in which each consecutive step is itself a sold ticket in `data/vinci_price.yaml`. The fare of the sequence is the sum of those tickets, and it is a candidate only when that sum is strictly less than the direct ticket.

A gare SHALL be usable as a stop only when it has both an exit side and an entrance side. A gare the operator sells tickets into but none out of cannot be left, so no vehicle can stop there.

#### Scenario: A cheaper sequence is a candidate

- **WHEN** `A -> G` and `G -> Z` are both sold and their sum is less than `A -> Z`
- **THEN** stopping at `G` is a candidate for the pair `(A, Z)`

#### Scenario: A sequence that is not cheaper is not a candidate

- **WHEN** the sum of a sequence's tickets is greater than or equal to the direct ticket
- **THEN** it is not recorded

#### Scenario: An entrance-only gare is not a stop

- **WHEN** a gare has an entrance side and no exit side
- **THEN** no candidate names it as a stop

### Requirement: A candidate is kept only when the router re-enters at the stop

The extra time of a split SHALL be measured against the project's own untouched routing graph, driving `ENTER[A] -> EXIT[G1]`, then `EXIT[Gi] -> EXIT[Gi+1]` for each stop, and finally to `EXIT[Z]`, against the single leg `ENTER[A] -> EXIT[Z]`.

A leg that begins at a stop SHALL be discarded unless its route crosses a booth carrying the gare it started from, at a position after the first node of the path. Without that crossing the vehicle never re-entered the tolled road and bought no second ticket, so the fare being compared is for a journey nobody drove. Such a route is typically a slower cross-country drive that abandons the motorway.

The first node of a path IS the exit booth the leg starts from, so it SHALL NOT count as the re-entry.

Every lane of a plaza SHALL count, aliases included. The inventory names one lane of a plaza its group representative and the rest aliases; a vehicle re-entering may cross any of them, and testing only representatives rejects real re-entries.

#### Scenario: A leg that abandons the motorway

- **WHEN** the route from a stop to the destination crosses no booth of the stop's gare after its first node
- **THEN** that candidate is discarded

#### Scenario: The starting booth does not prove re-entry

- **WHEN** the only node of the stop's gare on the path is the path's first node
- **THEN** the candidate is discarded

#### Scenario: Re-entry through another lane of the plaza

- **WHEN** the route crosses an alias lane of the stop's gare rather than the group representative
- **THEN** the candidate is kept

#### Scenario: A two-way booth crossed twice

- **WHEN** the stop is a booth the inventory types `bidirectional` and its single node appears again later on the path
- **THEN** the candidate is kept

### Requirement: A stop costs booth time, and a two-way booth costs more

Each stop SHALL add a fixed booth time to the journey, and a stop at a booth the inventory types `bidirectional` SHALL add a larger fixed time instead.

A two-way booth is one node for both directions, so a router measures its turnaround as nothing. A vehicle cannot turn round on the plaza: it carries on to the next roundabout and comes back, and that drive is charged here because the graph cannot show it.

The extra time of a split SHALL NOT be recorded as less than the sum of its stops' fixed costs. Two legs joined at a stop that lies on the direct path can measure marginally faster than the single direct route; that is an artefact of snapping, not a saving, and left unfloored it puts impossible ratios at the top of the ranking.

#### Scenario: A two-way stop costs more than an ordinary one

- **WHEN** two candidates differ only in that one stops at a `bidirectional` booth
- **THEN** that one is recorded with the larger fixed time

#### Scenario: The measured drive is faster than the direct route

- **WHEN** the legs of a split sum to less driving time than the direct leg
- **THEN** the recorded extra time is the sum of the stops' fixed costs, not a smaller or negative value

### Requirement: Every surviving trade-off is kept, not only the cheapest

For each pair the system SHALL record every candidate that is not beaten on both fare and time by another candidate for that pair.

Recording only the cheapest answers a different question. A chain of stops that squeezes out the last euro can cost far more time than a single stop that captures most of the saving, and which one a driver wants depends on what an hour is worth to them. A candidate beaten on both counts can never be preferred and SHALL be dropped.

#### Scenario: A dearer but faster split is kept

- **WHEN** one candidate is cheaper and slower and another is dearer and faster
- **THEN** both are recorded for that pair

#### Scenario: A candidate beaten on both counts is dropped

- **WHEN** a candidate is both dearer and slower than another for the same pair
- **THEN** it is not recorded

### Requirement: Advice file output format

The system SHALL write `data/cost-cutting.yaml` as a mapping with a single top-level key, `toll_booths`, mapping an entrance gare code to a mapping of exit gare code to a list of candidates.

Each candidate SHALL carry:

- `nodes` — the OSM booth nodes to stop at, in driven order, two per stop: the exit booth the vehicle leaves by and the entrance booth it re-enters by. For a `bidirectional` booth both are the same node.
- `extra_time` — a whole number of seconds, the driving time the split adds over the direct route, including the fixed booth cost of every stop.

A candidate SHALL NOT carry any amount of money. The saving is determined entirely by `data/vinci_price.yaml`, and a second copy of it here would go stale the moment a booth is repriced, with nothing to notice.

Gare codes SHALL be quoted, because they are digit strings with leading zeros that YAML would otherwise read as integers. Entrance codes, exit codes, and the candidates of a pair SHALL each be written in a stable order, so that a rerun that learns nothing produces no diff.

```yaml
toll_booths:
  '12060':
    '05615':
      - nodes: [3248212729, 1042826707]
        extra_time: 174
  '04344':
    '04224':
      - nodes: [1588137485, 1588137486]
        extra_time: 150
```

#### Scenario: The file is written

- **WHEN** the step completes
- **THEN** `data/cost-cutting.yaml` parses as YAML with a single top-level `toll_booths` key

#### Scenario: A candidate names two nodes per stop

- **WHEN** a one-stop candidate is inspected
- **THEN** its `nodes` list has two entries, the exit booth and then the entrance booth

#### Scenario: Extra time is a whole number of seconds

- **WHEN** any `extra_time` is read
- **THEN** it is an integer, not a string and not a duration with a unit suffix

#### Scenario: No money is recorded

- **WHEN** the file is searched for amounts
- **THEN** it carries no price, saving, or rate of any kind

#### Scenario: Rewriting is stable

- **WHEN** the step runs again against unchanged inputs
- **THEN** the file is byte-identical

### Requirement: The step is checkpointed on its own output and keyed to the prices

The step SHALL be skipped when `data/cost-cutting.yaml` is present and no newer than the artefacts it is derived from.

`data/vinci_price.yaml`, `data/vinci_toll_booth.yaml` and `data/osm_toll_booths.yaml` SHALL be real prerequisites rather than order-only ones. This file *is* those tariffs read as arbitrage, so a repriced booth that left it alone would advise splits at prices the operator no longer charges, and nothing downstream could tell.

The step SHALL issue no request to the rate service. Every duration comes from the project's own untouched routing graph.

#### Scenario: A repriced booth rebuilds the advice

- **WHEN** `data/vinci_price.yaml` is newer than `data/cost-cutting.yaml`
- **THEN** the step runs again

#### Scenario: Nothing to do

- **WHEN** the step runs against inputs no newer than its output
- **THEN** it does no work

#### Scenario: The operator is not contacted

- **WHEN** the step runs with no rate service key configured
- **THEN** it completes normally

### Requirement: Advice is offered only above a threshold

A split SHALL be offered for a closed section of a route only when the euros it saves, divided by the hours of extra driving it costs, is at least a configured threshold, defaulting to 20 EUR per hour.

The threshold SHALL be applied when a route is answered, not when the file is built. A threshold frozen into a committed artefact could not be changed without rebuilding the pipeline.

#### Scenario: A split below the threshold is not offered

- **WHEN** the best candidate for a section saves 1.00 EUR for 12 minutes of extra driving
- **THEN** no split is offered for that section

#### Scenario: A split above the threshold is offered

- **WHEN** the best candidate for a section saves 2.40 EUR for 2.5 minutes of extra driving
- **THEN** that split is offered

#### Scenario: The threshold is configurable

- **WHEN** the threshold is set to a different value and the same route is queried
- **THEN** the set of sections offered a split changes accordingly
