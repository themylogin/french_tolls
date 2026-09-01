## MODIFIED Requirements

### Requirement: A two-way booth is measured in both roles from its free side

A `bidirectional` booth that carries `prices` SHALL record both `first_toll_node_id` and `last_toll_node_id`, because it is an entrance to a journey driven one way and an exit to the same journey driven the other.

The two roles SHALL be told apart by the sides `data/bidirectional_booth_sides.yaml` already records. A region SHALL leave the booth only by a node that is not in the booth's `inside_nodes`: the entrance's region grows back from the free side, and the exit's region forward onto it. A region grown through the inside nodes is the other role's road.

A two-way booth whose sides did not settle SHALL be left unmeasured and reported. Its `inside_nodes` are incomplete, so the side restriction that tells its two roles apart cannot be applied, and a region grown without one runs through the toll side and answers for the wrong role. An absent extent falls back to the booth node, which is a gap; a region grown through the wrong side is a wrong measurement.

A booth did not settle when the inventory records an adjacent node that appears in neither of its lists — the test `bidirectional-booth-sides` prescribes.

A `bidirectional` booth carrying no `prices` SHALL be skipped. It is a barrier: no journey has it as an end, so no tariff is divided by a distance from it.

A two-way booth SHALL NOT be given a larger sample than a one-way one, because no sample is taken. The 64 roles that fell below the convergence floor at N=24, and the 33 that stayed unmeasured at four times that, SHALL be measured like any other.

#### Scenario: Both roles are recorded

- **WHEN** a `bidirectional` booth carrying `prices` is measured
- **THEN** its entry carries both `first_toll_node_id` and `last_toll_node_id`, each on the free side

#### Scenario: The toll side is not entered

- **WHEN** a two-way booth's region is grown for its exit role
- **THEN** no node of its `inside_nodes` is used to leave the booth

#### Scenario: An unsettled two-way booth is not measured

- **WHEN** a `bidirectional` booth has an adjacent node in neither of its side lists
- **THEN** no extent is derived for it and it is reported, rather than a region being grown with no side restriction

#### Scenario: A barrier is skipped

- **WHEN** a `bidirectional` booth carries no `prices`
- **THEN** no extent is recorded for it and it is not reported as a gap

#### Scenario: A booth with few reachable places is still measured

- **WHEN** a two-way booth whose free side reaches few places is measured
- **THEN** its extent is derived from its region like any other booth's
