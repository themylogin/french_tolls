# toll-weighted-graph Specification

## Purpose
Turns the entrance/exit tariffs in `data/vinci_price.yaml` into a per-segment price and an OSRM segment speed file, so that a second routing graph costs the toll network what it actually costs a driver instead of treating it as free.

## Requirements

### Requirement: A priced pair contributes one sample per segment it drives

A **priced pair** is an ordered pair of booth groups where the source group carries a price in `data/vinci_price.yaml` under a gare code, and the target group is the group carrying that gare code.

Every priced pair SHALL be routed on the untouched graph, from the entrance's `first_toll_latlon` to the exit's `last_toll_latlon`. Where an end carries no extent, that end's booth coordinates SHALL be used instead, and the step SHALL count how often that happened.

The pair's **price per kilometre** SHALL be its tariff divided by the length of that route in kilometres. That one value SHALL be recorded as a sample against every directed segment the route drives, where a directed segment is an ordered pair of consecutive OSM node ids from the route's node annotation.

Measuring between the extents rather than between the barriers is what makes the rate a rate. MERU to AMBLAINVILLE is 1.5 km barrier to barrier and 10.0 km between the ends of its tolled road, so the same 1.90 EUR reads 1.2422 EUR/km one way and 0.1891 the other.

The route's first and last segments SHALL be excluded. The router snaps each endpoint onto a lane, so those two segments are partial: their length and duration are a fraction of the segment's own, and taking them as whole would misstate both the sample and the segment's speed.

A gare code carried by more than one group SHALL be resolved to the group whose route from the source crosses no third booth. Where more than one qualifies, the shortest route SHALL be taken.

Whether a route crosses a booth group SHALL be decided by resolving each traversed node through the inventory's aliases, never by looking for the group's own node id. A plaza has one lane per booth and the inventory records the others as aliases of it, so a route crosses the group by whichever lane the router picked. Asking for the representative's id finds nothing when the router used a neighbouring lane, and the pair is then discarded as though its own booths were not on its route.

#### Scenario: A tariff becomes a rate

- **WHEN** a pair priced at 14.50 EUR routes 105.5 km
- **THEN** every directed segment of that route except the first and the last records a sample of 0.1375 EUR/km

#### Scenario: The denominator is the tolled distance

- **WHEN** the pair MERU to AMBLAINVILLE, priced at 1.90 EUR, is measured
- **THEN** its route runs from MERU's `first_toll_latlon` to AMBLAINVILLE's `last_toll_latlon`, about 10.0 km, and its rate is about 0.19 EUR/km

#### Scenario: An unmeasured end falls back to the booth

- **WHEN** a pair's exit booth carries no extent
- **THEN** the exit booth's own coordinates are used as that end, and the step counts the fallback

#### Scenario: Both directions are separate segments

- **WHEN** one carriageway of a motorway is driven by pairs in one direction only
- **THEN** samples are recorded against the directed segments of that carriageway alone, and the opposing carriageway's segments carry no sample from those pairs

#### Scenario: A partial end segment is dropped

- **WHEN** a route's node annotation carries N nodes
- **THEN** samples are recorded against N-3 directed segments, and neither the segment containing the origin snap nor the one containing the destination snap is among them

#### Scenario: A gare code carried by two groups

- **WHEN** a source's price names a gare code held by two booth groups
- **THEN** the group reached without crossing a third booth is used, and where both qualify the shorter route is used

#### Scenario: A route that crosses a third booth

- **WHEN** the only route from a source to a target crosses a third booth group
- **THEN** the step stops and names the source, the target and the booth in the way, rather than recording samples the tariff does not describe

#### Scenario: A route crosses a booth by another of its lanes

- **WHEN** a pair's route traverses a node the inventory records as an alias of the pair's own source group, and not that group's own node id
- **THEN** the route is treated as crossing that group, and the pair is used

### Requirement: A pair that is not a journey contributes no sample

Some ordered pairs the operator prices are not journeys anyone drives, and a tariff divided by a distance nobody drove is not a price per kilometre. Such a pair SHALL be excluded from the sample table and reported as an unusable pair, naming the reason.

A pair SHALL be excluded when its **barrier-to-barrier route is more than a configured multiple of the straight-line distance between the two barriers**, defaulting to five. Two ramps of one interchange under two gare codes are the case this catches: the router loops out and back, crossing no third booth, so nothing else rejects them. Measured over 23 376 pairs the ratio is 1.26 at the median and 2.09 at the 99th percentile, and then nothing until 5.6, 29.7, 48.3 and 69.1 — four pairs, all of that shape.

The ratio SHALL be measured barrier to barrier and SHALL NOT be measured between whatever endpoints the route was requested from. A pair routed between the ends of its tolled road covers ground outside the two barriers, and testing that ratio would discard the pairs whose measurement is most improved by it — MERU to AMBLAINVILLE is 1.0 barrier to barrier and 6.8 between the extents.

