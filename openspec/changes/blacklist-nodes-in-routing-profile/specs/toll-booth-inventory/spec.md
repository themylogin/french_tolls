## REMOVED Requirements

### Requirement: Hand-maintained booth overrides

**Reason**: Replaced by "Hand-maintained booth decisions" below. The file loses its `nodes_blacklist` section, so the permitted top-level keys fall from three to two and the two scenarios validating that section have nothing left to validate.

**Migration**: Move the node ids to `data/nodes_blacklist.yaml`, under a `nodes_blacklist` key. Leaving them in the override file now stops the step, as any unknown section does.

## ADDED Requirements

### Requirement: Hand-maintained booth decisions

The extraction step SHALL read `data/osm_toll_booths_overrides.yaml`, a hand-maintained input recording decisions that no rule can derive from the extract. A missing file SHALL be treated as an empty set of overrides.

The file SHALL be a mapping with two permitted top-level keys. `toll_booths` holds decisions about individual booths, keyed by OSM node id; an entry SHALL carry at least one of `type`, `parent_id`, `vinci`, or `price`. `duplicate_gares` holds operator numbers of gares that one route may legitimately pay twice.

A top-level key that is neither of the two SHALL stop the step. A mistyped section name would otherwise read as an absent section, and every entry beneath it would be dropped without a word.

Operator numbers in `duplicate_gares` SHALL be compared as strings. They carry leading zeros, which YAML reads away when the value is unquoted, so `04210` and `"04210"` SHALL name the same gare.

Blacklisted nodes are not booth overrides and SHALL NOT appear here. They describe the road graph rather than any booth, they are enforced by the routing profile, and `build-pipeline` gives them a file of their own.

#### Scenario: Overrides are read

- **WHEN** the extraction step runs with the override file present
- **THEN** it applies the entries in that file before writing the inventory

#### Scenario: No override file

- **WHEN** `data/osm_toll_booths_overrides.yaml` does not exist
- **THEN** the step runs as though it were empty, rather than failing

#### Scenario: An entry carries no key at all

- **WHEN** an entry is empty
- **THEN** the step stops and names that entry

#### Scenario: An unknown key

- **WHEN** an entry carries a key other than `type`, `parent_id`, `vinci`, or `price`
- **THEN** the step stops and names the entry and the key

#### Scenario: An unknown top-level section

- **WHEN** the file carries a top-level key other than `toll_booths` or `duplicate_gares`
- **THEN** the step stops and names it, rather than silently ignoring everything under it

#### Scenario: A leftover nodes_blacklist section stops the step

- **WHEN** the file still carries a `nodes_blacklist` key
- **THEN** the step stops and names it, as it would any unknown section

#### Scenario: A gare number written without quotes

- **WHEN** `duplicate_gares` lists `04210` unquoted, which YAML reads as an integer
- **THEN** it still names gare `04210`, with the leading zero intact

#### Scenario: duplicate_gares is not a list

- **WHEN** `duplicate_gares` carries something other than a list
- **THEN** the step stops and names what it found
