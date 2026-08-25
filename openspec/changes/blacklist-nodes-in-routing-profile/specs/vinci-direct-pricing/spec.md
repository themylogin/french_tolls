## REMOVED Requirements

### Requirement: A route through a blacklisted node stops the step

**Reason**: The routing profile now makes a blacklisted node impassable, so no route the step receives can traverse one. The stop condition is unreachable.

**Migration**: None. Pairs that stopped the step under the old rule are now routed around the defect and judged on their merits — priced, or rejected for a booth in the way, or rejected for a wrong side. The last survey stopped on 335 such pairs, 211 of them reaching one booth whose approach crossed a single node; those become ordinary results.

Prices recorded before this change are unaffected: a route that reached a booth without touching a blacklisted node is the same route under either rule.
