## ADDED Requirements

### Requirement: A barrier no route reaches is asked about on its own

A booth the override file types `passthrough` charges for itself, and lies on a trip that ends outside France, so no route in the route set crosses it and no route's passage list carries its gare. The system SHALL ask about it directly, by submitting a passage list holding that booth's gare and nothing else. The amount returned SHALL be recorded as that booth's price, under `type: passthrough`.

One request SHALL be made per such booth. Two booths carrying one gare are the two carriageways of one plaza and yield the same answer, which the existing rule against a price changing then checks rather than assumes.

The request SHALL be built from `data/vinci_toll_booth.yaml` alone, as every other request in this step is. Nothing is routed and nothing is invented: a single passage is the smallest question the rate service answers, and it is the whole question a barrier poses.

A booth the override file types `enter` or `exit` SHALL NOT be asked about this way. The service answers a lone passage for a closed-section end too, with an amount that is not what that gare charges — `09240` BEAUREPAIRE is an entrance whose real tariffs are 53.90 and 54.60 against its two exits, and whose lone-passage answer is 14.70. Recording that would publish a price the operator never charges.

#### Scenario: A stated barrier is asked about

- **WHEN** the step runs and a booth typed `passthrough` by the override file has not been asked about
- **THEN** it submits one request whose passage list holds that booth's gare alone, and records the amount as that booth's price

#### Scenario: The request carries no other passage

- **WHEN** a single-passage request is built
- **THEN** its passage list has length one, and no route in `data/route_set.yaml` contributed to it

#### Scenario: A stated entrance is not asked about

- **WHEN** a booth typed `enter` or `exit` by the override file is recorded
- **THEN** no single-passage request was issued for it, and its entry carries no `price`

#### Scenario: Two carriageways of one barrier agree

- **WHEN** two booths typed `passthrough` carry one gare code
- **THEN** both are asked about, both record the same price, and the second changes nothing

### Requirement: A stated role is recorded whether or not a price was found

A booth the override file types `enter`, `exit`, or `passthrough` SHALL be recorded in `data/vinci_price.yaml` under that type. For `enter` and `exit` the entry carries `type` alone: the gare's tariff depends on the partner at the other end of the ticket, and the direct pricing step is what supplies it. Recording the role is what puts the booth into the grid that step enumerates.

#### Scenario: A stated entrance becomes a source

- **WHEN** a booth typed `enter` by the override file is recorded
- **THEN** its entry carries `type: enter` and nothing else, and the direct pricing step takes it as a source

#### Scenario: A stated exit becomes a target

- **WHEN** a booth typed `exit` by the override file is recorded
- **THEN** its entry carries `type: exit`, and the direct pricing step takes it as a target

### Requirement: A stated barrier the operator will not price on its own stops the step

When a booth typed `passthrough` by the override file gets `No rate found.` for its gare alone, the system SHALL stop and name the booth and the gare. The service declines a lone passage for a gare that is one end of a closed section, so the answer says the booth is not a barrier and the statement is wrong.

The converse SHALL NOT be inferred. A lone passage answered with a price does not establish that a gare is a barrier, because the service answers one for a closed-section end as well. Nothing in this step can tell the two apart, and a check that pretended otherwise would stop on booths that are correctly stated.

What does tell them apart is whether any partner is reachable without crossing another booth, which is a question for the router and therefore for the direct pricing step. A booth stated `enter` or `exit` that turns out to have no clean partner at all is a barrier misstated, and that step is where it becomes visible.

#### Scenario: A closed-section end stated as a barrier

- **WHEN** a booth typed `passthrough` gets `No rate found.` for its gare alone
- **THEN** the step stops and reports that the operator prices that gare only against a partner

#### Scenario: A stated barrier the operator prices

- **WHEN** a booth typed `passthrough` gets a price back for its gare alone
- **THEN** the run continues and the booth is recorded with that price

#### Scenario: An entrance that also answers a lone passage is not second-guessed

- **WHEN** a booth typed `enter` carries a gare the service would price on its own
- **THEN** the step issues no such request, records the stated role, and does not stop

