## Purpose

Turns the entrance/exit tariffs in `data/vinci_price.yaml` into a per-segment price and an OSRM segment speed file, so that a second routing graph costs the toll network what it actually costs a driver instead of treating it as free.

## ADDED Requirements

### Requirement: A priced pair contributes one sample per segment it drives

A **priced pair** is an ordered pair of booth groups where the source group carries a price in `data/vinci_price.yaml` under a gare code, and the target group is the group carrying that gare code. Every priced pair SHALL be routed on the untouched graph, from the source group's coordinates to the target group's coordinates.

The pair's **price per kilometre** SHALL be its tariff divided by the length of that route in kilometres. That one value SHALL be recorded as a sample against every directed segment the route drives, where a directed segment is an ordered pair of consecutive OSM node ids from the route's node annotation.

The route's first and last segments SHALL be excluded. The router snaps each endpoint onto a lane, so those two segments are partial: their length and duration are a fraction of the segment's own, and taking them as whole would misstate both the sample and the segment's speed.

A gare code carried by more than one group SHALL be resolved to the group whose route from the source crosses no third booth. Where more than one qualifies, the shortest route SHALL be taken.

Whether a route crosses a booth group SHALL be decided by resolving each traversed node through the inventory's aliases, never by looking for the group's own node id. A plaza has one lane per booth and the inventory records the others as aliases of it, so a route crosses the group by whichever lane the router picked. Asking for the representative's id finds nothing when the router used a neighbouring lane, and the pair is then discarded as though its own booths were not on its route.

#### Scenario: A tariff becomes a rate

- **WHEN** a pair priced at 14.50 EUR routes 105.5 km
- **THEN** every directed segment of that route except the first and the last records a sample of 0.1375 EUR/km

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

### Requirement: The segment speed file preserves duration and moves only weight

For every directed segment carrying at least one sample, the step SHALL write one row of `from_osm_id,to_osm_id,edge_speed_in_km_h,edge_rate` to `data/segment_weights.csv`.

The **speed** SHALL be the segment's original speed on the untouched graph, so that applying the file leaves the segment's duration as it was.

The **rate** SHALL be `length_in_metres / target_weight`, where

    target_weight = original_weight + segment_price_eur / wage_eur_per_hour * 3600
    segment_price_eur = price_per_kilometre * length_in_metres / 1000

`wage_eur_per_hour` SHALL default to 20 and SHALL be settable. The added term is the time a driver earning that wage works to pay the segment's toll: a 100 m segment at 2 EUR/km costs 0.20 EUR and adds 36 seconds.

The original speed, weight and length SHALL be taken from the router's own annotations on the priced routes, not from a separate reading of the extract. They are the numbers the graph was built with, so anything derived elsewhere could disagree with it.

Where a segment's annotations disagree between the routes that drove it, the observation giving the shortest duration and the lowest weight SHALL be taken. The router folds a turn penalty into the segment before the turn, and a penalty only ever adds, so the smallest observation is the one free of it.

No row SHALL be written for a segment no priced route drove. Such a segment is not known to be tolled, and a row would restate its speed to no purpose while risking a changed duration.

#### Scenario: A row is derived

- **WHEN** a segment is 100 m long, takes 2.77 s, has weight 2.77, and its rate is 2.00 EUR/km
- **THEN** its row carries a speed of 129.963899 km/h and a rate of `100 / (2.77 + 36)`, that is 2.579314

#### Scenario: Duration survives the update

- **WHEN** the file is applied to a copy of the untouched graph and a priced route is requested from both graphs
- **THEN** the two durations are equal — measured at 0.000 s difference over a 105.5 km route of 1 047 segments

#### Scenario: A turn penalty is discarded

- **WHEN** one route observes a segment at 2.77 s and another, turning immediately after it, at 5.77 s
- **THEN** 2.77 s is used

#### Scenario: An untouched segment

- **WHEN** a directed segment is driven by no priced pair
- **THEN** it has no row in the file, and its speed and weight on both graphs are identical

#### Scenario: The wage is settable

- **WHEN** the step is run at 40 EUR/hour
- **THEN** every segment's added weight is half what it is at 20 EUR/hour

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

The tolerance on that difference SHALL be 20% by default and SHALL be settable. It is not a bound on the graph's arithmetic, which is exact; it is a bound on how far the per-segment means reconstruct this one tariff. Measured, the pair comes back at 36.2 minutes — the means price this journey at 12.07 EUR against the operator's 14.50, an error of -16.7% that sits inside the measured p90 of 24.4% for all pairs.

The durations SHALL be equal. Measured, they are: 3688.7 s on both graphs.

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

#### Scenario: The check fails

- **WHEN** the weight difference is outside tolerance
- **THEN** the step stops and reports both weights, both durations and the expected difference
