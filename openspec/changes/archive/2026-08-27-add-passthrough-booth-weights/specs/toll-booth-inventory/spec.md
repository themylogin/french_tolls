## ADDED Requirements

### Requirement: Every booth carries the nodes a vehicle reaches after passing it

The system SHALL write `onward_nodes` on every entry under `toll_booths` and `aliases`: a mapping from the id of each node a vehicle reaches immediately after passing **that** node, one for each direction it can leave by, to that node's position in latitude, longitude order, in ascending numeric key order.

A booth node is a point, and what a consumer needs to act on it is the arc a vehicle drives next. That arc is a property of the road network, so nothing but the extract can answer it, and asking the extract again downstream would mean a second pass over the plaza neighbourhoods for a question this step has already answered. Measured, the field is 1 613 arcs over 1 556 lane nodes: 1 502 nodes leave by one arc and 54 by two.

The position is carried for the same reason `passage` carries positions rather than ids: a consumer that has to route across the arc has nowhere to look a node id up. The node beyond a booth is an ordinary way node, so it appears nowhere else in the inventory, and no routing service will translate an id into a point. A node the extract gives no position for SHALL be refused rather than written without one.

The field SHALL be written for every entry, whatever the booth's `type` and whatever the operator charges for it. This step reads no price file, so it cannot know which booths a consumer will need the field for, and a field written for some booths would carry a distinction this step has no basis for.

The field SHALL name the arcs **as the extract tags them**, over the road classes the car profile gives a speed to. That is wider than the through-road classes the grouping uses, deliberately: the grouping filter exists to keep a car park barrier out of the inventory and to stop a private forecourt manufacturing a shared predecessor, and neither reason bears on what lies immediately beyond a booth a vehicle has already reached. Measured, the wider set adds three arcs over the whole inventory, all of class `service`.

Direction SHALL be read from the extract uncorrected by any override. An override that states a two-way-tagged booth is really one-way corrects this step's grouping, not the road: the routing graph is built from the same tags, so a vehicle can still drive both senses, and a consumer acting on the field must see both.

Adjacency SHALL be taken from the carved plaza extract the grouping already reads, so the field costs no further pass over the source.

`onward_nodes` SHALL NOT be empty for any entry. A booth is in the inventory only because it lies on a through road, so a booth no vehicle can leave contradicts the rule that admitted it. The step SHALL stop and name any booth for which the field would be empty.

`onward_nodes` is distinct from `adjacent_nodes` and does not replace it. `adjacent_nodes` names the nodes on **either** side of a two-way booth and says whether the way reaching each is one-way; it is a work list for telling a two-way booth's sides apart. `onward_nodes` names only what lies **ahead**, for every booth.

```yaml
toll_booths:
  13380042:
    latlon: [48.3955158, 1.3849458]
    onward_nodes:
      13380043: [48.3955477, 1.3849881]
  81055576:
    latlon: [49.0371990, 0.4416040]
    type: bidirectional
    adjacent_nodes:
      81055579: false
      1430501272: false
    onward_nodes:
      81055579: [49.0372414, 0.4416515]
      1430501272: [49.0371601, 0.4415602]
aliases:
  13380044:
    parent_id: 13380042
    latlon: [48.3955521, 1.3849902]
    onward_nodes:
      13380045: [48.3955840, 1.3850325]
```

#### Scenario: Every entry carries the field

- **WHEN** the inventory is written
- **THEN** every entry under `toll_booths` and under `aliases` carries `onward_nodes`, a non-empty mapping from node id to position in ascending numeric key order

#### Scenario: An alias carries its own onward nodes

- **WHEN** a group whose lanes lie metres apart is inspected
- **THEN** each alias carries the nodes beyond its own lane, not a copy of the representative's

#### Scenario: A one-way lane leaves by one arc

- **WHEN** a booth lies on a one-way way with a node beyond it
- **THEN** its `onward_nodes` holds that one node and its position, and not the node behind it

#### Scenario: A two-way booth leaves by two arcs

- **WHEN** a booth lies on a way the car profile can traverse in both directions
- **THEN** its `onward_nodes` holds the node on each side, because a vehicle passing the booth in either sense reaches one of them next

#### Scenario: An override does not change the direction

- **WHEN** a booth is stated one-way by override against a two-way tag in the extract
- **THEN** its `onward_nodes` still holds the node on each side, because the routing graph is built from the same tag and drives both senses

#### Scenario: A service road beyond a booth is named

- **WHEN** the only way leading on from a booth node is tagged `highway=service`
- **THEN** that node appears in `onward_nodes`, although the grouping's through-road filter would not have followed it

#### Scenario: A booth with nothing beyond it stops the step

- **WHEN** a retained booth has no node a vehicle can reach from it
- **THEN** the step stops and names that booth, rather than writing an entry with an empty `onward_nodes`

#### Scenario: A neighbour without a position stops the step

- **WHEN** the carved extract gives no position for a node beyond a booth
- **THEN** the step stops and names the pair, rather than writing an arc a consumer cannot route across

#### Scenario: The field comes from the carved extract

- **WHEN** the step runs
- **THEN** it reads no extract it did not already read to group the booths

#### Scenario: Regenerating is stable

