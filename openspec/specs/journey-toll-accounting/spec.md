# journey-toll-accounting Specification

## Purpose
Turns the ordered node ids of a driven route into the list of toll passages it makes and what each one costs, using the booth inventory, the gare mapping, the tariffs, and the booth sides that the build pipeline publishes.

## Requirements

### Requirement: Accounting reads the pipeline's published artefacts

The system SHALL take every fact about a booth from the four committed pipeline artefacts:

- `data/osm_toll_booths.yaml` — which nodes are booths, and which nodes are lanes of another booth.
- `data/vinci_price.yaml` — each booth's type and its tariffs.
- `data/vinci_toll_booth.yaml` — each booth's gare code and the operator's name for it.
- `data/bidirectional_booth_sides.yaml` — which neighbours of a two-way booth lie inside the toll network.

The system SHALL NOT carry a booth or tariff snapshot of its own. A snapshot goes stale silently: the one this capability replaces was taken before the `gantry` type existed, so the 52 priced gantries the pipeline now carries charged nothing, and no part of the answer said so.

The artefacts SHALL be read once at start-up rather than on each request.

#### Scenario: A gantry is charged

- **WHEN** a route passes a booth the price file types `gantry` with a price of 2.20 EUR
- **THEN** the journey is charged 2.20 EUR and the passage is named

#### Scenario: No private snapshot exists

- **WHEN** the application's own files are listed
- **THEN** none of them holds a booth inventory or a tariff table

### Requirement: A lane is accounted as the plaza it belongs to

Every node id of a route SHALL be resolved through the inventory's `aliases` to the booth it is a lane of, and accounted as that booth.

A plaza is mapped as one node per lane on parallel ways, and a route drives exactly one of them. Looking for the representative's own id finds nothing whenever the router chose a neighbouring lane, and the passage is then missed entirely. The inventory records 262 lanes as aliases of 1 295 booths.

Where a route's node sequence resolves to the same booth on consecutive nodes, that SHALL count as one passage. The same booth resolved again later in the route SHALL count as a further passage.

#### Scenario: A neighbouring lane is charged

- **WHEN** a route traverses a node the inventory records as an alias of another booth
- **THEN** the passage is accounted against that other booth, with its type, tariffs, gare code, and name

#### Scenario: One plaza, one passage

- **WHEN** two consecutive nodes of a route both resolve to the same booth
- **THEN** the journey records one passage, not two

### Requirement: A ticket is opened at an entrance and closed at an exit

The system SHALL walk the resolved booths in the order the route drives them and SHALL keep at most one open ticket.

- A booth typed `enter` SHALL open a ticket.
- A booth typed `exit` SHALL close the open ticket. The passage SHALL be priced at the open entrance's tariff for this booth's gare code, and named `<entrance> → <exit>`.
- A booth typed `passthrough` SHALL be charged its own flat price and SHALL leave the ticket state alone.
- A booth typed `gantry` SHALL be charged its own flat price and SHALL leave the ticket state alone.

A tariff SHALL be read from the entrance's tariff mapping under the exit's gare code. It SHALL NOT be taken as an element of a list by position: the source records one amount per gare code, and picking by position charges a journey the price of another.

Where an `exit` is reached with no ticket open, the system SHALL look back at the last `gantry` crossed since the last ticket ended. Where that gantry's gare prices this exit's gare code, the passage SHALL be priced at that tariff and named `<gantry> → <exit>`, and the gantry's own crossing SHALL NOT also be counted unpriced.

Some gantries are ticketless entrances: the portal reads the plate and the barrier at the far end collects, so the vehicle crosses nothing that looks like an entrance. A route joining the A41 at Chambéry Nord passes gantry `7346104910` and reaches the barrier at Annecy Centre having crossed no `enter` booth, and the 5.60 EUR section is the charge.

Only the last gantry SHALL be considered. An earlier one belongs to a section already settled.

A gantry carrying its own `price` SHALL NOT be read as a ticketless entrance. It collected where it stands and is charged there; billing a section for the same passage would charge it twice.

What a section costs SHALL be answered in one place. Both walks read it, and everything downstream of them: the charge on the journey, the quote for a section, and the fare a split is measured against. Where they disagree, a section is charged to the driver and skipped by the advice, or the reverse.

