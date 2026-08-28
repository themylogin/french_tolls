## MODIFIED Requirements

### Requirement: A refinement is bought in two phases, and each is bought once

Refining and *seeing the result* are two questions, and they cost differently.

The **first phase** asks Google to drive the waypoints the route already has, reads the stretches where it went its own way, and produces the refined set. It is what a link needs: following a link requires the waypoints and nothing else.

The **second phase** asks Google to drive the refined set, and exists only to be looked at. It cannot be folded into the first: the route through the refined waypoints does not exist until it is asked for, and the first request's whole purpose is to find the places that route will differ.

A journey SHALL therefore cost at most two Google requests, ever — one if nobody looks at it. The second phase SHALL be performed only when a caller asks for the geometry, and SHALL NOT be performed by a redirect.

Where the first phase finds nothing to correct, the route it already has *is* the route the link produces, and the second phase SHALL be skipped. Such a journey costs one request whether or not anyone looks at it.

Each phase SHALL be stored as it completes, so a journey whose link was followed and is later looked at buys only the phase it is missing.

Stored SHALL be the refined waypoints, the waypoints the drawable route was driven through, Google's route geometry, its distance and duration, the faithfulness before and after, and when it was fetched.

A refinement SHALL be keyed exactly as a route answer is keyed, and `route-service` states that key. A refinement describes a particular optimal route, so it is stale exactly when that route is, and the two SHALL therefore be invalidated together and never separately.

Nothing SHALL invalidate a refinement automatically. A rebuilt pipeline leaves both the answer and the refinement in place, and an operator purges them by hand. This is what `route-service` decided for the answer, and a refinement that outlived the route it describes — or was discarded while that route stood — would be the one thing in the store that disagreed with it.

A refinement is paid for. Where the two could be treated differently, the refinement SHALL be the one kept: an answer recomputes in about a second, and a refinement costs up to two Google requests.

#### Scenario: A link costs one request

- **WHEN** a link is followed for a journey never asked about before
- **THEN** one Google request is made, and the geometry is not bought

#### Scenario: Looking at it afterwards buys only what is missing

- **WHEN** the control is used on a journey whose link has already been followed
- **THEN** one further request is made, and the total for that journey is two

#### Scenario: The second visitor pays nothing

- **WHEN** two visitors ask the same question about the same journey
- **THEN** the second makes no request and receives the same refinement

#### Scenario: A journey Google already agreed with

- **WHEN** the first phase finds no stretch to correct
- **THEN** no second request is made, and the route already obtained is the one drawn

#### Scenario: A rebuilt pipeline invalidates it

- **WHEN** the artefacts change, the cache is purged as a rebuild now requires, and the same journey is requested
- **THEN** the stored refinement is not used, and the refinement is bought again

#### Scenario: A rebuilt pipeline that was not purged does not

- **WHEN** the artefacts change and the same journey is requested without the cache being purged
- **THEN** the stored refinement is still used, because nothing detects that the route it describes has been recomputed

#### Scenario: The answer and the refinement are purged together

- **WHEN** the cache is purged after a pipeline rebuild
- **THEN** neither the answer nor the refinement for a journey survives, because the two share a key
