## ADDED Requirements

### Requirement: A booth that charges at a point contributes one row per arc leaving it

A **flat-charge booth** is a booth group whose entry in `data/vinci_price.yaml` carries `type: passthrough` and a single `price`. It sells no ticket, so it appears in no priced pair, and the sampling that prices the ticket network never reaches it. There are 239 of them, tariffed from 0.40 EUR to 55.50 EUR with a median of 2.00 EUR.

For every flat-charge booth, the step SHALL write one row for each **directed arc whose tail is one of that group's lane nodes**, and each such row SHALL carry the group's whole tariff. A lane node is the group's representative or any node the inventory records as an alias of it.

The arcs SHALL be taken from the inventory's `onward_nodes`, which names the node a vehicle reaches after passing each lane node in each direction it can leave by. The step SHALL NOT read an extract to work them out for itself. Which arc leaves a booth is a fact about the road network, and the inventory is where this pipeline records those.

The tail is what makes this exact. A row is an oriented `from,to` pair, so the two senses of a two-way barrier are two rows that never interfere, and a vehicle can traverse an arc out of the booth only by standing on the booth node — which is what passing the barrier means. Charging the arc that arrives at the booth would instead charge vehicles that turn off before it.

Every lane SHALL be charged, aliases included. A plaza where one lane carries the charge and another does not is worse than a plaza where neither does: the router finds the free lane and takes it every time, and the journey then costs less than it did before the barrier was priced at all.

Measured over the 239 groups: 286 lane nodes, 288 arcs, 284 lane nodes with one arc out and 2 with two. No arc's head is itself a booth lane node, of that group or any other, so no route can pay two rows for one barrier.

Booths that charge over a distance SHALL NOT be given a flat row. A `gantry` and a `bidirectional` booth may carry a `price` as well — 41 and 2 of them do — but both are also ends of priced pairs, and one gantry carries `price` and `prices` together. A flat row for those would charge the same passage twice.

#### Scenario: A barrier is charged

- **WHEN** the VIADUC DE MILLAU barrier, a flat-charge booth at 13.80 EUR, is written
- **THEN** the file carries a row for the arc leaving its lane node, and that row's target weight exceeds the arc's own by `13.80 / 20 * 3600`, that is 2 484

#### Scenario: A journey across a barrier is no longer free

- **WHEN** Clermont-Ferrand to Beziers, which crosses the VIADUC DE MILLAU barrier, is routed on both graphs
- **THEN** the toll-weighted graph either charges 2 484 more weight than the untouched graph or returns a route that does not cross the barrier — measured before this change, the difference is +0.0 on both counts

#### Scenario: A barrier with no alternative is charged in full

- **WHEN** Le Havre to Honfleur, whose road crosses the PONT DE NORMANDIE barrier at 5.90 EUR, is routed on both graphs
- **THEN** both graphs return the same road, and the toll-weighted weight exceeds the untouched weight by 1 062, that is 17.7 minutes of a driver's work, with the two durations equal

#### Scenario: A barrier is only as dear as the way past it

- **WHEN** a plaza's other lanes carry no `barrier=toll_booth` node, so the inventory holds one lane of it, as at ILE DE RE
- **THEN** the toll-weighted graph routes through the untagged lanes and pays a fraction of the tariff, and no rule in this step corrects that — what is missing is a booth in the extract, not a row in the file

#### Scenario: Each direction of a two-way barrier is its own row

- **WHEN** a flat-charge booth's lane node has an arc out in each direction
- **THEN** the file carries a row for each of the two arcs, and a journey through the booth in either direction pays the tariff once

#### Scenario: Every lane of a plaza is charged

- **WHEN** a flat-charge group is carried by six lane nodes, as ENTREE TUNNEL DU FREJUS is
- **THEN** the file carries a row for the arc leaving each of the six, and no lane of that plaza is cheaper than another

#### Scenario: A ticket booth gets no flat row

- **WHEN** a booth's entry carries `type: enter` or `type: exit`
- **THEN** no row is written for the arcs leaving it on that account, and its tolls reach the file only through the pairs it belongs to

#### Scenario: A gantry with a flat price gets no flat row

- **WHEN** a booth's entry carries `type: gantry` and a `price`
- **THEN** no row is written for the arcs leaving it, because that booth is also an end of priced pairs and would otherwise be charged twice

### Requirement: The arc of a flat-charge booth is measured on the graph, and an unmeasured one stops the run

The length, duration and weight of an arc leaving a flat-charge booth SHALL be taken from the router's own annotation for that arc, as they already are for a sampled segment. They are the numbers the graph was built with, and a length taken from the extract or a speed taken from the road's class would restate the arc's duration to no purpose.

The step SHALL stop when any arc of a flat-charge group cannot be measured, naming the group, its tariff and the arc. It SHALL NOT write a file in which some lanes of a plaza carry the charge and others do not, and it SHALL NOT silently drop a barrier.

