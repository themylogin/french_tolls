## Context

See `proposal.md` — Why. Measured from the twenty stored journeys before writing this:

- Faithfulness and the travel-time ratio move together. Below 80% overlap the ratio averages x0.9087; between 80 and 90, x0.9174; above 90, x0.9447. Correlation +0.464 over n=20.
- Refinement is predictable from what is already stored. Modelling *"inserting a waypoint removes that stretch's drift and adds none"* gives 15 of 20 journeys at 99% overlap or better and 5 below. Validated where it could be: Bayeux to Apt predicted 92.0%, measured 91.8%.
- The predicted overlaps leave an empty band between 97.7% and 99.5%, so a threshold of 98% and one of 99% produce the identical 15/5 split. The number is not delicate.
- Four of the five predicted-divergent journeys are ones whose waypoint budget cannot cover their drift: Hendaye to Wissembourg arrives with 8 of 9 slots already used and 7 stretches to correct.
- `french_tolls/refine.py` holds `drift_sections` and `waypoints_for`, already used by the application. `french_tolls/geometry.py` is already imported by the evaluation, so the pattern for sharing exists.
- `evaluation/fetch_google_routes.py` requests `FieldMask: *` and stores the response whole; the median response is 220 KB.

## Goals / Non-Goals

**Goals:**

- Measure the route a driver is actually sent down.
- A travel-time multiplier that means one thing.
- Say why a journey stayed divergent.

**Non-Goals:**

- Raising the nine-waypoint ceiling, or buying a second refinement pass for journeys the first cannot fix. This change measures the ceiling's effect; what to do about it needs the measurement.
- Re-buying the twenty journeys already stored. Their unrefined answers stay as the before-refinement baseline.
- Changing the application. The evaluation imports its refinement code; it does not call its endpoints.

## Decisions

### The evaluation refines for itself, importing the application's code

Two ways to refine each journey:

| | calls the app's `/api/refine` | refines in-process |
| --- | --- | --- |
| algorithm under test | the real one | the real one, imported |
| spends against | the app's monthly ceiling | the evaluation's own guard |
| a 2 450-journey sweep | exhausts the app's ceiling at once | bounded by the guard, as today |
| pollutes the app's database | yes, 2 450 journeys of it | no |

In-process. The application's ceiling exists to keep a public service inside a free allowance; a bulk sweep driven through it would consume that allowance and fill the application's store with journeys no user asked for. The evaluation already has a guard designed for bulk, and it already imports `geometry` for exactly this reason.

What must not diverge is the algorithm, so `drift_sections` and `waypoints_for` are imported from `french_tolls.refine` rather than copied — the same rule that moved `geometry.py` into the package.

### Two phases, both stored

```
      ask Google through our waypoints
                 │
                 ▼
      measure drift ─────────────► keep: overlap, drift, distance, duration
                 │                       (geometry discarded — never drawn)
                 ▼
      place waypoints in the worst stretches
                 │
                 ├── nothing to place ──► the route already in hand is the answer
                 │                         (one request, not two)
                 ▼
      ask Google through the refined waypoints
                 │
                 ▼
      keep the whole response ────► this is what the report ranks and draws
```

Discarding the first geometry is what keeps the corpus where it is. Two whole responses would be ~1.1 GB over 2 450 journeys; one whole response plus the other's numbers stays near 660 MB.

Storing each phase as it completes makes the sweep resumable between them, and lets the twenty existing answers be topped up with one request each instead of two.

### The threshold is settable and printed

`--close-overlap`, defaulting to 0.98. Printed with the result, because a reader who does not know where the line was drawn cannot interpret either figure.

0.98 rather than 0.95 or 0.99 because the predicted distribution has nothing between 97.7% and 99.5% — 98 and 99 give the same split, and 98 sits in the middle of the empty band rather than on its edge.

*Alternative rejected:* deciding the threshold from the data at report time, by finding the largest gap. It would move between runs, and two reports would then not be comparable.

### Why a journey stayed divergent

For each diverging journey the report says whether the waypoint budget could have covered its drift — comparing the drift the budget's worth of stretches accounts for against the total. Four of the five predicted-divergent journeys fail that test, and it is the difference between "the algorithm placed them badly" and "there was nowhere left to put one".

### The guard counts requests against the free cap

`USD_PER_1000_ADVANCED = 10.0` goes, and with it the comment claiming that intermediate waypoints imply an "Advanced" tier. Neither is supported: Google's pricing page names Essentials and Pro, does not say which a waypointed route request falls into, and states a free cap of 10 000 requests a month. The dollar figure was written from memory.

The guard reports requests and what share of the monthly cap they consume. A full sweep is 4 900 of 10 000 — the useful fact being what is left for the application, which shares the key.

*Consequence:* the guard can no longer say what a run costs in money, because that cannot be derived from the published pricing. Saying nothing is better than saying a number that was invented.

## Risks / Trade-offs

- **The refinement model may not hold.** The 15/5 prediction assumes a new waypoint removes its stretch's drift and creates none elsewhere. One journey validates it; nineteen do not. → The measurement is the point; a prediction that turns out wrong is a finding, not a failure.
- **Two spenders on one allowance.** A sweep of 4 900 leaves 5 100 for the application that month. → The guard states what it leaves. Nothing enforces the division, and a sweep run twice in a month would exhaust it.
- **The corpus's meaning changes.** The twenty stored journeys currently *are* the pre-refinement baseline; after this they carry both. → The two are kept distinct in the file, and the report prints both.
- **A journey that gets worse after refining.** Nothing guarantees the extra waypoints help. → It would land in the diverging population with its before-overlap recorded beside its after, which makes it visible rather than hidden.
- **The threshold is a judgement.** 98% is defended by a gap in twenty journeys. Over 2 450 the distribution may have no such gap. → Settable and printed; the first full run is what would say whether 98 still divides anything real.

## Migration Plan

1. Import the refinement functions into the evaluation.
2. Add the second phase to the fetch, storing each phase as it completes.
3. Change the guard to count requests against the free cap.
4. Split the report's third section, and add the budget diagnosis.
5. Top up the twenty stored journeys — 20 requests.
6. Read the report and record what the split says.

Rollback is reverting two scripts; the stored answers keep their unrefined measurements either way.

## Open Questions

None blocking. Whether 98% still divides a real population over 2 450 journeys is a question the first full run answers, and the threshold is settable precisely so that answer can be acted on without a code change.
