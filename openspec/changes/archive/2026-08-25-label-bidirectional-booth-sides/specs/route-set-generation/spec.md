## ADDED Requirements

### Requirement: The route search does not classify booth sides

The route search SHALL NOT attempt to tell a two-way booth's sides apart.

Which side of such a booth lies on the toll network is settled by probing the router against booths whose `enter`/`exit` role the operator has already answered for, and that role does not exist until the pricing step has run. The search runs long before it, so the only quantity available to it is direction of travel — and direction of travel does not separate the sides, because an ordinary interchange ramp is driven both ways.

`covers` SHALL continue to record the node a route arrived from for a two-way booth, so that the two directions remain separate coverage targets. That is a statement about coverage, not about which side is which.

#### Scenario: The route set carries no side classification

- **WHEN** the route set is written
- **THEN** it carries no `inside_nodes`, `outside_nodes`, or equivalent per-booth side records

#### Scenario: Coverage still distinguishes the two directions

- **WHEN** a two-way booth is traversed
- **THEN** `covers` records the node the route arrived from, and both directions remain targets
