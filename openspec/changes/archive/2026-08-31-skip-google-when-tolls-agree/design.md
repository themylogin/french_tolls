## Context

See proposal.md — Why.

The decision lives in `french_tolls/drive.py` as a generator over values. It reads a `Part` and yields `AskRoute` and `AskGoogle`; `french_tolls/bot.py` performs those and builds the `Part` from the service answer. The rule being added needs one fact the `Part` does not carry today: which booths the **fastest** route crosses. The optimal route's set is already there, as `Part.booths`.

That fact is already published. `route.get_route` returns `{"fast": ..., "optimal": ...}` and `_describe` puts a `booths` key on both, from `booths_crossed` over each route's own node ids. So the rule costs no request and no computation — only a field.

`Part.booths` is `frozenset | None`, and None means nobody established the set. The new field carries the same distinction for the same reason.

## Goals / Non-Goals

**Goals**

- The rule is a value comparison inside the decision, testable with a hand-built `Part` and no network.
- The bot reads the fastest route's booths from the answer it already has.

**Non-Goals**

- Changing what `route.py` returns. The data is there.
- Changing the evaluation. It measures how faithfully Google follows our road and does not run this decision.
- Detecting, in production, a journey this rule answered wrongly. By construction we never ask, so there is nothing to compare against. See Risks.

## Decisions

### Compare booth sets, not costs

Two routes crossing the same booths cost the same, so the cost test would accept a strict subset of what the booth test accepts and would accept it for a weaker reason. Two different booth sets can also total the same price by coincidence, and a cost test would call that agreement when the driver is being sent through different barriers.

*Alternative considered:* compare `optimal["cost"]` with `fast["cost"]`. Rejected — cheaper to write, wrong on coincidental totals, and the codebase already reasons in booth sets everywhere else that compares two routes.

### Equality, not containment

`drive.accepts` uses containment — `booths(theirs) <= booths(ours)` — because a route crossing *fewer* of our booths costs the driver less and needs no correction. The same argument would admit a fastest route that crosses a subset.

This rule uses equality anyway. Containment there is applied to a route Google has actually said it would drive; here it would be applied to a route from our own fast graph, standing in for a Google route nobody has asked about. A strict subset means our two graphs disagree about which road to take, and that disagreement is exactly the signal that the plain link is not settled. Equality is the case where our graphs agree and there is nothing left to check.

*Alternative considered:* `fast.booths <= optimal.booths`. Rejected — it fires precisely where the two roads differ, which is where the rule's own justification fails.

### The rule sits between "pays no tolls" and "budget exhausted"

Below rule 1 because a toll-free part has two empty booth sets and matches this rule as well, and the avoid-tolls instruction is still owed: the sets compared are drawn from this project's graph, and the setting governs what the driver's own application chooses. Rule 1 must win or a toll-free journey silently loses its instruction.

Above the budget rule because this rule produces a settled answer at no cost, and the budget rule produces an unchecked link with a caveat. A part that can be answered for nothing should never be answered with an apology.

### The `Part` carries the fastest route's booths

`part_of` reads `answer["fast"]["booths"]` alongside the optimal set it already reads, and both halves produced by a split get theirs the same way, because `perform(AskRoute)` calls `get_route` and builds a `Part` from the full answer. So the rule applies at any depth with no extra plumbing.

*Alternative considered:* have the decision yield a new request for the fastest route's booths. Rejected — the answer already carries them, and a new request type would put a round trip in front of a rule whose whole point is that it costs nothing.

### A link accepted this way records its own basis

`Message.basis` is `TOLLS`, `ROAD`, or None, and `bot.send_outcome` logs which. A rule-2 link is accepted on tolls, but on tolls nobody paid to learn. Logging it as `TOLLS` would merge two populations in the one place an operator can see them apart, and the interesting question — how often the flow now answers for free — would become unanswerable from the log.

### The link carries no waypoints

Waypoints steer a fastest-path router off the road it would pick and onto the optimal one. Where both roads cross the same booths there is nothing to steer away from. Sending the optimal route's waypoints would constrain a route that is already acceptable, and would make the link longer for no gain.

## Risks / Trade-offs

**Our fast graph is not Google's router.** The rule concludes "Google's road will pay these tolls" from "our two graphs pick roads that pay these tolls". Google optimises for time under live traffic and may pick a third road with a booth neither of ours crosses. The driver would then pay more than they were quoted, and nothing would notice. → This is the trade the request makes deliberately, and it is bounded: it applies only where our own fastest and cheapest roads already agree, which is the case where a fastest-path router has the least room to differ. It is accepted knowingly rather than mitigated in code.

**The error is invisible in production.** Because no request is made, there is no Google route to compare against, so the flow can never report how often this rule was wrong. → It can be measured offline instead. The evaluation corpus holds bought Google routes and this project's booth sets for the same journeys; the rate at which a journey with equal fast and optimal booth sets got a Google route crossing a different set is computable from what is already stored, with no new spending. Worth running before this rule is trusted widely, and out of scope here.

**A toll-free journey losing its instruction.** Empty sets are equal, so rule 2 matches every toll-free part. → Rule ordering, stated in the spec and covered by a unit test that a toll-free part still receives the avoid-tolls instruction.

**An unknown booth set read as agreement.** `None == None` is true in Python, so a naive equality test would fire when neither set is known. → The spec requires both sets to be known; the implementation must test for that before comparing.

## Migration Plan

None. The rule only removes requests; no stored data, schema, or link format changes. Reverting is deleting the rule and the field.

The new pinned journey records no Google answer, because it makes no request. It still gets a cassette holding an empty list, as `toll-free.json` already does: the file is what says the journey bought nothing, and it pins the routing quality the journey was driven at so a later change of preference is caught rather than silently replayed.
