## MODIFIED Requirements

### Requirement: The toll total is tested against booths written by hand

The suite SHALL build the booth table in the test — booths, lanes, types, gare codes, tariffs, and the two sides of a two-way barrier — and SHALL run the accounting over a node sequence it writes.

Hand-built booths are what make the states testable. A route that begins inside the toll network, an entrance never closed, a gare the entrance does not price, a booth absent from the price file: each of these is three lines to write and a hunt through 1 295 real booths to find.

The suite SHALL demonstrate:

- an entrance and a later exit produce one passage named `<entrance> → <exit>`, priced by the exit's gare code;
- a `passthrough`, and a `gantry` carrying a flat price, are each charged their own amount and neither opens nor closes a ticket;
- an `exit` reached with no ticket open is priced from the last `gantry` crossed where that gantry's gare prices it, and stays unpriced where there is no such gantry;
- that look-back finds the tariff under a sibling group of the gantry's gare when the gantry's own mapping does not carry it;
- a `gantry` carrying a flat price is charged there and does not also start a section;
- a `bidirectional` barrier reached from an outside node opens a ticket, and the same barrier reached from an inside node closes one, so the two directions produce different passages;
- a `bidirectional` barrier whose preceding node is neither side is resolved from the following node with the sense reversed, and one whose neighbours resolve to neither side is recorded unpriced;
- a node the inventory records as a lane is accounted against the booth it is a lane of;
- consecutive nodes resolving to one booth produce one passage, and the same booth reached again later produces another;
- a tariff is never read from a booth other than the open entrance when an entrance was crossed, even where another booth of the same gare code carries one;
- the total is the sum of the priced passages.

The look-back cases are listed because a suite that tested only the flat gantry is how a real route came to be answered with an unpriced section between Chambéry Nord and Annecy Centre. The two directions of the gare rule are listed together, because the difference between them — widening the lookup where no entrance was crossed and nowhere else — is the whole of what keeps the change from moving fares that are correct today.

#### Scenario: A ticketed section is priced by the exit's gare

- **WHEN** a route passes an entrance pricing gare `00002` at 13.70 EUR, and later the exit carrying that gare
- **THEN** one passage named `<entrance> → <exit>` costs 13.70 EUR

#### Scenario: The two directions of a two-way barrier differ

- **WHEN** a two-way barrier is crossed from an outside node, and then in a second journey from an inside node
- **THEN** the first opens a ticket and the second closes one, and the two passage lists differ

#### Scenario: A lane is charged as its plaza

- **WHEN** the route's node sequence carries a lane recorded as an alias
- **THEN** the passage is accounted against the booth that lane belongs to

#### Scenario: One plaza, one passage

- **WHEN** two consecutive nodes resolve to the same booth
- **THEN** one passage is recorded

#### Scenario: The look-back is demonstrated

- **WHEN** the suite builds a `gantry` carrying a tariff for a later exit's gare, with no entrance between them
- **THEN** a test shows one passage named `<gantry> → <exit>` at that tariff, and another shows the same exit unpriced with no gantry behind it

#### Scenario: The gare-wide lookup is demonstrated

- **WHEN** the suite builds a gantry whose own mapping omits the exit's gare, beside a booth of the same gare that prices it
- **THEN** a test shows the passage priced at that tariff

#### Scenario: A flat gantry is not read as a section start

- **WHEN** the suite builds a gantry carrying both a flat price and a tariff for a later exit
- **THEN** a test shows the flat price charged and the exit recorded unpriced

#### Scenario: A crossed entrance reads only its own tariffs

- **WHEN** the suite builds two booths carrying one gare code, only one of which prices the exit
- **THEN** a test shows the passage recorded unpriced when the other is the open entrance
