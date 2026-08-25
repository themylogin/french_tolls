## Context

See proposal.md — Why. Measured against the current data:

```
two-way booths           45 entrance/exit, 2 barrier
prices in the file       23 148
  source is a barrier         0     nothing to invalidate outright
  target gare is a barrier    0
  source is a two-way e/e  2 130
  target gare is a two-way 2 121
  touching a two-way booth 4 027    17.4% of the file
grid                     sources 516 -> 514, targets 513 -> 511
```

## Goals / Non-Goals

**Goals:**

- Stop pairing a two-way booth as an end it is not acting as.
- Keep the two rejection reasons distinguishable in the record.
- Re-derive only what the rule can have affected.

**Non-Goals:**

- Re-running the whole grid. 19 000 prices between one-way booths are untouched by this and are not asked again.
- Deciding what the two barriers should be typed as. They are excluded here; re-typing them is a separate question.

## Decisions

### The test is on the node beside the booth, at both ends

```
source   the route departs toward D    require D in inside_nodes
target   the route arrives from A      require A in inside_nodes
```

Both ends want the toll-side node, which reads oddly until you say it aloud: entering the network means driving *into* it, leaving means arriving *from* it. The same node the sides were established from, so the two cannot drift apart.

This is checked after routing rather than before. Which side a route uses is not knowable until it exists, unlike a barrier, a self-pair or a prohibited pair — all of which are dropped before a route is requested.

### A wrong-side rejection names no booth

The rejection database's `blocker` is currently `NOT NULL`, which encodes an assumption that every rejection is about a third booth. A wrong-side rejection implicates none.

```sql
blocker  INTEGER,              -- was NOT NULL; null for a wrong-side rejection
reason   TEXT NOT NULL         -- 'booth' | 'wrong side'
```

Naming a booth anyway — the source, say, or a sentinel — would make the table unreadable afterwards, and the point of recording rejections is that someone can read them.

### The 4 027 prices are discarded rather than filtered

Nothing in `vinci_price.yaml` records which side a route used, so a price recorded before the rule cannot be checked against it. The amount is a number; the journey that produced it is gone.

So they are discarded and asked again. About 67 minutes of rate requests. The alternative — keeping them and applying the rule only to new pairs — would leave the file a mixture of two contracts with no way to tell which entry follows which, and that is worse than an hour.

Prices with a one-way booth at both ends are untouched. The rule cannot have affected them, and re-asking 19 000 of them would cost five hours to learn nothing.

## Risks / Trade-offs

**The rule may reject pairs that are real tickets** → if a two-way booth's sides are wrong, every pair through it is wrongly judged. The sides carry their own cross-check — the two barriers are exactly the two-way booths with a flat price and no pair prices, in data the probe never reads — but that validates the barriers, not all 45 entrance/exit booths. A sharp fall in priced pairs through a particular booth would be the signal to look.

**It may not fix the 15 findings** → they are the reason for the change and the expectation is that they become ordinary rejections, but that is a prediction. If a finding survives, the pairing was clean on both sides and something else explains it — most likely the route leaving and re-entering the network, which no rule here tests.

**Two writers on the rejection database schema** → the migration is additive, and the step creates the table if absent. An existing database from before this change has no `reason` column, so it must be dropped and rebuilt rather than migrated. That costs seven minutes of routing and no requests.

## Open Questions

None that change the specs, the approach, or the tasks.
