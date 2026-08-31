## MODIFIED Requirements

### Requirement: The segment speed file preserves duration and moves only weight

For every directed segment carrying at least one sample, and for every directed arc leaving a flat-charge booth, the step SHALL write one row of `from_osm_id,to_osm_id,edge_speed_in_km_h,edge_rate` to `data/segment_weights.csv`.

The **speed** SHALL be the segment's original speed on the untouched graph, so that applying the file leaves the segment's duration as it was.

The **target weight** SHALL be

    target_weight = original_weight + toll_eur / wage_eur_per_hour * 3600
    toll_eur      = segment_price_eur + flat_charge_eur
    segment_price_eur = price_per_kilometre * length_in_metres / 1000
    flat_charge_eur   = the tariff of the flat-charge booth this arc leaves, or zero

`wage_eur_per_hour` SHALL default to 20 and SHALL be settable. The added term is the time a driver earning that wage works to pay what the segment costs: a 100 m segment at 2 EUR/km costs 0.20 EUR and adds 36 seconds, and an arc leaving a 55.50 EUR barrier adds 9 990 seconds however short it is.

The **stored weight** SHALL be the target weight rounded to the granularity `osrm-customize` keeps, which is one over the routing profile's weight multiplier. The stock profile sets no `weight_precision`, so the multiplier is 10 and the granularity is 0.1 weight units.

The **rate** SHALL be `length_in_metres / stored_weight`.

Rounding the target before inverting it, rather than leaving the rounding to `osrm-customize`, does not change the graph. `osrm-customize` computes `round(length / rate * multiplier)`, which is the same integer either way. Measured against a file written the old way from the same graph, no stored weight moved on any of 249 781 rows, and no speed moved.

What it changes is the file: a row now names a weight the graph can hold, so a rerun that produces the same graph produces the same bytes. Left unrounded, the rate carries digits the graph discards, and a rerun that changes no weight anywhere still rewrites most of the file — measured at one regeneration, 38 306 rows moved and 3 of them changed a stored weight.

The original speed, weight and length SHALL be taken from the router's own annotations, not from a separate reading of the extract. For a sampled segment they come from the priced routes that drove it; for an arc leaving a flat-charge booth they come from a route across that arc. They are the numbers the graph was built with, so anything derived elsewhere could disagree with it.

Where a segment's annotations disagree between the routes that drove it, the observation giving the shortest duration and the lowest weight SHALL be taken. The router folds a turn penalty into the segment before the turn, and a penalty only ever adds, so the smallest observation is the one free of it.

The rate SHALL be written with enough precision that the weight `osrm-customize` derives from it is the stored weight the row was built from, and not a neighbouring one. Nine decimal places is what that takes at the small end of the range: the smallest rate the file carries is 0.001371056, an arc leaving a 55.50 EUR barrier, and six places there would name a weight 0.08% away from the one the row means.

No row SHALL be written for a segment that no priced route drove and that leaves no flat-charge booth. Such a segment is not known to be tolled, and a row would restate its speed to no purpose while risking a changed duration.

#### Scenario: A row is derived

- **WHEN** a segment is 100 m long, takes 2.77 s, has weight 2.77, and its rate is 2.00 EUR/km
- **THEN** its target weight is `2.77 + 36`, that is 38.77, its stored weight is 38.8, and its row carries a speed of 129.963899 km/h and a rate of `100 / 38.8`, that is 2.577319588

#### Scenario: A row for a barrier arc is derived

- **WHEN** the arc leaving a 55.50 EUR barrier is 13.7 m long, takes 2.3 s and has weight 2.3
- **THEN** its target weight is `2.3 + 9990`, that is 9992.3, which is already on the grid, so its stored weight is 9992.3 and its row carries a speed of 21.443478 km/h and a rate of 0.001371056

#### Scenario: The row names the weight the graph stores

- **WHEN** the file is applied and a segment carrying a row is annotated by the router
- **THEN** the weight the router reports for that segment equals the stored weight its row was built from, exactly

#### Scenario: A rerun that changes no weight changes no byte

- **WHEN** the step is rerun and every segment's target weight moves by less than half the granularity
- **THEN** the file it writes is byte-identical to the one it wrote before

#### Scenario: A rerun that changes a weight changes only those rows

- **WHEN** the step is rerun and one journey routes differently, moving the fitted rate on many segments but the stored weight on only a few
- **THEN** only the rows whose stored weight moved, and the rows whose segments the reroute added or dropped, differ in the file

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
