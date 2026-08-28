## MODIFIED Requirements

### Requirement: A booth that charges at a point contributes one row per arc leaving it

A **flat-charge booth** is a booth group whose entry in `data/vinci_price.yaml` carries a `price` and that is **not an end of any placed pair**. It charges for passing one point rather than over a distance, so the sampling that prices the ticket network never reaches it. There are 280 of them, tariffed from 0.40 EUR to 55.50 EUR with a median of 2.00 EUR.

The definition SHALL NOT be a test on the entry's `type`. That field names the hardware, not the charge. `gantry` comes from the OSM tag `highway=toll_gantry` and covers three unrelated behaviours: a ticketless entrance that takes no money and leaves the collecting to an exit barrier, a point that opens and closes priced sections on a free-flow motorway, and a point that charges a fixed amount for passing it. `bidirectional` names a lane a vehicle can drive either way, which says nothing about what it charges. Selecting on the type both misses 41 booths that charge at a point and would admit booths that do not.

Carrying a `price` is what says the operator charges for the passage itself: the price file records one only for a passage the operator returned with no exit attached to it.

Ending no placed pair is what says the passage is not already paid for. A booth that is the entrance or the exit of a priced pair has its tariff spread over the segments of that pair's route, and a flat row for it would charge the same passage twice. Two booths are rejected on this ground, both gantries at Montbeugny Est on the A79: one is the target of a pair priced at 1.90 EUR over 3.55 km, and one carries `price` and `prices` together.

A group SHALL NOT be rejected because an arc leaving it already carries a sample. That cannot happen to a group ending no placed pair — a pair whose route crosses a third booth is rejected before it samples anything — and where the two sources do meet the rule is that they add, not that the charge is dropped.

For every flat-charge booth, the step SHALL write one row for each **directed arc whose tail is one of that group's lane nodes**, and each such row SHALL carry the group's whole tariff. A lane node is the group's representative or any node the inventory records as an alias of it.

The arcs SHALL be taken from the inventory's `onward_nodes`, which names the node a vehicle reaches after passing each lane node in each direction it can leave by. The step SHALL NOT read an extract to work them out for itself. Which arc leaves a booth is a fact about the road network, and the inventory is where this pipeline records those.

The tail is what makes this exact. A row is an oriented `from,to` pair, so the two senses of a two-way barrier are two rows that never interfere, and a vehicle can traverse an arc out of the booth only by standing on the booth node — which is what passing the barrier means. Charging the arc that arrives at the booth would instead charge vehicles that turn off before it.

Every lane SHALL be charged, aliases included. A plaza where one lane carries the charge and another does not is worse than a plaza where neither does: the router finds the free lane and takes it every time, and the journey then costs less than it did before the barrier was priced at all.

Because the second clause reads the placed pairs, the flat set SHALL be chosen after the priced pairs have been routed, not before. A run that enumerates without routing SHALL report the groups carrying a `price` rather than a number of arcs it cannot yet know.

Measured over the 280 groups: 333 arcs, no arc's head is itself a booth lane node of that group or any other, so no route can pay two rows for one point. Of those, 239 groups and 289 arcs are the barriers already written; the other 41 groups and 44 arcs are new, over 22 gares, tariffed from 0.70 EUR to 10.80 EUR with a median of 2.50 and a total of 128.20 EUR.

#### Scenario: A barrier is charged

- **WHEN** the VIADUC DE MILLAU barrier, a flat-charge booth at 13.80 EUR, is written
- **THEN** the file carries a row for the arc leaving its lane node, and that row's target weight exceeds the arc's own by `13.80 / 20 * 3600`, that is 2 484

#### Scenario: A journey across a barrier is no longer free

- **WHEN** Clermont-Ferrand to Beziers, which crosses the VIADUC DE MILLAU barrier, is routed on both graphs
- **THEN** the toll-weighted graph either charges 2 484 more weight than the untouched graph or returns a route that does not cross the barrier

#### Scenario: A barrier with no alternative is charged in full