The step SHALL likewise stop when a flat-charge booth's entry in the inventory carries no `onward_nodes`, naming the booth. An inventory too old to hold the field prices every barrier at nothing, and nothing downstream can tell that from a file that simply has no barriers in it.

Measured over the 288 arcs, two independent measurements agree exactly. A route between the arc's two node coordinates, with the snapping radius held to a few metres, returns 287 of them; a route that drives past the arc from a standoff either side returns 257 and covers the one the first misses. Over the 256 arcs both return, they differ by 0.000 m, 0.000 s and 0.000 weight.

#### Scenario: An arc is measured

- **WHEN** an arc leaving a flat-charge booth is measured
- **THEN** its length, duration and weight are those the untouched graph reports for that arc, and the routed length agrees with the distance between its two nodes to within a metre

#### Scenario: An unmeasurable arc stops the run

- **WHEN** one arc of a flat-charge group cannot be measured on the untouched graph
- **THEN** the step stops, names the group, its tariff and the arc, and `data/segment_weights.csv` is not written or replaced

#### Scenario: An inventory without the field stops the run

- **WHEN** a flat-charge booth's entry carries no `onward_nodes`
- **THEN** the step stops and names that booth, rather than writing a file in which its barrier is free

#### Scenario: Every group is accounted for

- **WHEN** the step completes
- **THEN** every flat-charge group in the price file has a row for every node its lane nodes' `onward_nodes` name

### Requirement: A flat charge and a per-kilometre rate add on the same segment

Where a directed segment both leaves a flat-charge booth and carries samples from priced pairs, its target weight SHALL include both terms. A row SHALL NOT replace one with the other.

Measured against the file as it stands, no such segment exists: none of the 288 arcs carries a row today, and no lane node of a flat-charge booth appears in any of the 249 454 rows. The rule is stated because the two sources are independent, and a future inventory or a future price file can make them meet.

The step SHALL report how many segments carry both.

#### Scenario: The two sources are disjoint today

- **WHEN** the step runs against the current price file and inventory
- **THEN** it reports no segment carrying both a sample and a flat charge, and writes 249 742 rows: 249 454 sampled, 288 flat, none replaced

#### Scenario: A segment carrying both

- **WHEN** a segment leaves a flat-charge booth of 2.00 EUR and also carries samples worth 0.30 EUR over its own length
- **THEN** its target weight adds `2.30 / wage * 3600` to its original weight, and the step counts it among the segments carrying both

### Requirement: The report names every flat charge

The report SHALL carry a section for the flat-charge booths, naming for each group its gare code and the operator's name, its tariff, every arc written for it, each arc's length, class and own weight, and the rate the row asks for.

It SHALL also report the totals: how many groups and arcs were written, and the range of the rates asked for.

A flat row is the whole tariff on one short arc, so it is the row most worth reading back. The rates it asks for are three orders of magnitude below anything the fitted rows ask for, and nothing else in the report would show that.

#### Scenario: Each barrier can be read back

- **WHEN** the report is written
- **THEN** it names each flat-charge group with its gare code, its tariff, its arcs and their rates

#### Scenario: The range of the rates is stated

- **WHEN** the report is written
- **THEN** it states the lowest and highest rate written for a flat charge alongside the lowest and highest written for a sampled segment

## MODIFIED Requirements

### Requirement: The segment speed file preserves duration and moves only weight

For every directed segment carrying at least one sample, and for every directed arc leaving a flat-charge booth, the step SHALL write one row of `from_osm_id,to_osm_id,edge_speed_in_km_h,edge_rate` to `data/segment_weights.csv`.

The **speed** SHALL be the segment's original speed on the untouched graph, so that applying the file leaves the segment's duration as it was.

The **rate** SHALL be `length_in_metres / target_weight`, where

    target_weight = original_weight + toll_eur / wage_eur_per_hour * 3600
    toll_eur      = segment_price_eur + flat_charge_eur
    segment_price_eur = price_per_kilometre * length_in_metres / 1000
    flat_charge_eur   = the tariff of the flat-charge booth this arc leaves, or zero

`wage_eur_per_hour` SHALL default to 20 and SHALL be settable. The added term is the time a driver earning that wage works to pay what the segment costs: a 100 m segment at 2 EUR/km costs 0.20 EUR and adds 36 seconds, and an arc leaving a 55.50 EUR barrier adds 9 990 seconds however short it is.

The original speed, weight and length SHALL be taken from the router's own annotations, not from a separate reading of the extract. For a sampled segment they come from the priced routes that drove it; for an arc leaving a flat-charge booth they come from a route across that arc. They are the numbers the graph was built with, so anything derived elsewhere could disagree with it.

