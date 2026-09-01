## MODIFIED Requirements

### Requirement: A booth the operator does not carry

A booth whose override is one of the `absent_*` types SHALL stay in the inventory: it is a real booth on a real road that a route drives through. The requirement that the gare mapping find a gare for it SHALL be waived, because the operator's placemark layer does not carry it and there is no gare to find.

The accepted values SHALL be `absent_enter`, `absent_exit`, and `absent_passthrough`, recording how a route meets the booth.

Whether such a booth is a coverage target follows from that distinction, and `route-set-generation` settles it. An `absent_passthrough` drops out of a passage list harmlessly, so it remains a target. An `absent_enter` or `absent_exit` makes its whole route unaskable, so it is not a target and no route may be selected that traverses it.

An `absent_*` override SHALL NOT be combined with a `vinci` entry: stating that the operator does not carry the booth and then naming its gare is a contradiction.

`price` SHALL state what such a booth charges, and SHALL be accepted only with `absent_passthrough`. An enter or an exit is one half of a journey whose charge depends on where the other half was, so there is no single price to state. `price` SHALL be a number.

#### Scenario: An absent booth stays in the inventory

- **WHEN** a booth carries `type: absent_passthrough`
- **THEN** it appears in the inventory and remains a coverage target, unlike an ignored booth

#### Scenario: An absent half-pair stays in the inventory and stops being a target

- **WHEN** a booth carries `type: absent_enter` or `type: absent_exit`
- **THEN** it appears in the inventory, unlike an ignored booth, and is not a coverage target

#### Scenario: An absent booth needs no gare

- **WHEN** the gare mapping runs over a route that drives through an absent booth
- **THEN** that booth is not required to have a gare

#### Scenario: Absent and vinci together

- **WHEN** an entry carries both an `absent_*` type and a `vinci` entry
- **THEN** the step stops and names that entry

#### Scenario: Price on the wrong type

- **WHEN** `price` appears on any entry whose type is not `absent_passthrough`
- **THEN** the step stops and names the entry

#### Scenario: Price is not a number

- **WHEN** `price` carries a value that is not a number
- **THEN** the step stops and names the entry and the value
