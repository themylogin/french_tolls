## Purpose

Defines what it means for another router's route to cost a driver the same as ours, how a route known only as geometry is turned into the toll booths it crosses, and what the system does when that cannot be established.

## ADDED Requirements

### Requirement: Two routes are equivalent when one pays no toll the other does not

The system SHALL judge a foreign route against the optimal route by the toll booths each crosses.

A foreign route SHALL be **equivalent** when every booth it crosses is one the optimal route crosses too. It need not cross all of them: a route paying strictly fewer of our tolls costs the driver less, and there is nothing to correct about that. A route crossing a booth the optimal route avoids costs them money they did not agree to, and is not equivalent however closely it follows our road.

Equivalence SHALL be decided on the booths themselves rather than on what they come to in euros. Two different plazas can charge the same amount, and a comparison of totals would call that agreement.

Booths SHALL be identified as `journey-toll-accounting` identifies them, through the inventory's aliases, so that a plaza is one booth whichever of its lanes a router drove.

#### Scenario: The same booths, a different road

- **WHEN** a foreign route crosses exactly the booths the optimal route crosses
- **THEN** it is equivalent, whatever share of its length ran along ours

#### Scenario: Fewer booths is not a fault

- **WHEN** a foreign route crosses a subset of the optimal route's booths
- **THEN** it is equivalent, because the driver pays less

#### Scenario: One extra booth is a fault

- **WHEN** a foreign route crosses every booth the optimal route does, and one more
- **THEN** it is not equivalent, however faithfully it followed the road

#### Scenario: A plaza is one booth whichever lane was driven

- **WHEN** the two routes cross the same plaza by different lanes
- **THEN** both resolve to the same booth and the plaza does not count as a difference

### Requirement: A route known only as geometry is matched onto the graph to price it

Google returns a route as a polyline. This project prices a route from node ids. The system SHALL recover them by matching the geometry onto the untouched graph, and SHALL then price it exactly as it prices its own routes.

**The whole trace SHALL be matched in a single request.** Matching it in windows was the sole cause of every incorrect result found while establishing this: a window is matched with no knowledge of the road travelled before it, so at a boundary the matcher may begin on a slip road and rejoin later. Measured on one journey, that produced a four-hundred-metre excursion which bypassed a plaza entirely and understated the toll by €13.70, on a route whose geometry was identical to ours.

**Each leg's leading node SHALL be discarded except the first.** A leg's node annotation begins with the node *preceding* its start, because the tracepoint snapped partway along a segment — the same behaviour `waypoint-route-search` already forgives when it verifies a leg. Retained, it makes the sequence step back and forward across a booth, and one crossing becomes two charges. Measured, three phantom crossings and €3.00 on a route identical to ours.

**The trace SHALL be thinned before it is sent**, to a spacing chosen by measurement, keeping its two ends. Thinning was expected to be a saving and turned out to be a correction as well: measured over 210 journeys, an untouched trace is returned in pieces on four of them and a trace at one point per kilometre on eleven, while one at a point every 250 m is priced correctly on all 210, in a twelfth of a second.

Density is still not what makes a match *right* — the single request is. Thinning decides what the request costs, and at both extremes it decides whether the matcher keeps hold of the road at all.

#### Scenario: Our own route prices back to our own bill

- **WHEN** the optimal route's own geometry is matched and priced
- **THEN** it yields the booths and the total the route's own node ids yield

#### Scenario: One request, not several

- **WHEN** a trace is matched
- **THEN** it is sent as one request, so the matcher has the whole road as evidence

#### Scenario: A repeated leg head does not become a second charge

- **WHEN** a leg boundary falls beside a booth
- **THEN** the booth is charged once

#### Scenario: A trace is thinned, and keeps its ends

- **WHEN** a trace is prepared for matching
- **THEN** its points are spaced at the measured distance, and its first and last points are the ones the route began and ended at

### Requirement: What cannot be priced is not equivalent

Where the tolls a foreign route pays cannot be established, the system SHALL NOT treat it as equivalent, and SHALL fall back to the geometric test.

The matcher can fail: it can break a trace into pieces where it loses confidence, and a break between an entry and its exit leaves a ticket open and misprices everything after it. Not knowing what a route costs is not the same as knowing it costs the same.

The system SHALL be able to say which of the two decided a journey, so that a link accepted because Google drove our road can be told from one accepted because it pays our tolls.

#### Scenario: A broken trace falls back

- **WHEN** the matcher returns the trace in more than one piece
- **THEN** the route is judged on overlap instead, and is not called equivalent

#### Scenario: The reason is available

- **WHEN** a route is accepted
- **THEN** the system reports whether it was accepted on its road or on its tolls