### Requirement: Every border-typed booth must be recorded

When the step completes, every booth the override file types `enter`, `exit`, or `passthrough` SHALL carry an entry in `data/vinci_price.yaml`, or the step SHALL fail and name it.

This is stricter than the rule for a covered booth, which is reported and not fatal. A covered booth without a price is a gap in the route set, which is where it is fixed. A border-typed booth is settled by the override file and, for a barrier, by one direct question, so nothing stands between the statement and the record.

The check SHALL run on every invocation, including one that finds no outstanding work.

#### Scenario: A border-typed booth with no entry

- **WHEN** the step completes and some border-typed booth carries no entry
- **THEN** the step fails and names that booth

#### Scenario: The check runs with nothing outstanding

- **WHEN** the step is re-run with every route and every border-typed booth already processed
- **THEN** it issues no request and still reports any border-typed booth without an entry

## MODIFIED Requirements

### Requirement: Prices are derived from the existing route set and gare mapping

The system SHALL build each request from `data/route_set.yaml` and `data/vinci_toll_booth.yaml` alone, and SHALL NOT contact a routing service or the placemark service. It SHALL read `data/osm_toll_booths.yaml` for each booth's `type`, which decides how a group is classified but takes no part in any request.

For each route, the passage list SHALL be that route's `covers` entries in the order they appear, each replaced by the gare code `data/vinci_toll_booth.yaml` records for that booth group.

The system SHALL NOT invent a trip of its own and submit it as a route. The one exception is the single-passage request for a barrier the route set cannot reach, which is not a trip: it holds one gare, it names a booth the override file states by hand, and it is governed by its own requirements.

#### Scenario: A route's passages follow its covers

- **WHEN** a route is submitted
- **THEN** its passage list holds the gare of each `covers` entry, in the order `covers` lists them

#### Scenario: No routing service is contacted

- **WHEN** the step runs with outstanding routes and the OSRM instance stopped
- **THEN** it completes normally

#### Scenario: Routes are not invented

- **WHEN** the step runs
- **THEN** every passage list of more than one gare comes from an entry of `data/route_set.yaml`

#### Scenario: A single-passage request is not a route

- **WHEN** the step submits a single-passage request for a stated barrier
- **THEN** `data/route_set.yaml` is unchanged, and no multi-gare request was built for that booth

### Requirement: A booth the inventory types keeps that type

Most booths hold one role for good. Three kinds do not hold the role a given route reports, and two files name them.

`data/osm_toll_booths.yaml` names two with its `type` field:

- **`bidirectional`** — one group in both directions, so it is an entrance to a journey driven one way and an exit to the same journey driven the other.
- **`gantry`** — a free-flow point charging per section travelled, so it starts a section when another gantry follows on the same journey and is a charge of its own when none does.

`data/osm_toll_booths_overrides.yaml` names the third with `type: enter`, `type: exit`, or `type: passthrough`: a booth no route reaches, whose role is stated by hand because no route can demonstrate it.

A group either file types SHALL be recorded under that same type whatever role a given route reports for it. A group the inventory types SHALL NOT be recorded as `passthrough`, `enter`, or `exit`.

Such an entry SHALL carry `prices` for every exit gare a route left at after it, and `price` when a route was charged for it on its own. It MAY carry both, and MAY carry neither. It carries nothing extra for the routes that merely ended a section there, because an exit records no amount — so a group met only that way carries `type` alone.

Recording the role instead would need the journey as part of the key, and would buy nothing: an exit stores no amount, and the exit gare in `prices` already identifies the journey that produced it.

#### Scenario: A two-way booth reported in two roles

- **WHEN** one route reports a `bidirectional` group as an entrance and another reports it as an exit
- **THEN** both are recorded on one `bidirectional` entry, and neither stops the step

#### Scenario: A gantry is a section start on one route and a charge of its own on the next

- **WHEN** a `gantry` group is priced at 1.90 paired with the next gantry on one route, and at 0.90 alone on a route that leaves before reaching one
- **THEN** its entry carries `prices` holding 1.9 and `price` holding 0.9