Where the entrance is a `gantry`, the tariff SHALL be sought under its gare code across every group carrying it. A rate request names two gare codes and the answer is the pair's, so every group of a gare charges the same. Groups hold different numbers of tariffs for two reasons: `vinci-direct-pricing` never enumerates a gantry as a source, so a gantry is priced only by the routes that cross it; and a pair it does enumerate is asked about only where no booth lies between. Chambéry Nord's gantry records 3 tariffs and the `enter` group beside it records 27, both under gare `03008`.

Where the entrance is any other type, the tariff SHALL be read from that group's own mapping alone. A group the route crossed already answers for itself, and widening it would move fares that are correct today. A gantry entrance arises only from the look-back, which fires where the passage would otherwise be unpriced — so the wider read can replace a gap with an amount and can never change one.

#### Scenario: An ordinary ticketed section

- **WHEN** a route passes an entrance and later the exit whose gare code the entrance prices at 13.70 EUR
- **THEN** the journey records one passage named `<entrance> → <exit>` costing 13.70 EUR

#### Scenario: A barrier and a gantry on one journey

- **WHEN** a route passes a `passthrough` barrier priced 2.40 EUR and then a `gantry` priced 0.90 EUR
- **THEN** the journey records two passages costing 2.40 and 0.90 EUR, and no ticket was opened

#### Scenario: An exit with no entrance is priced from the gantry behind it

- **WHEN** a route crosses a `gantry` carrying no flat price with no ticket open, and later reaches an `exit` whose gare code the gantry's gare prices at 5.60 EUR
- **THEN** the journey records one passage named `<gantry> → <exit>` costing 5.60 EUR, and reports nothing unpriced

#### Scenario: The tariff is found under a sibling group of the gantry's gare

- **WHEN** the gantry's own mapping does not price the exit but another group carrying the gantry's gare code prices it at 5.60 EUR
- **THEN** the passage is priced at 5.60 EUR

#### Scenario: An exit with no gantry behind it stays unpriced

- **WHEN** an `exit` is reached with no ticket open and no gantry crossed since the last ticket ended
- **THEN** the passage is recorded unpriced as an exit without an entrance

#### Scenario: A gantry that charges flat is not also billed a section

- **WHEN** a route crosses a `gantry` carrying a flat price of 0.90 EUR and later an `exit` its gare prices
- **THEN** the gantry is charged 0.90 EUR and the exit is recorded unpriced as an exit without an entrance

#### Scenario: A crossed entrance reads only its own tariffs

- **WHEN** a ticket is open at an `enter` group that does not price the exit's gare code, and another group carrying that entrance's gare code does
- **THEN** the passage is recorded unpriced, and that other group's tariff is not used

#### Scenario: The charge and the quote agree

- **WHEN** a section opened at a gantry is both charged on the journey and quoted for the split advice
- **THEN** both report the same amount

### Requirement: A two-way booth is resolved by the side the route arrives from

A booth typed `bidirectional` SHALL act as an exit when the route reached it from one of its `inside_nodes`, and as an entrance when the route reached it from one of its `outside_nodes`.

A vehicle at an inside node is holding a ticket it will have to pay, so crossing the barrier closes that ticket. A vehicle at an outside node is circulating freely, so crossing it takes a ticket. All 47 two-way booths carry both lists.

Where the preceding node is in neither list, the system SHALL decide from the following node with the sense reversed: a following node that is inside means the vehicle is entering. Where neither node resolves, the passage SHALL be recorded unpriced.

The direction the vehicle travels SHALL NOT decide the sense on its own, and the ticket state SHALL NOT decide it either. Treating a two-way booth as an entrance whenever no ticket happens to be open books an exit as an entrance every time a journey leaves the network through one.

#### Scenario: Entering through a two-way barrier

- **WHEN** a route reaches a `bidirectional` booth from a node listed in its `outside_nodes`
- **THEN** a ticket is opened at that booth

#### Scenario: Leaving through a two-way barrier

- **WHEN** a route reaches a `bidirectional` booth from a node listed in its `inside_nodes` while a ticket is open
- **THEN** the ticket is closed and the passage is priced at the entrance's tariff for this booth's gare code

#### Scenario: The ticket state does not decide the sense

