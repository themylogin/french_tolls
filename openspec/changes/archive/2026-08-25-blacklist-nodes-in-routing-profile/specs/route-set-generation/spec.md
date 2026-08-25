## REMOVED Requirements

### Requirement: A route through a blacklisted node is never selected

**Reason**: The routing profile now makes a blacklisted node impassable, so the router cannot return a route through one. A filter over the returned routes has nothing left to catch, and keeping it would imply the router might still produce such a route.

**Migration**: None for the route set's contract — no route through a blacklisted node was ever selected and none is now. The reports go: there is no discarded-candidate count, and no warning that the blacklist caught nothing. That warning moves in effect to the setup step, which is where a stale entry can now be noticed.

The route set produced under the old rule is not equivalent to one produced under the new. Discarding a candidate removed the coverage it would have given; making the node impassable lets the router find another way to the same booths. So the route set SHALL be regenerated rather than carried over.
