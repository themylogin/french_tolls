## MODIFIED Requirements

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