- **WHEN** Le Havre to Honfleur, whose road crosses the PONT DE NORMANDIE barrier at 5.90 EUR, is routed on both graphs
- **THEN** both graphs return the same road, and the toll-weighted weight exceeds the untouched weight by 1 062, that is 17.7 minutes of a driver's work, with the two durations equal

#### Scenario: A free-flow point charge is charged

- **WHEN** MONTESSON, a booth carrying `type: gantry` and `price: 10.80` and ending no placed pair, is written
- **THEN** the file carries a row for the arc leaving each of its lane nodes, each carrying the whole 10.80 EUR

#### Scenario: A two-way booth that charges at a point is charged

- **WHEN** LESTELLE ST MARTORY, carrying `type: bidirectional` and `price: 1.50` and ending no placed pair, is written
- **THEN** the file carries a row for the arc leaving its lane node, carrying the whole 1.50 EUR

#### Scenario: A ticketless entrance gets no flat row

- **WHEN** the booth at Chambéry Nord carrying `type: gantry`, `payment:none=yes` in the extract, `prices` and no `price` is considered
- **THEN** no row is written for the arcs leaving it, because it carries no `price` and takes no money at that point

#### Scenario: A section end gets no flat row

- **WHEN** a booth carries a `price` and is also the target of a placed pair, as the gantry at Montbeugny Est priced at 1.90 EUR over 3.55 km is
- **THEN** no row is written for the arcs leaving it, because its passage is already paid for by that pair

#### Scenario: A gantry with a flat price gets no flat row

- **WHEN** a booth's entry carries `type: gantry` and a `price`, and that booth is also an end of placed pairs — as the gantry carrying `price` and `prices` together at Montbeugny Est is
- **THEN** no row is written for the arcs leaving it, because it would otherwise be charged twice; a gantry carrying a `price` and ending no pair is written instead

#### Scenario: A ticket booth gets no flat row

- **WHEN** a booth's entry carries `type: enter` or `type: exit`
- **THEN** no row is written for the arcs leaving it, because it carries no `price`, and its tolls reach the file only through the pairs it belongs to

#### Scenario: Each direction of a two-way barrier is its own row

- **WHEN** a flat-charge booth's lane node has an arc out in each direction
- **THEN** the file carries a row for each of the two arcs, and a journey through the booth in either direction pays the tariff once

#### Scenario: Every lane of a plaza is charged

- **WHEN** a flat-charge group is carried by six lane nodes, as ENTREE TUNNEL DU FREJUS is
- **THEN** the file carries a row for the arc leaving each of the six, and no lane of that plaza is cheaper than another

#### Scenario: A barrier is only as dear as the way past it

- **WHEN** a plaza's other lanes carry no `barrier=toll_booth` node, so the inventory holds one lane of it, as at ILE DE RE
- **THEN** the toll-weighted graph routes through the untagged lanes and pays a fraction of the tariff, and no rule in this step corrects that — what is missing is a booth in the extract, not a row in the file

#### Scenario: The flat set is chosen after the routing

- **WHEN** the step is run without routing, to enumerate its work
- **THEN** it names the groups carrying a `price` and does not claim a number of arcs to charge, since which of them end a placed pair is not yet known

### Requirement: The arc of a flat-charge booth is measured on the graph, and an unmeasured one stops the run

The length, duration and weight of an arc leaving a flat-charge booth SHALL be taken from the router's own annotation for that arc, as they already are for a sampled segment. They are the numbers the graph was built with, and a length taken from the extract or a speed taken from the road's class would restate the arc's duration to no purpose.

A measured arc SHALL be checked against the straight-line distance between its own two nodes, so that a route returning some other stretch of road is not taken for the arc and given the whole tariff. The allowed disagreement SHALL be **the larger of one metre and one per cent of that straight line**.

The bound SHALL NOT be one metre alone. A road bends between its nodes, so the routed length exceeds the chord by a share of the length rather than by a fixed amount, and an absolute metre is a bound only a short arc can meet. A barrier sits in a plaza where the next node is close — 18.4 m at the median — while a free-flow point sits on open motorway where it can be half a kilometre away. Measured over the 44 new arcs, the disagreement is 0.07 m at the median and 1.53 m at the worst, which is 0.4874% of its own arc; the flat metre rejects two arcs of about 500 m that every radius and every standoff measures identically, and the proportional bound rejects none.