- **WHEN** the extraction step runs twice against the same extract
- **THEN** the two inventory files are byte-identical, `onward_nodes` included

### Requirement: A booth the extract does not tag can be stated by hand

A toll plaza is several parallel lanes. Where OSM tags `barrier=toll_booth` on one lane and not on the next, the untagged lane is a way past the barrier that costs nothing, and a router that prices the barrier finds that lane and takes it every time. Nothing in the extract distinguishes such a lane from an ordinary slip road, so the fact has to be stated.

`missing_toll_booth` in the override file SHALL hold a list of OSM node ids. Each SHALL be collected as a toll booth wherever booths are collected, exactly as though the extract carried `barrier=toll_booth` on it. Nothing further SHALL be statable about such a node: what the entry says is what that tag would have said.

A node named there SHALL then take part in classification, grouping, and the inventory on the same terms as any other booth. No rule SHALL treat it as a special case afterwards. At Tonnay-Charente that makes node 13048100170 an alias of group 1116803670, because the two lanes share the predecessor 1404370113 and the successor 7714272796, and the plaza is then charged the same whichever lane a vehicle uses.

A node the extract **already** tags SHALL stop the step, naming it. The entry claims a booth the extract does not carry; naming one it does carry states nothing, and worse, reads as though the untagged lane beside it were covered.

The node's position SHALL be taken from the carved plaza extract rather than from the filtered extract. The filter keeps only nodes that already carry a booth or a place tag, which is precisely the set this entry exists to add to.

A node that no drivable way in the carved plaza extract carries SHALL stop the step, naming it. The entry states a lane of a plaza, so the node has to lie beside a booth the extract does tag; a node found nowhere near one is a booth stated where no vehicle passes.

Nothing SHALL read a way's `toll` tag in place of this. A `toll=yes` way says the road is tolled, not that a fee is collected at a point on it — the mainline motorway carries the same tag for tens of kilometres — so the tag cannot stand in for a booth node.

#### Scenario: A stated booth becomes an ordinary booth

- **WHEN** `missing_toll_booth` names a node on the untagged lane of a plaza
- **THEN** the inventory carries that node with its own `latlon` and `onward_nodes`, and the grouping attaches it to the tagged lane beside it as an alias

#### Scenario: The plaza then costs the same by either lane

- **WHEN** a vehicle is routed past a plaza whose second lane was stated by hand
- **THEN** both lanes cost the barrier's tariff, and neither is cheaper than the other

#### Scenario: A node the extract already tags

- **WHEN** `missing_toll_booth` names a node the extract carries as `barrier=toll_booth`
- **THEN** the step stops and names it, rather than applying an entry that changes nothing

#### Scenario: A node on no drivable way

- **WHEN** `missing_toll_booth` names a node no drivable way in the carved plaza extract carries
- **THEN** the step stops and names it

#### Scenario: The entry states nothing but the node

- **WHEN** the section is read
- **THEN** it is a list of node ids, and a value that is not a node id stops the step

## MODIFIED Requirements

### Requirement: Hand-maintained booth decisions

The extraction step SHALL read `data/osm_toll_booths_overrides.yaml`, a hand-maintained input recording decisions that no rule can derive from the extract. A missing file SHALL be treated as an empty set of overrides.

The file SHALL be a mapping with four permitted top-level keys:

- `toll_booths` holds decisions about individual booths, keyed by OSM node id; an entry SHALL carry at least one of `type`, `parent_id`, `vinci`, `price`, `first_toll_node_id`, or `last_toll_node_id`.
- `duplicate_gares` holds operator numbers of gares that one route may legitimately pay twice.
- `prohibited_gare_pairs` holds ordered pairs of operator numbers that are not a journey anyone can be sold.
- `missing_toll_booth` holds OSM node ids the extract does not tag `barrier=toll_booth` and should.

A top-level key that is none of the four SHALL stop the step. A mistyped section name would otherwise read as an absent section, and every entry beneath it would be dropped without a word.

Operator numbers in `duplicate_gares` SHALL be compared as strings. They carry leading zeros, which YAML reads away when the value is unquoted, so `04210` and `"04210"` SHALL name the same gare.

Blacklisted nodes are not booth overrides and SHALL NOT appear here. They describe the road graph rather than any booth, they are enforced by the routing profile, and `build-pipeline` gives them a file of their own.

Every overridden node SHALL be checked against the extract, and the check runs in both directions. A node under `toll_booths` SHALL be a toll booth in the extract, because an override for a booth that is not there is stale. A node under `missing_toll_booth` SHALL NOT be one, for the mirror reason.

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

- **WHEN** an entry under `toll_booths` carries a key other than the six permitted
- **THEN** the step stops and names the entry and the key

#### Scenario: An unknown top-level section

- **WHEN** the file carries a top-level key other than `toll_booths`, `duplicate_gares`, `prohibited_gare_pairs` or `missing_toll_booth`
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

#### Scenario: An override names a booth the extract does not carry

- **WHEN** an entry under `toll_booths` names a node the extract does not tag as a toll booth
- **THEN** the step stops and names it

#### Scenario: The two checks are mirrors

- **WHEN** the same node is named under `toll_booths` and under `missing_toll_booth`
- **THEN** one of the two checks stops the step whichever way the extract tags it