#### Scenario: A plain one-way lane is never given an inventory type

- **WHEN** a group that neither file types is recorded
- **THEN** its type is `passthrough`, `enter`, or `exit`, taken from how the service charged it

#### Scenario: A stated role outranks a route

- **WHEN** the override file states a booth `enter` and a route that covers it reports it as an exit
- **THEN** it is recorded as `enter`, and the run continues

### Requirement: The step is resumable and always executes

The step SHALL read its own output to determine which routes it has already submitted, and SHALL submit none of them again. A route SHALL be appended to `routes` only after its whole response has been attributed, so an interruption costs at most one route.

The same SHALL hold for a single-passage request. It is recorded under `routes` as its booth's node id in both `from` and `to`, which no route can produce because a route's endpoints are two distinct place nodes, and it is recorded only after its answer has been applied in full.

A run with nothing outstanding SHALL issue no request, and SHALL still produce the end-of-run report.

#### Scenario: Resuming after an interruption

- **WHEN** a run is interrupted and the step is run again
- **THEN** it submits only the routes absent from `routes`, repeating at most one

#### Scenario: A complete file costs nothing

- **WHEN** the step runs against an output that already covers every submittable route and every stated barrier
- **THEN** it issues no request and exits successfully

#### Scenario: A single-passage request is recorded once applied

- **WHEN** the step fails while applying the answer to a single-passage request
- **THEN** that booth is absent from `routes`, and the next run asks again

### Requirement: Price file output format

The system SHALL write `data/vinci_price.yaml` as a mapping with two top-level keys, `toll_booths` and `routes`.

`toll_booths` SHALL map an OSM booth group id to a mapping carrying `type`, one of `passthrough`, `enter`, `exit`, `bidirectional`, or `gantry`.

- A `passthrough` entry SHALL also carry `price`, a number of euros.
- An `enter` entry SHALL carry `prices`, a mapping from an exit gare code to a number of euros, unless it is a booth the override file states, whose partners are priced by the direct pricing step and which therefore carries `type` alone until that step has run.
- An `exit` entry SHALL carry `type` alone.
- A `bidirectional` or `gantry` entry MAY carry `price`, `prices`, both, or neither. Neither means every route met it only as the end of a section, which records no amount, exactly as for an `exit`.

`routes` SHALL hold the `from`/`to` pairs already processed. A pair naming one booth twice is a single-passage request rather than a route.

`toll_booths` keys SHALL be written in ascending numeric order, and `prices` keys in ascending code order, so a rerun that learns nothing produces no diff.

```yaml
toll_booths:
  27174404:
    type: enter
    prices:
      "03086": 6.8
  130221205:
    type: exit
  289635259:
    type: bidirectional
    prices:
      "09170": 4.3
  4172775770:
    type: passthrough
    price: 55.5
  11578487423:
    type: gantry
    price: 0.9
    prices:
      "22535": 1.9
  609218048:
    type: passthrough
    price: 7.8
routes:
  - from: 547958
    to: 26692263
  - from: 4172775770
    to: 4172775770
```

#### Scenario: The file is written

- **WHEN** the step completes
- **THEN** `data/vinci_price.yaml` parses as YAML with top-level `toll_booths` and `routes` keys

#### Scenario: An exit carries no amount

- **WHEN** a group recorded as `exit` is inspected
- **THEN** it carries `type` and nothing else

#### Scenario: A typed entry that was only ever a section end

- **WHEN** every route crossing a `gantry` group met it as the end of a section
- **THEN** its entry carries `type` alone, and the step does not treat that as a gap

#### Scenario: A stated entrance before the direct pricing step

- **WHEN** a booth the override file states `enter` has been recorded and the direct pricing step has not yet run
- **THEN** its entry carries `type` alone, and the step does not treat that as a gap

#### Scenario: A single-passage request is recorded under routes

- **WHEN** a stated barrier has been asked about
- **THEN** `routes` carries an entry whose `from` and `to` are both that booth's node id

#### Scenario: Rewriting is stable

- **WHEN** a complete file is written again from the same state
- **THEN** the result is byte-identical
