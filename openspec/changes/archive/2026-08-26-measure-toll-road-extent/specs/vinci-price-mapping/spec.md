## MODIFIED Requirements

### Requirement: Price file output format

The system SHALL write `data/vinci_price.yaml` as a mapping with two top-level keys, `toll_booths` and `routes`.

`toll_booths` SHALL map an OSM booth group id to a mapping carrying `type`, one of `passthrough`, `enter`, `exit`, `bidirectional`, or `gantry`.

- A `passthrough` entry SHALL also carry `price`, a number of euros.
- An `enter` entry SHALL carry `prices`, a mapping from an exit gare code to a number of euros, unless it is a booth the override file states, whose partners are priced by the direct pricing step and which therefore carries `type` alone until that step has run.
- An `exit` entry SHALL carry `type` alone, plus `last_toll_node_id` once the toll extent step has measured it.
- A `bidirectional` or `gantry` entry MAY carry `price`, `prices`, both, or neither. Neither means every route met it only as the end of a section, which records no amount, exactly as for an `exit`.

An entry MAY additionally carry `first_toll_node_id`, `last_toll_node_id`, or both: the OSM node where the tolled road begins and ends at that booth. An `enter` entry carries the first, an `exit` entry the last, and a `bidirectional` entry carrying `prices` carries both. They are absent until the toll extent step has run, and their absence is not a gap — a consumer falls back to the booth's own node.

Each node id SHALL be accompanied by its coordinates, `first_toll_latlon` and `last_toll_latlon`, a two-element list of latitude and longitude. A node id alone cannot be routed to. A node id without its coordinates, or coordinates without their node id, SHALL stop the step that reads the file.

Within an entry the keys SHALL be written in the order `type`, `price`, `first_toll_node_id`, `first_toll_latlon`, `last_toll_node_id`, `last_toll_latlon`, `prices`.

`routes` SHALL hold the `from`/`to` pairs already processed. A pair naming one booth twice is a single-passage request rather than a route.

`toll_booths` keys SHALL be written in ascending numeric order, and `prices` keys in ascending code order, so a rerun that learns nothing produces no diff.

The file SHALL be written to a temporary name and renamed into place, and that temporary name SHALL be unique to the writing process. Four steps write this file and three of them write it repeatedly, so two runs against one tree is a mistake an operator can make. With a shared temporary name that mistake destroys the file rather than merely racing: both write `<path>.part`, one renames it, and the other's rename finds nothing there and fails with the file gone. With a per-process name the loser overwrites the winner, which is recoverable by re-running. A partial write SHALL leave no temporary file behind.

```yaml
toll_booths:
  27174404:
    type: enter
    first_toll_node_id: 5122294120
    first_toll_latlon: [49.20738, 2.15446]
    prices:
      "03086": 6.8
  130221205:
    type: exit
    last_toll_node_id: 240997497
    last_toll_latlon: [49.26640, 2.10175]
  289635259:
    type: bidirectional
    first_toll_node_id: 1830420133
    first_toll_latlon: [48.20461, 5.83112]
    last_toll_node_id: 385970534
    last_toll_latlon: [48.19875, 5.84003]
    prices:
      "09170": 4.3
  4172775770:
    type: passthrough
    price: 55.5
  11578487423:
    type: gantry
    price: 0.9
    prices:
      "22535": 1.9
  609218048:
    type: passthrough
    price: 7.8
routes:
  - from: 547958
    to: 26692263
  - from: 4172775770
    to: 4172775770
```

#### Scenario: The file is written

- **WHEN** the step completes
- **THEN** `data/vinci_price.yaml` parses as YAML with top-level `toll_booths` and `routes` keys

#### Scenario: An exit carries no amount

- **WHEN** a group recorded as `exit` is inspected
- **THEN** it carries `type`, and `last_toll_node_id` if the toll extent step has measured it, and no amount of any kind

#### Scenario: An extent is recorded

- **WHEN** the toll extent step has measured an `enter` booth
- **THEN** its entry carries `first_toll_node_id` as an integer OSM node id and `first_toll_latlon` as a two-element list, alongside `type` and `prices`

#### Scenario: A node id without its coordinates

- **WHEN** an entry carries `last_toll_node_id` and no `last_toll_latlon`
- **THEN** the step reading the file stops and names the booth, rather than recording an extent nothing can route to

#### Scenario: A file without extents is still valid

- **WHEN** the price file is read before the toll extent step has ever run
- **THEN** no entry carries either extent field, and every step that reads the file accepts it

#### Scenario: A typed entry that was only ever a section end

- **WHEN** every route crossing a `gantry` group met it as the end of a section
- **THEN** its entry carries `type` alone, and the step does not treat that as a gap

#### Scenario: A stated entrance before the direct pricing step

- **WHEN** a booth the override file states `enter` has been recorded and the direct pricing step has not yet run
- **THEN** its entry carries `type` alone, and the step does not treat that as a gap

#### Scenario: A single-passage request is recorded under routes

- **WHEN** a stated barrier has been asked about
- **THEN** `routes` carries an entry whose `from` and `to` are both that booth's node id

#### Scenario: Rewriting is stable

- **WHEN** a complete file is written again from the same state
- **THEN** the result is byte-identical

#### Scenario: Two runs against one tree

- **WHEN** two processes write the price file at overlapping times
- **THEN** each writes its own temporary file, and the file that survives is one of the two complete versions rather than absent

#### Scenario: A failed write leaves nothing behind

- **WHEN** writing the file fails partway
- **THEN** no temporary file is left in `data/`, and the previous file is untouched

#### Scenario: An earlier step does not drop the extents

- **WHEN** `build_vinci_prices` or `build_vinci_direct_prices` rewrites a file that already carries extents
- **THEN** every extent it did not itself produce is still there afterwards
