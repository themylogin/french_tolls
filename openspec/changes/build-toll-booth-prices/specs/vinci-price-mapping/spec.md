## Purpose

Defines how each OSM toll booth group is priced against the VINCI Ulys rate service — how a route's gares become a passage list, how a returned amount is attributed back to a booth group, how a group is classified as `passthrough`, `enter`, `exit`, `bidirectional`, or `gantry`, and the format and resume contract of `data/vinci_price.yaml`.

## ADDED Requirements

### Requirement: Prices are derived from the existing route set and gare mapping

The system SHALL build each request from `data/route_set.yaml` and `data/vinci_toll_booth.yaml` alone, and SHALL NOT synthesise routes of its own, contact a routing service, or contact the placemark service. It SHALL read `data/osm_toll_booths.yaml` for each booth's `type`, which decides how a group is classified but takes no part in any request.

For each route, the passage list SHALL be that route's `covers` entries in the order they appear, each replaced by the gare code `data/vinci_toll_booth.yaml` records for that booth group.

#### Scenario: A route's passages follow its covers

- **WHEN** a route is submitted
- **THEN** its passage list holds the gare of each `covers` entry, in the order `covers` lists them

#### Scenario: No routing service is contacted

- **WHEN** the step runs with outstanding routes and the OSRM instance stopped
- **THEN** it completes normally

#### Scenario: Routes are not invented

- **WHEN** the step runs
- **THEN** every route it submits is an entry of `data/route_set.yaml`

### Requirement: Passage order is the driven order

The order of passages in a request SHALL be the order the route drives them. The rate service pairs an entrance with the exit that follows it in the submitted list, so a list in any other order describes a journey that was not driven.

The system SHALL therefore depend on `covers` being ordered by traversal position, as `route-set-generation` requires.

#### Scenario: Entrance precedes its exit

- **WHEN** a route enters a closed section at gare A and leaves it at gare B
- **THEN** A appears before B in the submitted passage list

### Requirement: One tariff date for the whole file

Every passage of every request SHALL carry the same timestamp, read from the environment as `ULYS_PASSAGE_DATE`. Tariffs change on a date, so a file whose rows were priced on different dates would be internally inconsistent for a reason nothing in the file records.

#### Scenario: Every passage carries the configured date

- **WHEN** any request is submitted
- **THEN** every passage in it carries the value of `ULYS_PASSAGE_DATE`

#### Scenario: The date is not configured

- **WHEN** `ULYS_PASSAGE_DATE` is unset or empty and the step is run
- **THEN** the step stops with a message naming the missing variable, before any request is issued

### Requirement: One vehicle class and one payment option

Requests SHALL carry vehicle category 1 and payment option 2. `data/vinci_price.yaml` describes that combination and no other. The file SHALL NOT carry a class or payment dimension.

#### Scenario: Requests are single-class

- **WHEN** any request is submitted
- **THEN** it declares vehicle category 1 and payment option 2

### Requirement: A route that would be mis-paired is not submitted

A route whose `covers` includes a booth the override file marks `absent_enter` or `absent_exit` SHALL NOT be submitted. Such a booth has no gare, so its passage cannot be sent; omitting it would leave the neighbouring gare paired with a partner the vehicle never drove, and the service would return a real price for a journey nobody made.

A booth marked `absent_passthrough`, which forms no pair, SHALL simply be omitted from the passage list, and its route SHALL be submitted normally.

A skipped route SHALL be recorded as skipped rather than as processed, and SHALL be named in the end-of-run report.

#### Scenario: A route through an absent entrance is skipped

- **WHEN** a route's `covers` includes a booth marked `absent_enter`
- **THEN** no request is issued for that route, and the route is reported as skipped

#### Scenario: A route through an absent barrier is submitted

- **WHEN** a route's `covers` includes a booth marked `absent_passthrough` and no booth marked `absent_enter` or `absent_exit`
- **THEN** the route is submitted with that booth left out of the passage list

### Requirement: A returned amount is attributed by position

The service returns items in the order of the passage list, consuming one passage for an item that carries only `entranceToll` and two for an item that carries `exitToll` as well. Attribution SHALL follow that consumption with a cursor over the submitted passages, so a gare that appears twice on one route is never confused with itself.

For each returned item, the system SHALL advance the cursor to the next passage whose gare equals the item's `entranceToll` code, and consume it. When the item carries `exitToll`, the system SHALL consume the immediately following passage and SHALL require its gare to equal the item's `exitToll` code.

The gare code SHALL be read from the `code` field of the returned toll, not rebuilt from `operatorId` and `tollId`. The response reports those two as integers, so rebuilding would lose the leading zeros the request and `data/vinci_toll_booth.yaml` both use.