- **WHEN** a route reaches a `bidirectional` booth from an inside node with no ticket open
- **THEN** the passage is recorded unpriced as an exit without an entrance, and no ticket is opened

### Requirement: A passage that cannot be priced is recorded, not raised

The system SHALL record a passage it cannot price as a passage with no cost, carrying a reason, and SHALL continue accounting the rest of the journey.

The reasons SHALL be distinguished:

- an exit or a two-way exit reached with no ticket open;
- an entrance reached while a ticket is already open, which closes the earlier one unpriced;
- an exit whose gare code the open entrance does not price;
- a booth absent from the price file, or a booth whose gare code is unknown;
- a two-way booth whose neighbours resolve to neither side;
- a route that ends with a ticket still open.

An unpriceable passage SHALL NOT be silently charged 0 EUR. The journey SHALL report how many of its passages went unpriced, so an answer that is missing a toll says so.

A `passthrough` or `gantry` carrying no tariff SHALL NOT appear in the passage list, and SHALL still be counted among the unpriced. There is nothing to tell a driver about it: no amount, and a name that adds nothing to a road they are already looking at. It is still counted, because the journey must go on admitting that something was crossed and not charged; what stops is printing a line the reader cannot act on.

Every other unpriceable passage SHALL be listed. A ticketed section whose tariff is missing is a real charge of a real size that the driver will pay, and both its ends have names; leaving it out would hide money rather than hide noise.

Raising instead fails the whole journey over one barrier. Of 1 295 booths, 12 carry no gare code and 20 are absent from the price file, so this is a state a real route reaches.

#### Scenario: An exit without an entrance

- **WHEN** a route's first booth is typed `exit`, because the journey began inside the toll network
- **THEN** that passage is recorded unpriced with that reason, and the rest of the journey is accounted normally

#### Scenario: A journey ending inside the network

- **WHEN** a route's last booth opens a ticket that no later booth closes
- **THEN** a final unpriced passage records the open entrance, and the journey is still returned

#### Scenario: An unpriced gantry is counted but not listed

- **WHEN** a route crosses a gantry that carries no tariff
- **THEN** it does not appear in the passage list, and the count of unpriced passages includes it

#### Scenario: A ticketed section with no tariff is listed

- **WHEN** an entrance does not price the exit that closes its ticket
- **THEN** the passage is listed, named at both ends, and carries no cost

#### Scenario: An unpriced passage is visible

- **WHEN** a journey holds a passage that could not be priced
- **THEN** the answer reports the count of unpriced passages, and that passage carries no cost rather than a cost of zero

### Requirement: A passage is named from the operator's name for it

A passage SHALL be named by the first of these that exists, in this order:

1. the operator's name from `data/vinci_toll_booth.yaml`;
2. the OSM `name` from `data/osm_toll_booths.yaml`;
3. the booth's OSM node id.

A ticketed section SHALL be named `<entrance name> → <exit name>`, each end named by the same rule.

The operator's name comes first because it is what is written on the barrier a driver stops at. The OSM name comes next because it is a name: `Péage de Vienne` tells a reader where they are, and `OSM node 12288199204` tells them a fact about a database. The node id remains last so that a booth named nowhere is still identifiable — a fallback that identifies nothing would be worse than one that is ugly.

#### Scenario: A named section

- **WHEN** a ticket opened at VOREPPE BARRIERE is closed at MOIRANS
- **THEN** the passage is named `VOREPPE BARRIERE → MOIRANS`

#### Scenario: An unmapped booth

- **WHEN** a route passes a booth with no gare code whose node is named `Péage de Vienne` in OSM
- **THEN** the passage is named `Péage de Vienne`, not by its node id

#### Scenario: A booth nothing names

- **WHEN** a booth has neither a gare mapping nor an OSM name
- **THEN** the passage is named by that booth's OSM node id

### Requirement: The journey total is the sum of what was priced

The journey's cost SHALL be the sum of its priced passages, in euros.

The cost of the optimal route SHALL be reported beside the cost of the fast route, so that a driver sees what the detour saves. Where the two routes are the same route, the two costs are the same and the answer says so by reporting equal values, not by omitting one.

#### Scenario: Two routes, two costs

- **WHEN** a journey is answered
- **THEN** it carries a cost for the fast route and a cost for the optimal route, each the sum of that route's priced passages
