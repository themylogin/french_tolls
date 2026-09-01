## ADDED Requirements

### Requirement: A route the pricing step cannot ask about is not selected

A route SHALL NOT be selected when it traverses a booth the override file types `absent_enter` or `absent_exit`.

Such a booth has no gare, so its passage cannot be submitted, and omitting only that passage would leave the neighbouring gare paired with a partner the vehicle never drove. The pricing step therefore drops the whole route, as `vinci-price-mapping` requires. A route that step will drop covers nothing: every priceable booth on it is discarded with it, and a booth no other route reaches carries no price at all.

The rule SHALL apply to a candidate route and to a route loaded from an existing route set alike. A route already on disk is no evidence that it can be priced, and the selection pass never revisits a route it has accepted, so one kept now would survive every rebuild — the same reason an endpoint that became ineligible is discarded at load.

The rule SHALL be applied to the booth ids the pricing step itself tests, which are the group representatives recorded in `covers`. Testing any other set would let the search accept a route the pricing step then drops, which is the failure this rule exists to remove.

A booth typed `absent_passthrough` SHALL NOT block a route. It forms no pair, so it drops out of the passage list and its route is submitted normally.

A selected route SHALL still record every booth it traverses in `covers`, `absent_*` booths included. This rule decides which routes are selected. It does not change what a selected route reports.

#### Scenario: A candidate crossing an absent half-pair

- **WHEN** a candidate route traverses a booth typed `absent_enter` or `absent_exit`
- **THEN** it is not selected, whatever else it covers

#### Scenario: The targets it would have covered stay outstanding

- **WHEN** the only candidate covering a target traverses a booth typed `absent_exit`
- **THEN** that candidate is not selected and the target remains in the uncovered set, so the search continues to look for another route to it

#### Scenario: A resumed route crossing an absent half-pair

- **WHEN** an existing route set is loaded and one of its routes traverses a booth typed `absent_enter`
- **THEN** that route is dropped and the targets it covered are searched for again

#### Scenario: An absent barrier does not block

- **WHEN** a candidate route traverses a booth typed `absent_passthrough` and no booth typed `absent_enter` or `absent_exit`
- **THEN** the rule does not exclude it

#### Scenario: A selected route still reports what it drove

- **WHEN** a selected route traverses a booth typed `absent_passthrough`
- **THEN** that booth appears in its `covers` list

#### Scenario: The two steps agree

- **WHEN** every route in a generated route set is offered to the pricing step
- **THEN** none of them is skipped for crossing a booth the operator does not carry

## MODIFIED Requirements

### Requirement: Coverage of the booth inventory

The coverage target for a booth that is not bidirectional SHALL be the booth itself. A bidirectional booth SHALL contribute one target per direction a route can actually drive through it, identified by `prev_node_id`. Passing such a gare one way does not pay the toll charged the other way.

A booth the override file types `absent_enter` or `absent_exit` SHALL NOT be a coverage target. No route that reaches it can be priced, so a route bought to cover it buys nothing, and the booths that route carries alongside are lost with it. Such a booth remains in the inventory and is still recorded in `covers` when a selected route happens to traverse it; it is only removed from what the search sets out to reach.

A booth typed `absent_passthrough` SHALL remain a coverage target. Its route is submitted normally, so reaching it prices the booths around it.

The union of the `covers` lists across all routes SHALL equal the full set of coverage targets, except for targets the routing engine cannot be made to traverse by any generated endpoint pair.

#### Scenario: Complete coverage

- **WHEN** every coverage target is traversed by at least one generated route
- **THEN** the union of all `covers` lists equals the target set and nothing is reported as uncovered

#### Scenario: A bidirectional booth needs both directions

- **WHEN** every route through a bidirectional booth arrives from the same predecessor
- **THEN** the other direction remains an uncovered target, even though the booth itself has been traversed

#### Scenario: Verification runs before the file is accepted

- **WHEN** the route set step finishes generating routes
- **THEN** it recomputes the union of `covers` and compares it against the target set before reporting success

#### Scenario: An absent half-pair is not a target

- **WHEN** the target set is built over an inventory containing a booth typed `absent_enter`
- **THEN** that booth contributes no target, and no route is searched for on its account

#### Scenario: An absent half-pair is not reported as uncovered

- **WHEN** a run completes and no route traverses a booth typed `absent_exit`
- **THEN** `data/uncovered_booths.json` does not name it, because it was never a target

#### Scenario: An absent barrier is still a target

- **WHEN** the target set is built over an inventory containing a booth typed `absent_passthrough`
- **THEN** that booth contributes a target exactly as an untyped booth does