#### Scenario: A gare driven twice is attributed twice

- **WHEN** a route passes one gare twice and the response returns two items naming it
- **THEN** the first item is attributed to the first passage and the second item to the second

#### Scenario: The exit does not follow its entrance

- **WHEN** a returned item's `exitToll` does not equal the passage following the one its `entranceToll` matched
- **THEN** the step stops and names the route, the item, and both passages

#### Scenario: No passage matches an item

- **WHEN** no passage ahead of the cursor carries a returned item's `entranceToll` code
- **THEN** the step stops and names the route, the item, and the remaining passages

#### Scenario: Leading zeros are preserved

- **WHEN** the service returns `operatorId: 5`, `tollId: 55`, `code: "05055"`
- **THEN** the gare is read as `05055`

### Requirement: Passages the service did not price are reported

A response SHALL be checked against the passages it consumed. The system SHALL report the route and every passage the service did not price, and SHALL continue. A passage counts as unpriced when the cursor steps over it, when it is left over at the end, or when the item that consumed it carries no amount.

An item with no amount is not a malformed response. It is the service answering that it has no tariff for that passage, and `comments` says so. It SHALL still consume its passages, so the cursor stays in step, and SHALL record nothing.

A gare the inventory carries and the operator does not price on that route is a real disagreement, and burying it would leave a booth silently unpriced.

#### Scenario: The response prices fewer passages than were sent

- **WHEN** a route's response consumes fewer passages than were submitted
- **THEN** the unpriced passages are reported with their route, and the run continues

#### Scenario: An item carries no amount

- **WHEN** a returned item names an entrance, carries no amount, and comments `No rate found.`
- **THEN** its passages are reported as unpriced, nothing is recorded for them, and the run continues

#### Scenario: A passage the service ignores does not shift the cursor

- **WHEN** a route submits `04342, 04210, 04210, 04218` and the service returns `04342 -> 04210` and then `04218` with no amount
- **THEN** the second `04210` and `04218` are reported as unpriced, and `04342 -> 04210` is recorded

### Requirement: A booth group is classified by how the service charges it

An item that carries `entranceToll` alone SHALL classify the passage it consumed as `passthrough`, and its amount SHALL be that group's price.

An item that carries both SHALL classify the entrance passage as `enter` and the exit passage as `exit`, and its amount SHALL be recorded on the entrance group under the exit's gare code.

A group the inventory gives no `type` SHALL hold exactly one of those three classifications for the whole run.

#### Scenario: A barrier is a passthrough

- **WHEN** an item carries `entranceToll` and no `exitToll`
- **THEN** the group that passage resolves to is recorded as `passthrough` with that amount as its price

#### Scenario: A closed section is a pair

- **WHEN** an item carries `entranceToll` `04358`, `exitToll` `04355`, and price 6.80
- **THEN** the entrance group is recorded as `enter` with 6.8 under the key `"04355"`, and the exit group is recorded as `exit`

### Requirement: A booth the inventory types keeps that type

Most booths hold one role for good. Two kinds do not, and `data/osm_toll_booths.yaml` names both with its `type` field:

- **`bidirectional`** — one group in both directions, so it is an entrance to a journey driven one way and an exit to the same journey driven the other.
- **`gantry`** — a free-flow point charging per section travelled, so it starts a section when another gantry follows on the same journey and is a charge of its own when none does.

A group the inventory types SHALL be recorded under that same type whatever role a given route reports for it, and SHALL NOT be recorded as `passthrough`, `enter`, or `exit`.

Such an entry SHALL carry `prices` for every exit gare a route left at after it, and `price` when a route was charged for it on its own. It MAY carry both, and MAY carry neither. It carries nothing extra for the routes that merely ended a section there, because an exit records no amount — so a group met only that way carries `type` alone.

Recording the role instead would need the journey as part of the key, and would buy nothing: an exit stores no amount, and the exit gare in `prices` already identifies the journey that produced it.

#### Scenario: A two-way booth reported in two roles

- **WHEN** one route reports a `bidirectional` group as an entrance and another reports it as an exit
- **THEN** both are recorded on one `bidirectional` entry, and neither stops the step

#### Scenario: A gantry is a section start on one route and a charge of its own on the next

- **WHEN** a `gantry` group is priced at 1.90 paired with the next gantry on one route, and at 0.90 alone on a route that leaves before reaching one
- **THEN** its entry carries `prices` holding 1.9 and `price` holding 0.9

#### Scenario: A plain one-way lane is never given an inventory type

- **WHEN** a group the inventory does not type is recorded
- **THEN** its type is `passthrough`, `enter`, or `exit`

### Requirement: A contradiction stops the step

