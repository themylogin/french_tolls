## MODIFIED Requirements

### Requirement: A stretch Google went its own way becomes a waypoint

The system SHALL find every stretch of Google's route lying outside a corridor of the optimal route, measured as `google-route-comparison` measures it.

The system SHALL rank those stretches by their length weighted by where they begin. For a stretch whose bypassed portion of the optimal route begins `dist` metres from the origin along an optimal route of `total` metres, the rank SHALL be the stretch's length multiplied by `1.0 - (dist / total) / 2`.

Both `dist` and `total` SHALL be measured along the **optimal route**, not along Google's. The driver follows the optimal route, so it is the only route along which "how far in" describes what the driver experiences. Where the bypassed portion is located by two ends, `dist` SHALL be the nearer of them to the origin.

A stretch at the origin therefore counts for its full length, and a stretch at the destination for half. The purpose is that a driver follows a link from its beginning: a correction near the origin is reached by everyone who follows the link at all, while a correction near the destination is reached only by a journey that is driven to the end rather than abandoned, interrupted, or re-requested from a new position. Ranking by raw length spends a scarce budget as though every kilometre were equally likely to be driven.

For each of the highest-ranked stretches, up to the waypoint budget, the system SHALL place one new waypoint **on the optimal route**, at the midpoint by distance of the portion of the optimal route that the stretch bypassed.

The waypoint SHALL NOT be placed on Google's own path. The purpose is to name a point on the road the driver was meant to take; naming one on the road they are being steered away from would confirm the detour rather than correct it.

New waypoints SHALL be merged into the existing list in the order the optimal route reaches them, because Google is asked to visit them in order and a list in another order describes a different journey.

The ranking SHALL decide only which stretches are corrected. It SHALL NOT affect where a waypoint is placed within its stretch, nor the order the waypoints appear in the link.

#### Scenario: An earlier stretch outranks a longer later one

- **WHEN** the budget is one, and Google leaves the corridor for 40 km beginning 50 km along a 1 000 km optimal route, and again for 60 km beginning 950 km along it
- **THEN** the earlier stretch is chosen, because 40 × 0.975 exceeds 60 × 0.525

#### Scenario: A later stretch still wins when it is long enough

- **WHEN** the budget is one, and Google leaves the corridor for 20 km near the origin and for 60 km near the destination of the same 1 000 km route
- **THEN** the later stretch is chosen, because the weight halves a stretch at most and cannot overturn a threefold difference in length

#### Scenario: Stretches at the same place are ranked by length

- **WHEN** two stretches begin at the same distance along the optimal route
- **THEN** the longer is ranked first, because they carry the same weight

#### Scenario: The worst stretches are chosen

- **WHEN** Google leaves the corridor over seventeen stretches and the budget is two
- **THEN** a waypoint is placed for the two highest-ranked, and none for the other fifteen

#### Scenario: The waypoint sits on the intended road

- **WHEN** a stretch of Google's route bypasses 86 km of the optimal route
- **THEN** the new waypoint is a point of the optimal route, halfway along those 86 km

#### Scenario: Ranking does not move a waypoint

- **WHEN** a stretch is chosen under the weighted ranking
- **THEN** its waypoint is at the midpoint of the bypassed portion, the same point raw-length ranking would have produced for it

#### Scenario: Order is preserved

- **WHEN** a new waypoint falls between the third and fourth existing ones
- **THEN** the merged list carries it in that position

#### Scenario: Google already followed the route

- **WHEN** no stretch of Google's route lies outside the corridor
- **THEN** no waypoint is added and the link is unchanged
