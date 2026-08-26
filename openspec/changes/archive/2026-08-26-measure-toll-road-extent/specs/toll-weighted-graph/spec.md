## MODIFIED Requirements

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
