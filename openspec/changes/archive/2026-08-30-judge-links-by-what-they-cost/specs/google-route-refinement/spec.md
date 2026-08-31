## MODIFIED Requirements

### Requirement: How faithfully Google followed is part of the answer

The system SHALL report, with a refinement, the share of Google's route by length that ran within the corridor of the optimal route.

A configured threshold SHALL define what counts as following it. The system SHALL NOT decide what to do about a route that falls short — that belongs to the caller — but SHALL make the judgement available so that every caller applies the same one.

The threshold SHALL default to the share `google-route-comparison` already uses to separate a route Google drove from one it did not, so that what the evaluation calls faithful and what the bot calls followable are the same thing.

**The share is no longer the only thing a caller judges on.** It answers "did Google drive our road", and the question a driver has is "will I pay what you told me". `toll-equivalence` answers the second, and a caller may accept a route on either. The share remains because it is cheap, because it is what the evaluation reports, and because it is the answer when the tolls cannot be established.

Measured over 205 journeys the two disagree in both directions: 72 of the 100 routes the share rejects pay identical tolls, and 5 of the routes it accepts cross a booth the optimal route does not.

#### Scenario: The share is reported

- **WHEN** a refinement is returned
- **THEN** it carries the share of Google's route that ran within the corridor

#### Scenario: One threshold, two readers

- **WHEN** the evaluation and the drive flow judge the same route
- **THEN** both use the same configured share

#### Scenario: The share does not decide alone

- **WHEN** a route falls below the share but pays no toll the optimal route does not
- **THEN** nothing in the refinement calls it unacceptable; what to do about it is the caller's