The step SHALL stop when any arc of a flat-charge group cannot be measured, naming the group, its tariff and the arc. It SHALL NOT write a file in which some lanes of a plaza carry the charge and others do not, and it SHALL NOT silently drop a barrier.

The step SHALL likewise stop when a flat-charge booth's entry in the inventory carries no `onward_nodes`, naming the booth. An inventory too old to hold the field prices every barrier at nothing, and nothing downstream can tell that from a file that simply has no barriers in it.

Measured, a route between the arc's two node coordinates with the snapping radius held to a few metres returns all 44 of the new arcs and 287 of the 289 already written. A route that drives past the arc from a standoff either side returns 257 of the 289 and covers the ones the first misses; over the 256 both return, they differ by 0.000 m, 0.000 s and 0.000 weight.

#### Scenario: An arc is measured

- **WHEN** an arc leaving a flat-charge booth is measured
- **THEN** its length, duration and weight are those the untouched graph reports for that arc, and the routed length agrees with the distance between its two nodes within the larger of one metre and one per cent

#### Scenario: A long arc on a bend is accepted

- **WHEN** an arc whose two nodes are 500.1 m apart routes 501.7 m, a disagreement of 1.5 m and 0.305%
- **THEN** it is accepted, because the bound at that length is 5.0 m rather than 1 m

#### Scenario: A short arc is still held to a metre

- **WHEN** an arc whose two nodes are 20 m apart routes 21.5 m
- **THEN** it is rejected, because one per cent of 20 m is below the one-metre floor

#### Scenario: An unmeasurable arc stops the run

- **WHEN** one arc of a flat-charge group cannot be measured on the untouched graph
- **THEN** the step stops, names the group, its tariff and the arc, and `data/segment_weights.csv` is not written or replaced

#### Scenario: An inventory without the field stops the run

- **WHEN** a flat-charge booth's entry carries no `onward_nodes`
- **THEN** the step stops and names that booth, rather than writing a file in which its barrier is free

#### Scenario: Every group is accounted for

- **WHEN** the step completes
- **THEN** every flat-charge group has a row for every node its lane nodes' `onward_nodes` name

### Requirement: A flat charge and a per-kilometre rate add on the same segment

Where a directed segment both leaves a flat-charge booth and carries samples from priced pairs, its target weight SHALL include both terms. A row SHALL NOT replace one with the other, and the flat charge SHALL NOT be dropped on the ground that the segment is already sampled.

Measured against the file as it stands, no such segment exists: none of the 333 arcs carries a sample, and no lane node of a flat-charge booth appears in any of the 249 454 sampled rows. That is a consequence of how a pair is judged rather than a coincidence — a pair whose route crosses a third booth is rejected, so an arc leaving a booth is sampled only when that booth is itself a pair end, and such a booth is not a flat-charge booth. The rule is stated because a future judging rule or a future price file can make the two meet.

The step SHALL report how many segments carry both.

#### Scenario: The two sources are disjoint today

- **WHEN** the step runs against the current price file and inventory
- **THEN** it reports no segment carrying both a sample and a flat charge, and writes 249 787 rows: 249 454 sampled, 333 flat, none replaced

#### Scenario: A segment carrying both

- **WHEN** a segment leaves a flat-charge booth of 2.00 EUR and also carries samples worth 0.30 EUR over its own length
- **THEN** its target weight adds `2.30 / wage * 3600` to its original weight, and the step counts it among the segments carrying both

### Requirement: The two graphs differ by the cost of the toll and nothing else

For any route between two booths of a priced pair, the toll-weighted graph's route weight SHALL exceed the untouched graph's by approximately the driver's time to pay that pair's tariff, and the two durations SHALL agree.

The check SHALL be part of the step, run against a pair fixed in the pipeline rather than chosen at run time, so that a graph built wrongly is caught where it is built.

