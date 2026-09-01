## Context

See `proposal.md` — Why. Two defects meet at one booth: the sweep cannot reach THEZE's free side, and a booth it fails to settle is read downstream as a barrier. The first is a sampling gap, the second a check nobody performs.

They are worth fixing together because each hides the other. With the sampling fixed there is no unsettled booth left to expose the consumer defect; with the consumer fixed the sampling gap merely becomes visible instead of silent.

## Goals

- Settle a side no route-set place reaches, using the rules the capability already has.
- Stop a consumer reading a gap as a fact about the road.
- Move no side that is settled today.

## Non-Goals

- Changing the sweep, the verdict rules, the between-booth filter, or the output format.
- Drawing every place target from the catalogue. That would give every booth nearer targets and could move sides that are already established; measuring what moved would be a change of its own.
- Fixing THEZE by hand. The override file could state its sides, and the next such booth would again be found by accident.

## Decisions

### Widen the pool, do not force the route

The sweep's places come from `data/route_set.yaml` — the 745 the coverage search used as endpoints. The catalogue in `data/filtered.osm.pbf` holds every `place=` node in the extract. A side goes unobserved when nothing it can reach is offered to it, and the fix is to offer more, not to route differently.

Lalonquette settles THEZE's side outright: `place=village`, 2.0 km due north up the very road in question, absent from the route set. Both directions give `outside`, with one booth on the route, under the existing rules.

The retry is confined to unobserved sides. That keeps the change incapable of moving a settled side, which is what makes it safe to apply without re-verifying all 106 labels.

### Rejected: force the route down the side with a waypoint

This was the mechanism the first draft of this change specified, and implementing it showed it does not work. Recorded because it looks obviously right.

Two problems, both measured. First, `observe()` attributes an observation to the side facing the *target* — the node after the booth when routing away, before it when routing towards — so a route starting on side A and passing the booth reports side B. Forcing the start onto A does not make the observation about A. Second, forcing it with a waypoint produces a U-turn: routed booth → side A → place, all nine of THEZE's place targets come back through the booth, because the fast way to each is back onto the A 65. A route that crosses the booth twice supports no verdict.

### Rejected: settle the side by reachability

`escapes_freely`, from `measure-toll-extent-by-commitment`, asks whether a driver leaving by a node reaches the open network without crossing a toll point. It separates THEZE's sides correctly. It is still the wrong rule here, and the inventory says so: checked against every side the sweep has settled, it agrees on 84 labels and disagrees on 22.

The two answer different questions. "Inside" means holding a ticket, which the sweep derives from the roles of the booths it reaches; reachability asks whether the road physically lets you out, which on a ticket network is weaker — one gap in the ring and the closure escapes. A rule that contradicts the primary rule one time in five should not be the fallback when a better one exists.

### Rejected: anchor the place rule at the side node

Route from the side's own node to the places and ask whether any is reached without crossing a booth. Measured over all 745 places, both of THEZE's sides cross a booth every time, so it separates nothing. Every mechanism built on "where does the router go" meets the wall that broke the sweep: the motorway is faster.

### A consumer tests the inventory, not the emptiness of a list

`build_vinci_direct_prices.load_sides` calls a booth a barrier when either list is empty. That is true of a barrier and equally true of a booth that never settled, and the two mean opposite things: a barrier is a fact about the road, an unsettled booth is an absence of evidence.

The capability already prescribes the test — an unsettled booth is distinguishable "by the absence of its remaining nodes from both lists, checked against the inventory's `adjacent_nodes`". Measured over the current file it separates them exactly: THEZE leaves one of two adjacent nodes in neither list, while both genuine barriers list both of theirs. So no format change is needed; the consumer simply has to perform the check the format was designed for.

`build_toll_extent` needs the same test for a different reason. It uses `inside_nodes` to keep a two-way booth's region on the right side, and an incomplete `inside_nodes` silently removes that restriction rather than failing — a wrong measurement rather than a missing one. It should leave such a booth unmeasured, which its own fallback already handles.

## Risks / Trade-offs

- **The catalogue is large, and offering a booth thousands of targets is slow.** → It is consulted only for an unobserved side, and the sector rule caps what is offered as it does for the sweep. One booth qualifies today.
- **A catalogue place settles a side the sweep would have settled differently.** → It cannot: the retry runs only where the sweep produced nothing at all.
- **Fixing the sampling removes the only instance of the consumer defect, so the consumer fix ships untested against real data.** → It is testable by withholding the catalogue retry and re-running, which reproduces the unsettled state on demand. Task 4.3 does exactly that.
- **The change rests on one booth.** → The consumer half does not. It is a check that any future gap will need, and its absence is why this one cost a booth's worth of pricing without a word in any report.

## Migration Plan

1. Add the catalogue retry to `builder/build_booth_sides.py`, after the sweep, before the report.
2. Add the inventory check to `build_vinci_direct_prices.load_sides` and to `build_toll_extent`.
3. Delete `data/bidirectional_booth_sides.yaml` and re-run step 7; it is checkpointed on existence, so a stale file would survive.
4. Verify THEZE settles, and that every other booth's sides are byte-identical to the committed file.
5. Steps 8 and 9 read the file. Neither changes for a booth whose sides did not move, and THEZE gains a settled side it did not have.

Rollback is the previous `data/bidirectional_booth_sides.yaml`, which is tracked.

## Open Questions

None. The distance bounds and sector rule for catalogue targets are the sweep's own, and the one booth available settles from a place well inside them.
