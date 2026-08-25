## ADDED Requirements

### Requirement: Gare pairs the operator does not sell

The override file SHALL accept a `prohibited_gare_pairs` section: a list of two-element lists of operator numbers, each an ordered pair the pipeline must never ask the rate service about.

Operator numbers SHALL be normalised to strings, as every other operator number in the file is, so a leading zero survives YAML reading them as integers.

Direction SHALL be part of the statement. Prohibiting A to B says nothing about B to A, and both SHALL be listed when both are meant.

A pair naming one gare twice SHALL be refused. Such a pair is already excluded by the rule that drops same-gare pairs, so stating it can only mean something else was intended.

The section exists for pairs that are not a journey however the road network reads — two ramps of one interchange under two codes, where a router asked to drive between them produces a loop out and back that crosses no booth and so resembles a ticket.

#### Scenario: A prohibited pair is loaded

- **WHEN** the file lists `["04355", "04354"]`
- **THEN** the overrides carry the ordered pair `04355` to `04354`

#### Scenario: Leading zeros survive

- **WHEN** the file lists `[04355, 04354]` unquoted
- **THEN** the overrides carry `"04355"` and `"04354"` as five-character strings

#### Scenario: A malformed entry is refused

- **WHEN** the section holds something other than a list, or an entry that is not a two-element list
- **THEN** the step stops and names the offending value

#### Scenario: A pair of a gare with itself is refused

- **WHEN** the file lists `["04355", "04355"]`
- **THEN** the step stops and says the pair names one gare twice
