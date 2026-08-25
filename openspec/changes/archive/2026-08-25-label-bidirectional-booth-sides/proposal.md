## Why

`type: bidirectional` records one fact: the booth sits on a way OSM tags two-way. It says nothing about which side of it is the toll network and which is the free road, and that is the distinction every consumer actually needs.

Step 7 needs it most. It pairs a two-way booth as an entrance without any check that the route leaves on the side that makes it one, which is why 15 of its 17 `unexpected answer` findings are pairs of two-way booths.

A first attempt classified the sides by direction of travel — the node a route arrived from against the node it departed to. That is measurable during step 4 and it is the wrong quantity: an ordinary interchange ramp is driven both ways, so it labelled 35 of 47 booths "two-way" and told step 7 nothing.

What separates the sides is whether you are holding a ticket, and the router can be asked directly.

## What Changes

- Step 3 writes `adjacent_nodes` on every `bidirectional` booth: each node adjacent to it on a through-class way, mapped to whether the way reaching it is one-way. The override file's bare `enter`/`exit`/`passthrough` types stop being inert and correct a wrong `oneway=no` tag before grouping.
- A new step, `build_booth_sides`, determines each two-way booth's sides by probing with the router, and writes `data/bidirectional_booth_sides.yaml`.
- It runs **after** the pricing step: the probe needs the `enter`/`exit` roles that only `data/vinci_price.yaml` carries, so it cannot live in step 4.
- Each side is settled as `inside_nodes` — on the toll network, you are holding a ticket — or `outside_nodes`, where you circulate freely.
- A booth with one inside side and one outside side is an entrance/exit. A booth whose every side agrees is a barrier: you pay passing and never hold a ticket.
- A side with conflicting evidence stops the step and names the routes, which is how map defects are found. A side with no evidence is reported and does not.
- **BREAKING** `data/osm_toll_booths.yaml` gains `adjacent_nodes` on two-way booths.

## Capabilities

### New Capabilities

- `bidirectional-booth-sides`: what `adjacent_nodes`, `inside_nodes` and `outside_nodes` mean, how the probe establishes a side, what makes an observation admissible, the two settled states, and the errors.

### Modified Capabilities

- `toll-booth-inventory`: step 3 emits `adjacent_nodes` for `bidirectional` booths, and the override file's bare `enter`/`exit`/`passthrough` types stop being inert.
- `build-pipeline`: the pipeline gains a named step between pricing and direct pricing.
- `route-set-generation`: the route search explicitly does not classify booth sides.

## Impact

- **New**: `builder/build_booth_sides.py`, `data/bidirectional_booth_sides.yaml`.
- **Modified**: `builder/build_osm_toll_booths.py`, `builder/booth_groups.py`, `builder/overrides.py`, `Makefile`, `builder/Dockerfile`.
- **Reverted**: the direction-of-travel classification added to `builder/build_route_set.py`. It measured the wrong quantity and nothing consumed it.
- **Not in scope**: step 7 using the sides. That follows once they exist.
- **Runtime**: about 89 000 local route requests, two minutes. No operator requests at all.
