## 1. The place catalogue

- [x] 1.1 Read the `place=` nodes of `data/filtered.osm.pbf` into a catalogue of coordinates, and verify node 1825323182 (Lalonquette, `place=village`) is among them
- [x] 1.2 Read the catalogue only when a side is unobserved, and verify a run in which every side settles opens the extract not at all
- [x] 1.3 Pass the extract to the step as an argument in the Makefile recipe, alongside the inputs it already takes

## 2. The retry

- [x] 2.1 After the sweep, collect every side that received no admitted observation, and verify it is exactly one node — 10977821568 on booth 986537073 — on the current inventory
- [x] 2.2 Offer each unobserved side catalogue targets by the sweep's own sector and distance rule, and verify Lalonquette is among those offered to that side
- [x] 2.3 Route them in both directions and read the verdict through the existing `observe` and `verdict` functions, and verify no verdict logic is duplicated
- [x] 2.4 Verify booth 986537073 settles with `inside_nodes: [986537071]` and `outside_nodes: [10977821568]`
- [x] 2.5 Verify no booth the sweep settles is revisited, and that all 46 of them keep the sides they have today

## 3. The report

- [x] 3.1 Report the sides settled from the catalogue apart from the sweep's counts, and verify booth 986537073 with node 10977821568 appears there
- [x] 3.2 Verify the run reports 47 booths as 45 entrance/exit, 2 barrier, 0 not settled
- [x] 3.3 Keep reporting a side still unobserved after the retry, and verify none remains

## 4. The consumers

- [x] 4.1 Make `build_vinci_direct_prices.load_sides` judge a barrier by whether every adjacent node the inventory records appears in one of the two lists, and verify booths 277617392 and 6367778328 are still barriers
- [x] 4.2 Return the unsettled booths separately, exclude them from the grid as barriers are, and report them apart from the barrier count
- [x] 4.3 Verify the check on the degraded state: with the catalogue retry withheld, booth 986537073 is reported unsettled rather than counted as a barrier
- [x] 4.4 Make `build_toll_extent` leave an unsettled two-way booth unmeasured and report it, rather than growing a region with no side restriction
- [x] 4.5 Verify that with the sides settled, step 9 derives booth 986537073's two roles with the side restriction applied

## 5. Republishing

- [x] 5.1 Delete `data/bidirectional_booth_sides.yaml`, re-run step 7, and verify the result is byte-identical to the committed file
- [x] 5.2 Re-run step 9 for booth 986537073 and record what its extents become: they stay at the barrier, and correctly so — with the side restriction now applied its region may leave only by 10977821568, from which the free network is reachable without paying, so nothing before the barrier is committed. The task asserted they would move; that expectation was wrong.
- [x] 5.3 Verify `make test` still passes