The system SHALL stop, naming the route and both values, when a route reports:

- a classification for a group the inventory does not type that differs from the one already recorded;
- an open-flow price for a group that differs from the one already recorded;
- a pair price for an entrance group and exit gare that differs from the one already recorded.

Amounts SHALL be compared exactly, in whole cents. The service returns decimal amounts, and comparing them as binary floating point would report a difference where none exists.

#### Scenario: An untyped group changes role

- **WHEN** a group the inventory does not type, already recorded as `enter`, is reported as `exit`
- **THEN** the step stops and names the group, both roles, and the route

#### Scenario: A typed group changing role is not a contradiction

- **WHEN** a `bidirectional` or `gantry` group reported as an entrance is later reported as an exit
- **THEN** the run continues

#### Scenario: A pair price changes

- **WHEN** a pair already recorded at 6.80 is reported at 7.10
- **THEN** the step stops and names the entrance group, the exit gare, both amounts, and the route

#### Scenario: The same amount is not a contradiction

- **WHEN** a pair already recorded at 6.80 is reported at 6.80
- **THEN** the run continues

### Requirement: A hand-stated price is published

A booth the override file marks `absent_passthrough` with a `price` SHALL be written to `data/vinci_price.yaml` as `passthrough` carrying that price, so a consumer reads one file rather than two. A booth marked `absent_passthrough` without a `price` SHALL receive no entry.

#### Scenario: A stated price is copied out

- **WHEN** a booth is marked `absent_passthrough` with `price: 1.4`
- **THEN** `data/vinci_price.yaml` records it as `passthrough` with price 1.4

#### Scenario: An unpriced absent barrier is omitted

- **WHEN** a booth is marked `absent_passthrough` with no `price`
- **THEN** `data/vinci_price.yaml` carries no entry for it

### Requirement: A booth without a price is reported, not fatal

At the end of a complete run the system SHALL report every booth group that a route in `data/route_set.yaml` covers and that carries no entry in the output, together with why — no gare, or covered only by routes that were skipped. The step SHALL exit successfully.

Unlike the gare mapping step, a missing price is not a disagreement with the operator. It is a consequence of the routes that could be submitted, and the route set is where it is fixed.

#### Scenario: A covered booth has no price

- **WHEN** a run completes and a covered booth group carries no entry
- **THEN** the step reports that group and the reason, and exits successfully

### Requirement: Price file output format

The system SHALL write `data/vinci_price.yaml` as a mapping with two top-level keys, `toll_booths` and `routes`.

`toll_booths` SHALL map an OSM booth group id to a mapping carrying `type`, one of `passthrough`, `enter`, `exit`, `bidirectional`, or `gantry`.

- A `passthrough` entry SHALL also carry `price`, a number of euros.
- An `enter` entry SHALL also carry `prices`, a mapping from an exit gare code to a number of euros.
- An `exit` entry SHALL carry `type` alone.
- A `bidirectional` or `gantry` entry MAY carry `price`, `prices`, both, or neither. Neither means every route met it only as the end of a section, which records no amount, exactly as for an `exit`.

`routes` SHALL hold the `from`/`to` pairs already processed.

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

#### Scenario: Rewriting is stable

- **WHEN** a complete file is written again from the same state
- **THEN** the result is byte-identical

### Requirement: The step is resumable and always executes

The step SHALL read its own output to determine which routes it has already submitted, and SHALL submit none of them again. A route SHALL be appended to `routes` only after its whole response has been attributed, so an interruption costs at most one route.

A run with nothing outstanding SHALL issue no request, and SHALL still produce the end-of-run report.

#### Scenario: Resuming after an interruption

- **WHEN** a run is interrupted and the step is run again
- **THEN** it submits only the routes absent from `routes`, repeating at most one

#### Scenario: A complete file costs nothing

- **WHEN** the step runs against an output that already covers every submittable route
- **THEN** it issues no request and exits successfully

### Requirement: Request politeness and retries

The system SHALL issue at most one request per second, measured from the previous request, on a single thread. A failed request SHALL be retried up to five times with exponential backoff. A route whose attempts are exhausted SHALL stop the step, and SHALL NOT be recorded as processed.

#### Scenario: Exhausted retries stop the step

- **WHEN** a route's request fails five times
- **THEN** the step stops, and that route is absent from `routes` in the output

### Requirement: Response comments are surfaced

A returned item carrying a non-empty `comments` list SHALL be reported with its route and the gares it names. The field is undocumented, and discarding it would hide whatever the service is qualifying.

#### Scenario: An item carries a comment

- **WHEN** a returned item's `comments` list is not empty
- **THEN** its contents are reported with the route and the item's gares