A pair SHALL be excluded when its **tariff is zero**. The operator records a small number of pairs at 0.00 EUR, and each would put a sample of 0 EUR/km on every segment of a real motorway journey. Measured, one such pair set the low end of a segment 1 504 journeys use. What a free section means is a question for the price file, not for this step's arithmetic.

A pair SHALL be excluded when its route does not cross both of its own booth groups, after alias resolution. Such a route is not the journey the tariff is for.

#### Scenario: An interchange loop is excluded

- **WHEN** a pair's two barriers are 0.70 km apart and its route between them is 20.8 km, a ratio of 29.7
- **THEN** the pair contributes no sample and is reported as an unusable pair naming the ratio

#### Scenario: A long way round is kept

- **WHEN** a pair's barriers are 32.7 km apart and its route is 101.6 km, a ratio of 3.1
- **THEN** the pair is used, because the network genuinely goes around

#### Scenario: The ratio is not measured between the extents

- **WHEN** a pair is 1.0 times the straight line barrier to barrier and 6.8 times it between the ends of its tolled road
- **THEN** it is judged on the first figure and kept

#### Scenario: A zero tariff is excluded

- **WHEN** a priced pair carries a tariff of 0.00 EUR
- **THEN** it contributes no sample, and no segment records 0 EUR/km on its account

#### Scenario: A route that misses its own booth

- **WHEN** a pair's route does not cross its source group by any of that group's lanes
- **THEN** the pair contributes no sample and is reported as an unusable pair

### Requirement: A segment's rate is fitted to the tariffs and held to its samples

A directed segment's **price per kilometre** SHALL be fitted so that the rates reproduce the tariffs, and SHALL be held toward the mean of that segment's own samples in proportion to how few journeys constrain it.

The mean alone is the wrong answer whenever the journeys through a segment pay different rates for the same distance. Each journey votes one number — its tariff over its own length — onto all of its segments equally, so a segment shared by a dear section and a cheap one lands between, and summing the means back misses both. Measured, ROUMOIS to ALENCON NORD is 34.80 EUR and reconstructs at 22.82, an error of 34% and 36 minutes of a driver's time.

The fit SHALL treat each journey as one equation, `sum over its segments of rate * length = tariff`, and SHALL minimise the error in those equations — which is the journey error itself, rather than a per-segment agreement that journeys need not follow.

The fit alone is also wrong, because 23 352 equations do not pin 249 454 unknowns. A segment four journeys cross can take any value that balances the books elsewhere, and unconstrained it does: rates reach 7.94 EUR/km, 35 times the mean, on a slip road at VAL DE LOING — half a kilometre carrying 4.24 EUR of toll instead of 0.12, a 12-minute penalty for any journey nobody priced.

So each segment SHALL be a weighted average of what its journeys ask for and what its own samples said, the first weighted by the number of journeys and the second by a configured constant. The constant says how many journeys it takes before a segment is trusted over its own mean; it SHALL default to 5 and SHALL be settable, as SHALL the number of iterations.

No fitted rate SHALL fall outside the range of the segment means. At the default that holds: the highest fitted rate is 0.5386 EUR/km against the means' own highest of 0.5355, so no segment is priced outside what some real journey paid.

The step SHALL report every segment's sample count, lowest, highest and mean sample, and its **spread**, `(highest - lowest) / mean`, ordered widest first, each row naming the segment, the way carrying it and the pairs that produced its extremes.

That spread is a diagnostic about the tariffs, not about the file. It is how four separate measurement errors were found. It SHALL NOT gate the run: measured, 97.9% of segments spread more than 10% after every correction, because two journeys on different concessions genuinely pay different rates for the same distance. A limit on it would stop every run for a fact about French tolls that no pipeline can fix, and the fit is what stops that fact reaching the driver.

The step SHALL report how many segments rest on a single sample, since those carry no evidence either way.

#### Scenario: The fit reduces the journey error

- **WHEN** the rates are fitted at the default settings
- **THEN** the median journey error falls from 8.5% to 3.5% and the 90th percentile from 23.2% to 13.1%, and the share of journeys priced within 10% rises from 56.7% to 84.4%

#### Scenario: A dear section is no longer undercharged

- **WHEN** ROUMOIS to ALENCON NORD, priced at 34.80 EUR, is reconstructed
- **THEN** it reads 31.14 EUR rather than the 22.82 the means give, an error of -10% rather than -34%

#### Scenario: A weakly constrained segment keeps its mean

- **WHEN** a segment is crossed by 4 journeys and the fit would move it far from its mean
- **THEN** it is held near its mean, and no fitted rate exceeds the highest segment mean

#### Scenario: The regularisation is what bounds the rates

