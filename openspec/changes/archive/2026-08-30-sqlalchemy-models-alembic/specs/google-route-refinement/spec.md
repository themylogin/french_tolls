## ADDED Requirements

### Requirement: A refinement is bought in two phases, and nothing is kept between them

Refining and *seeing the result* are two questions, and they cost differently.

The **first phase** asks Google to drive the waypoints the route already has, reads the stretches where it went its own way, and produces the refined set. It is what a link needs: following a link requires the waypoints and nothing else.

The **second phase** asks Google to drive the refined set, and exists only to be looked at. It cannot be folded into the first: the route through the refined waypoints does not exist until it is asked for, and the first request's whole purpose is to find the places that route will differ.

The second phase SHALL be performed only when a caller asks for the geometry, and SHALL NOT be performed by a redirect.

Where the first phase finds nothing to correct, the route it already has *is* the route the link produces, and the second phase SHALL be skipped.

**A refinement SHALL NOT be stored.** Each ask buys what it needs and keeps nothing. A journey therefore costs one request per redirect and two per look at the geometry, without bound, and the same journey asked about twice costs twice.

The guarantee that a journey cost at most two Google requests ever is withdrawn. It was worth what it cost while it held, and it is being given up with the store that held it — for the reason the store is being given up, not because the amortisation stopped being valuable. **This is the price of the change, and it is stated here rather than left to be found in a bill.**

`web-front-end` requests a refinement for every journey calculated while its debug setting is on. Under that setting the month's ceiling is now consumed at two requests per calculation.

What bounds the spending is unchanged. `route-service` and this capability's two-budget requirement still apply: every request is claimed against the month's ceiling before it is issued, and a journey that cannot afford one still returns its unrefined waypoints naming the budget that stopped it. What is lost is the amortisation, not the ceiling.

Nothing stored means nothing stale. A rebuilt pipeline needs no purge for a refinement to stop describing a route that no longer exists, and a refinement bought at one routing preference can no longer be read back under another.

#### Scenario: A link costs one request

- **WHEN** a link is followed for a journey
- **THEN** one Google request is made, and the geometry is not bought

#### Scenario: Looking at it costs two

- **WHEN** the geometry is asked for
- **THEN** the first phase and the second phase are both bought, and the total for that ask is two

#### Scenario: The second visitor pays the same as the first

- **WHEN** two visitors ask the same question about the same journey
- **THEN** each pays for their own requests, and the second receives a refinement bought fresh

#### Scenario: A journey Google already agreed with

- **WHEN** the first phase finds no stretch to correct
- **THEN** no second request is made, and the route already obtained is the one drawn

#### Scenario: A redirect never buys the geometry

- **WHEN** a redirect is served
- **THEN** only the first phase is bought

#### Scenario: A rebuilt pipeline needs no purge

- **WHEN** the artefacts change and the same journey is refined
- **THEN** the refinement is bought against the route as it is now, because no earlier one was kept

#### Scenario: An exhausted budget still answers

- **WHEN** the month's ceiling is reached and a refinement is asked for
- **THEN** no request is made, and the answer carries the unrefined waypoints and names the budget that stopped it

## REMOVED Requirements

### Requirement: A refinement is bought in two phases, and each is bought once

**Reason**: The store that made "bought once" true is removed. `route-service` removes the cache key that a refinement shared with a route answer, and the refinements table goes with it, so every clause about what is stored, when it is invalidated, and which of the two to keep when they could be treated differently is about something that no longer exists.

The two-phase structure survives unchanged and is restated in **A refinement is bought in two phases, and nothing is kept between them**, together with what the loss of storage costs.

**Migration**: None for a caller. The refinement returned is the same shape, carries the same fields, and is reached the same way. The difference is what it costs: a journey no longer amortises, so a deployment running with `web-front-end`'s debug setting on should expect the month's ceiling to be reached sooner and should set `GOOGLE_MAX_REQUESTS_PER_MONTH` against the number of calculations expected rather than the number of distinct journeys.