The fixed pair SHALL be LE PERTHUS, OSM node 36967365, to BEZIERS-OUEST, OSM node 1676618837, priced at 14.50 EUR. At 20 EUR per hour that is 43.5 minutes of work.

The tolerance on that difference SHALL be 20% by default and SHALL be settable. It is not a bound on the graph's arithmetic, which is exact; it is a bound on how far the per-segment rates reconstruct this one tariff. Measured, the pair comes back at 36.2 minutes — the rates price this journey at 12.07 EUR against the operator's 14.50, an error of -16.7% that sits inside the measured p90 for all pairs.

The durations SHALL be equal. Measured, they are: 3688.7 s on both graphs.

The check SHALL also cover **every arc of every flat-charge booth**. Each arc SHALL be routed on both graphs and its weight difference SHALL equal that booth's tariff converted at the wage, within 1% or one weight unit, whichever is larger. The floor is there because the cheapest barrier is 0.40 EUR, which is 72 weight units, and a proportional bound alone would turn the check on the last decimal place of the smallest tariff.

The arcs and their tariffs SHALL be read from the report the run wrote, not derived again. The check routes no priced pair, so it cannot tell which groups ended one, and a check that selected its subjects by a different rule from the one that wrote the file would not be checking that file. Where the report is absent or names an arc the file does not carry, the check SHALL stop and say so.

The arc SHALL be routed between its own two node positions with the snapping radius held tight, so that the router has nowhere to go but along the arc. Routing a journey across the barrier instead would not do: the toll-weighted graph is free to answer with a route that avoids the barrier, and then the check measures a different road.

That part of the check is tight where the pair check is loose, and deliberately so. A flat charge is not reconstructed from rates; it is written whole onto one arc, so the arithmetic is exact and any disagreement is a fault in the file or in the graph rather than in the pricing. It is also the only check that catches the three ways a flat row can fail silently: a rate the customization clamps, a rate the written precision rounds away, and a row whose segment `osrm-customize` never matched. All three leave the barrier free, and a route across it looks entirely normal.

#### Scenario: The weight difference is the toll

- **WHEN** the fixed pair is routed on both graphs after the file is applied
- **THEN** the toll-weighted weight exceeds the untouched weight by 43.5 minutes within the 20% tolerance — measured at +2173.4 s, that is 36.2 minutes

#### Scenario: The duration difference is nil

- **WHEN** the fixed pair is routed on both graphs
- **THEN** the two durations are equal — measured at 3688.7 s on both

#### Scenario: An unpriced route is unchanged

- **WHEN** a route that touches no tolled segment is requested from both graphs
- **THEN** its weight and its duration are identical on both — measured over a 68.0 km route in Brittany, weight 3198.7 and duration 3176.5 on each

#### Scenario: A tolled route is avoided when the toll costs more than the time

- **WHEN** a route whose fastest path uses a tolled motorway is requested from both graphs, and the toll exceeds the driver's time saved
- **THEN** the untouched graph returns the tolled path and the toll-weighted graph returns a free alternative — measured Narbonne to Montpellier, 94.2 km in 71.2 min against 116.3 km in 82.7 min

#### Scenario: Every barrier arc is checked

- **WHEN** the acceptance check runs
- **THEN** each of the 333 arcs the report names is routed on both graphs, and each weight difference equals that booth's tariff at the wage

#### Scenario: A free-flow point charge is no longer free

- **WHEN** an arc leaving MONTESSON, a point charge of 10.80 EUR, is routed on both graphs
- **THEN** the toll-weighted weight exceeds the untouched weight by 1 944, that is 32.4 minutes of a driver's work, with the two durations equal

#### Scenario: A barrier arc the customization did not match

- **WHEN** one flat row names a segment `osrm-customize` did not apply, so its arc weighs the same on both graphs
- **THEN** the check stops and names that booth, its tariff and its arc

#### Scenario: The report is missing

- **WHEN** the acceptance check runs and the report naming the flat arcs is absent
- **THEN** it stops and names the file, rather than checking a set of arcs it derived by a different rule

#### Scenario: The check fails

- **WHEN** the weight difference is outside tolerance
- **THEN** the step stops and reports both weights, both durations and the expected difference