- **WHEN** the rates are fitted with the constant set to zero
- **THEN** 587 segments exceed 1 EUR/km and 1 909 fall to nothing, against none of either at the default

#### Scenario: A wide spread does not stop the run

- **WHEN** 97.9% of segments have samples spreading more than 10% about their mean
- **THEN** the step reports the widest, writes the file, and exits successfully

#### Scenario: A single-sample segment

- **WHEN** a segment is driven by exactly one priced pair
- **THEN** its spread is reported as zero and it is counted in the single-sample total

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

### Requirement: The run reports what it costs a driver

Generating the file SHALL end by reporting the **journey error**: for every priced pair, the tariff the operator charges against the amount the rates charge, being the sum of `rate * length` over the segments of its route.

This is the measure that matters, because it is what a driver feels. The per-segment spread says how far two tariffs disagree about a stretch of road; the journey error says what that disagreement costs on a whole journey, and the two move independently.

The report SHALL carry the totals and the net bias, the relative and absolute error distributions, the share of journeys priced within given bands, and a breakdown by journey length.

The report SHALL then name the **worst journeys in euros** and the **worst journeys in proportion**, as two separate lists. They disagree, and both matter: the largest errors in euros are long journeys on dear sections, which can send a driver down the wrong motorway; the largest in proportion are short cheap hops, where being twice the price is worth a minute and changes nothing. A report giving only one of the two misreads the data.

Every named journey SHALL carry a link to itself on the map, both gare codes and names, the tariff, the charged amount, both errors, the route length, and the driver's time the error is worth. A number without a road is not something anyone can check.

The step SHALL also offer a survey mode that does everything except write the file.

#### Scenario: The report ends the run

- **WHEN** the segment speed file is generated
- **THEN** the journey error report is printed after the file is written, and the step exits successfully

#### Scenario: Both worst lists are given

- **WHEN** the report is printed
- **THEN** it names the worst journeys by absolute error and the worst by relative error separately, and the two lists do not coincide

#### Scenario: Each named journey can be opened

- **WHEN** a journey is named among the worst
- **THEN** its row carries a routing link for it on openstreetmap.org

#### Scenario: The error falls with distance

- **WHEN** the breakdown by journey length is printed
- **THEN** it shows the relative error falling as journeys lengthen, and the absolute error rising

#### Scenario: A pair that reached no segment

- **WHEN** a priced pair's route crosses a third booth
- **THEN** it is reported as an unusable pair naming that booth, and it contributes to neither the rates nor the journey error

#### Scenario: Survey mode writes nothing

- **WHEN** the step is run in survey mode
- **THEN** it routes every pair and prints every report, and no segment speed file is written

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

### Requirement: The reconstruction error is reported

The step SHALL reconstruct each priced pair's tariff by summing `price_per_kilometre * length` over the segments of its route, and SHALL report the distribution of the relative error against the tariff the operator gave.

This is the measure of how well a per-segment rate can describe a tariff at all. A per-segment deviation says how much the samples for one segment disagree; the reconstruction error says what that disagreement costs on a whole journey, which is the quantity the router will act on.

The report SHALL name the worst pairs by absolute error, with both gare codes, the tariff, the reconstructed amount and the route length.

#### Scenario: The distribution is reported

- **WHEN** the step completes
- **THEN** it prints the median, the 90th percentile and the maximum relative reconstruction error over all priced pairs

#### Scenario: The worst pairs are named

- **WHEN** the step completes
- **THEN** it prints the pairs with the largest absolute error, each with both gare codes, the operator's tariff, the reconstructed amount and the route length

### Requirement: The toll-weighted graph is a customized copy of the untouched one

The toll-weighted graph SHALL be produced by copying every file of the untouched graph over it and then running `osrm-customize` on the copy with `data/segment_weights.csv` as the segment speed file. It SHALL NOT be produced by a separate extract or partition.

Copying first is what makes the two graphs comparable. `osrm-customize` rewrites weights and durations in place, so a graph customized twice carries the first customization's numbers under the second; only a fresh copy of the untouched graph gives a result that differs from it in exactly the rows of the file.

The step SHALL overwrite whatever the toll-weighted graph directory already holds.

#### Scenario: The copy is made first

- **WHEN** the step runs against a toll-weighted directory holding a previous graph
- **THEN** every file of the untouched graph replaces what is there before `osrm-customize` runs

#### Scenario: No re-extraction

- **WHEN** the step runs
- **THEN** neither `osrm-extract` nor `osrm-partition` is invoked

#### Scenario: The untouched graph is not modified

- **WHEN** the step completes
- **THEN** every file under the untouched graph's directory is byte-identical to what it was before

#### Scenario: The file is missing

- **WHEN** the step runs and `data/segment_weights.csv` is absent
- **THEN** it stops and names the file, rather than producing a copy indistinguishable from the untouched graph

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
