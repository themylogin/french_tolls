## ADDED Requirements

### Requirement: A side the sweep leaves unobserved is retried against the place catalogue

Where a side receives no admitted observation, the system SHALL retry it against places drawn from the inventory's place catalogue, and SHALL settle it by the rules already in place.

The sweep's places come from `data/route_set.yaml`, which lists the places the coverage search used as route endpoints — 745 of them. The catalogue in `data/filtered.osm.pbf` holds every `place=` node the extract carries. A side goes unobserved when no offered target is best reached that way, and a target too far off is beaten by the motorway however the roads lie.

Péage de Thèze, booth 986537073, is the case. Its free side is a slow local road against the A 65, and its nine route-set places are all reached past another barrier. Lalonquette — `place=village`, node 1825323182 — is 2.0 km up that local road and is not in the route set. Against it the sweep settles the side at once, in both directions, with one booth on the route.

The catalogue SHALL be consulted only for a side the sweep leaves unobserved. Every booth the sweep settles SHALL settle from the same targets it uses today, so this cannot move a side that is already established.

Catalogue targets SHALL be selected by the rule the sweep already uses for places — nearest per bearing sector, within the same distance bounds — so that a side is offered a destination in its own direction.

The verdict, the between-booth filter and the admission rules SHALL be unchanged. Only where the targets come from changes.

#### Scenario: A side no route-set place reaches is settled from the catalogue

- **WHEN** the sweep leaves node 10977821568 of booth 986537073 unobserved
- **THEN** the step retries that side against catalogue places and settles it `outside` from a village 2.0 km along it

#### Scenario: A settled booth is not revisited

- **WHEN** every side of a booth received an observation from the sweep
- **THEN** the catalogue is not consulted for it, and its sides are those the sweep established

#### Scenario: The verdict rules are unchanged

- **WHEN** a catalogue route reaches a place having crossed no booth
- **THEN** the side is outside, by the same rule that governs a route-set place

### Requirement: The report says which sides rest on the catalogue

A side settled from the catalogue SHALL be reported as such, apart from the sweep's counts.

A reader deciding whether to trust a side should not have to work out which pool produced it, and the count is what would say the sweep's own places have stopped being enough.

#### Scenario: A catalogue side is named

- **WHEN** the step settles a side from the catalogue
- **THEN** it reports that booth and that node, apart from the ordinary counts

## MODIFIED Requirements

### Requirement: A side with no evidence is reported, not fatal

A node no admitted observation reached, after both the sweep and the catalogue retry, SHALL be reported and SHALL NOT stop the step. The booth does not settle, and nothing downstream may treat it as settled.

That is a gap in what the probe reached, of the same kind as an uncovered coverage target, and this pipeline reports those rather than dying on them.

#### Scenario: An unobserved side is reported

- **WHEN** a booth ends the run with a node in neither set
- **THEN** the booth and that node are reported, and the step continues

#### Scenario: The catalogue is tried before the report

- **WHEN** the sweep leaves a side unobserved
- **THEN** the side is reported unobserved only after the catalogue retry has also failed to settle it
