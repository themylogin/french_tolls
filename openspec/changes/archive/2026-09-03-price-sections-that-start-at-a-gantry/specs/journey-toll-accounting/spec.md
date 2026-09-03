## MODIFIED Requirements

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