Where a segment's annotations disagree between the routes that drove it, the observation giving the shortest duration and the lowest weight SHALL be taken. The router folds a turn penalty into the segment before the turn, and a penalty only ever adds, so the smallest observation is the one free of it.

The rate SHALL be written with enough precision that the weight `osrm-customize` derives from it is within 0.01% of the target weight. Six decimal places is not enough: the smallest rate the file now carries is 0.000642661, a 55.50 EUR barrier on a 6.4 m arc, where six places cost 0.0778% and nine cost 0.0000778%. The fitted rows never ask for less than 1.09, so six places were never tested below that.

No row SHALL be written for a segment that no priced route drove and that leaves no flat-charge booth. Such a segment is not known to be tolled, and a row would restate its speed to no purpose while risking a changed duration.

#### Scenario: A row is derived

- **WHEN** a segment is 100 m long, takes 2.77 s, has weight 2.77, and its rate is 2.00 EUR/km
- **THEN** its row carries a speed of 129.963899 km/h and a rate of `100 / (2.77 + 36)`, that is 2.579314

#### Scenario: A row for a barrier arc is derived

- **WHEN** the arc leaving a 55.50 EUR barrier is 13.7 m long, takes 2.3 s and has weight 2.3
- **THEN** its row carries a speed of 21.443478 km/h and a rate of `13.7 / (2.3 + 9990)`, that is 0.001371374

#### Scenario: Duration survives the update

- **WHEN** the file is applied to a copy of the untouched graph and a priced route is requested from both graphs
- **THEN** the two durations are equal — measured at 0.000 s difference over a 105.5 km route of 1 047 segments

#### Scenario: A turn penalty is discarded

- **WHEN** one route observes a segment at 2.77 s and another, turning immediately after it, at 5.77 s
- **THEN** 2.77 s is used

#### Scenario: An untouched segment

- **WHEN** a directed segment is driven by no priced pair and leaves no flat-charge booth
- **THEN** it has no row in the file, and its speed and weight on both graphs are identical

#### Scenario: The wage is settable

- **WHEN** the step is run at 40 EUR/hour
- **THEN** every segment's added weight is half what it is at 20 EUR/hour, flat charges included

### Requirement: The two graphs differ by the cost of the toll and nothing else

For any route between two booths of a priced pair, the toll-weighted graph's route weight SHALL exceed the untouched graph's by approximately the driver's time to pay that pair's tariff, and the two durations SHALL agree.

The check SHALL be part of the step, run against a pair fixed in the pipeline rather than chosen at run time, so that a graph built wrongly is caught where it is built.

The fixed pair SHALL be LE PERTHUS, OSM node 36967365, to BEZIERS-OUEST, OSM node 1676618837, priced at 14.50 EUR. At 20 EUR per hour that is 43.5 minutes of work.

The tolerance on that difference SHALL be 20% by default and SHALL be settable. It is not a bound on the graph's arithmetic, which is exact; it is a bound on how far the per-segment means reconstruct this one tariff. Measured, the pair comes back at 36.2 minutes — the means price this journey at 12.07 EUR against the operator's 14.50, an error of -16.7% that sits inside the measured p90 of 24.4% for all pairs.

The durations SHALL be equal. Measured, they are: 3688.7 s on both graphs.

The check SHALL also cover **every arc of every flat-charge booth**. Each arc SHALL be routed on both graphs and its weight difference SHALL equal that booth's tariff converted at the wage, within 1% or one weight unit, whichever is larger. The floor is there because the cheapest barrier is 0.40 EUR, which is 72 weight units, and a proportional bound alone would turn the check on the last decimal place of the smallest tariff.

The arc SHALL be routed between its own two node positions with the snapping radius held tight, so that the router has nowhere to go but along the arc. Routing a journey across the barrier instead would not do: the toll-weighted graph is free to answer with a route that avoids the barrier, and then the check measures a different road.

That part of the check is tight where the pair check is loose, and deliberately so. A flat charge is not reconstructed from means; it is written whole onto one arc, so the arithmetic is exact and any disagreement is a fault in the file or in the graph rather than in the pricing. It is also the only check that catches the three ways a flat row can fail silently: a rate the customization clamps, a rate the six-decimal grid rounds away, and a row whose segment `osrm-customize` never matched. All three leave the barrier free, and a route across it looks entirely normal.

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
- **THEN** each of the arcs written for a flat-charge booth is routed on both graphs, and each weight difference equals that booth's tariff at the wage — measured over 288 arcs, the worst disagreement is 0.00 weight units

#### Scenario: A barrier arc the customization did not match

- **WHEN** one flat row names a segment `osrm-customize` did not apply, so its arc weighs the same on both graphs
- **THEN** the check stops and names that booth, its tariff and its arc

#### Scenario: The check fails

- **WHEN** the weight difference is outside tolerance
- **THEN** the step stops and reports both weights, both durations and the expected difference
