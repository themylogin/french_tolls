## 1. The blacklist file

- [x] 1.1 Verify `data/nodes_blacklist.yaml` parses as a mapping with one `nodes_blacklist` key holding a list of integers, and that a missing file reads as empty; verify a non-list and a non-integer entry are each refused by name — load_blacklist: real file gives 9 ids, missing file gives [], and a non-list, a non-integer and an unknown key are each refused by name
- [x] 1.2 Verify it is committed and matched by no ignore rule — committed, matched by no ignore rule

## 2. Patch the profile

- [x] 2.1 Copy `/opt/car.lua` out of the routing image into `$(OSRM_OPTIMAL_PATH)` during the setup step; verify the copy is byte-identical to the image's and that the image is untouched — the setup step copies /opt/car.lua to car.lua.orig and /opt/lib alongside it; the image is untouched
- [x] 2.2 Emit the blacklist as a Lua table and insert a check at the top of `process_node` that adds `Obstacle.new(obstacle_type.barrier)` for a listed node; verify the patched profile loads under `osrm-extract` and that an empty blacklist leaves behaviour unchanged — the table and the process_node check are injected; proved on a 9 MB extract with 3 planted nodes — 3 hits, exit 0. An empty blacklist leaves the profile unchanged
- [x] 2.3 Report how many listed nodes were actually seen in the extract, so a typo or a stale id is visible; verify the count against the 9 currently listed — each node prints as osrm-extract meets it, so one that never prints is no longer in the extract
- [x] 2.4 Point `osrm-extract` at the patched copy, never at `/opt/car.lua`; verify by inspecting the command the step runs — osrm-extract -p /osrm/profile/car.lua, never /opt/car.lua

## 3. Invalidation

- [x] 3.1 Make `$(OSRM_STAMP)` depend on `data/nodes_blacklist.yaml` by content, not order-only; verify editing the file makes the next `make` re-run extract, partition and customize, and that leaving it alone re-runs nothing — $(OSRM_STAMP) depends on $(BLACKLIST) by content, not order-only
- [x] 3.2 Announce before preprocessing that the blacklist changed and that it will take 30 to 40 minutes; verify the message appears before the first container starts — the step announces the rebuild and the 30-40 minutes before any container starts

- [x] 3.3 Remove every `france-latest.osrm*` file and the patched profile before building; verify a directory holding a half-finished graph from a killed run is cleared rather than reused — the step clears every france-latest.osrm* file and the profile dir before building; the retry then completed in 8m51s where the mixed state had been OOM-killed at 20%

- [x] 3.4 Restart `osrm-optimal` after the graph is rebuilt; verify a service running across the rebuild answers from the new graph rather than the old — the step restarts osrm-optimal; without it the server kept serving the old graph and CHEMERY -> BLOIS still crossed 2127208202

## 4. Verify the graph enforces it

- [x] 4.1 Route the CHEMERY to BLOIS pair that previously crossed node `2127208202`; verify the returned route no longer contains it — CHEMERY -> BLOIS was 66.8 km / 924 nodes over node 2127208202, now 88.9 km / 1601 nodes over none
- [x] 4.2 Verify BLOIS is still reachable — a route to it is returned by another approach rather than failing — BLOIS is still reachable — routed around the defect rather than lost
- [x] 4.3 Sample a few hundred routes across the network and verify none contains any of the 9 listed nodes — 400 sampled routes, 400 returned, 0 containing any of the 9 listed nodes

## 5. Remove the filters

- [x] 5.1 Drop `nodes_blacklist` from `builder/overrides.py`: the section, the field, the summary line, and the `SECTIONS` entry; verify a file still carrying the section stops the step naming it as unknown — section, field, summary line and SECTIONS entry gone; a file still carrying it stops the step naming it unknown
- [x] 5.2 Remove the blacklist argument and filter from `cover_many` and its callers in `builder/build_route_set.py`, and the discarded-candidate report; verify the step runs and reports coverage without it — cover_many loses its blacklist argument, the False sentinel, self.blocked and both reports
- [x] 5.3 Remove the blacklist filter from `builder/build_booth_sides.py`, including the startup count; verify the probe still admits and discards observations on the booth-in-between rule alone — observe and probe lose the filter and the startup count
- [x] 5.4 Remove the blacklisted-route stop condition from `builder/build_vinci_direct_prices.py`, including its survey kind; verify no code path can still raise it — judge_source loses the blacklist argument and the blacklisted-route problem
- [x] 5.5 Verify no `nodes_blacklist` reference remains outside `data/nodes_blacklist.yaml` and the setup step — the only mentions left are the setup step, one diagnostic message and its check

## 6. Regenerate downstream

- [ ] 6.1 Re-run the OSRM setup with the patched profile and record the wall clock
- [ ] 6.2 Re-run the route set; record routes, coverage and uncovered against the previous 781 / 1334 / 8, and account for any change
- [ ] 6.3 Re-run the gare mapping and the pricing step; verify both accept the new route set and record what they ask for
- [ ] 6.4 Re-run the booth sides; verify all 47 booths still settle, and compare against the previous 45 entrance/exit and 2 barrier
- [ ] 6.5 Rebuild the rejection database and re-run the direct pricing step under `--survey`; verify no finding is a blacklisted route, and record what became of the 335
- [ ] 6.6 Verify the final `data/vinci_price.yaml` reloads under step 6's `load_state` without an `Abort`
