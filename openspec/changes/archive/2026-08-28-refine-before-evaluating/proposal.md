## Why

The evaluation measures the wrong thing. It buys Google's route through the waypoints the optimal search emits, and reports how faithfully Google followed. But that is no longer what a user is given: since `refine-waypoints-with-google`, a link carries the *refined* waypoints, and the route Google drives through those is a different route.

So the headline figures describe a link nobody receives. Bayeux to Apt is recorded at 74.4% faithful; the link a driver actually follows measured **91.8%**.

The travel-time multiplier is worse than out of date — it is contaminated. It averages over two different questions, and the existing corpus shows the two pulling apart:

```
overlap < 80%    n=7    x0.9087
overlap 80-90%   n=6    x0.9174
overlap >= 90%   n=7    x0.9447          correlation(overlap, ratio) = +0.464
─────────────────────────────
ALL MIXED        n=20   x0.9239
```

Where Google drove our road, the ratio compares OSRM's clock with Google's on the same tarmac. Where it drove its own, the ratio compares our time on one road with Google's on another — which says nothing about clocks and everything about Google preferring a different road. One number over both cannot be read as either.

## What Changes

### Every journey is refined before it is analysed

- **BREAKING** A journey's stored answer becomes the route Google drives through the **refined** waypoints, not the original ones. That is the route a driver is sent down, and the only one worth measuring.
- Refining needs the unrefined route first — the stretches where Google left ours are what the new waypoints are placed in — so each journey now costs **two** Google requests instead of one.
- The unrefined route's measurements are kept: its faithfulness and its drift are what justify the refinement, and the report shows the before and after together. Its geometry is not kept; only the refined route is drawn or ranked.
- The refinement SHALL use the same drift and placement code the application uses, imported as `geometry` already is. What is measured has to be the algorithm, not a second copy of it.

### The multiplier is reported per population, with counts

- **BREAKING** Report section 3 stops being one number. It becomes two, each with its count, its spread, and the threshold that separated them:
  - journeys Google drove **faithfully after refining** — the OSRM-to-Google clock comparison;
  - journeys that **still diverge** — how much time Google believes it saves by ignoring the route.
- Both are results. The second is not a residue: it quantifies what a driver gives up by following our link rather than Google's own idea.
- The overall mixed average SHALL still be printed, labelled as mixing the two, so the change to the headline is visible rather than silent.

### A journey that still diverges says why

Four of the five journeys predicted to remain divergent are ones where the nine-waypoint ceiling cannot cover the drift — Hendaye to Wissembourg arrives with eight waypoints already used and seven stretches to fix with one slot. The report SHALL name that, so a divergent journey is diagnosed rather than merely listed.

### The guard counts requests, not invented money

- **BREAKING** The spending guard stops quoting a dollar figure. `USD_PER_1000_ADVANCED = 10.0` and its claim that intermediate waypoints imply an "Advanced" tier were written from memory and are not supported by Google's pricing page, which names Essentials and Pro tiers and does not say which applies.
- What the page does state is a **free cap of 10 000 requests a month**. The guard SHALL count against that instead: a full fifty-city sweep at two requests each is 4 900, inside the cap, and the useful question before a run is how much of the month's allowance it will consume — not a price that was guessed.
- The application shares the key and therefore the cap. The guard SHALL say what it is about to use and leave.

## Capabilities

### Modified Capabilities

- `google-route-comparison`: what is bought and stored per journey, what the report's third section says, and what the spending guard counts.

## Impact

- Modified: `evaluation/fetch_google_routes.py` (two-phase fetch, the guard), `evaluation/report.py` (the split, the diagnosis), the stored answer's shape.
- Unchanged: the application, the pipeline, the unit suite, `make all`, `make test`.
- **The 20 stored answers are unrefined.** They are not discarded: their measurements remain the before-refinement baseline. Each needs one further request to gain the refined route — 20 requests, well inside the monthly cap.
- Requests for a full sweep: 2 450 → **4 900**, against a free cap of 10 000 a month.
- Not addressed: whether the nine-waypoint ceiling should be raised, or a second refinement pass bought for journeys the first cannot fix. This change measures the ceiling's effect; deciding what to do about it needs the measurement first.
