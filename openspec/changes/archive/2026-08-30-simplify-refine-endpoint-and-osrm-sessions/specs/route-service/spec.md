## ADDED Requirements

### Requirement: The API serves the page from two routes and no more

The HTTP API SHALL expose place lookup and route calculation, and nothing else.

**There SHALL be no endpoint for the refinement.** `google-route-refinement` states why: a refinement describes a particular optimal route, so answering for one separately means computing that route a second time. One question from a visitor SHALL cost one request and one search.

A route query SHALL carry the refinement beside its two routes where the debug setting is on, and SHALL omit the key entirely where it is off. Omission rather than an empty value, so that a caller distinguishes "the operator did not ask for this" from "there was nothing to draw", which is a different fact and is reported inside the key as a reason.

The key SHALL sit beside `fast` and `optimal` rather than inside either. It describes the journey rather than one of its two routes, and nesting it in `optimal` would put it among keys `web-front-end` reads for every route.

Nothing that duplicates a value already in the answer SHALL be carried in it.

#### Scenario: Two routes, and the refinement is not one of them

- **WHEN** the API's routes are enumerated
- **THEN** they are place lookup and route calculation, and no path serves a refinement

#### Scenario: The refinement travels with the answer

- **WHEN** a journey is calculated with the debug setting on
- **THEN** the answer carries `fast`, `optimal`, and the refinement beside them

#### Scenario: The key is absent rather than empty

- **WHEN** a journey is calculated with the debug setting off
- **THEN** the answer carries `fast` and `optimal` and no refinement key at all

#### Scenario: A caller posting to the old path is not served

- **WHEN** a request is made to the refinement's former path
- **THEN** the API does not serve it

### Requirement: A router request carries its own connection

A request to either routing graph SHALL open its own connection and SHALL NOT reuse one from an earlier request.

Sharing a pool across a search was measured and bought nothing: on the dearest journey — 327 requests — a connection per request came out 17% faster on one run and 1% slower on the next, with both arms interleaved in one process. The routers answer in 2 to 11 ms on the same host, so the handshakes disappear into the routing itself.

What the pool did cost was a failure mode. The server closes an idle pooled connection, and the next request over it fails for a reason that has nothing to do with the question asked. Retrying that failure — distinguishing it from a router that is genuinely down, and not counting the retry against the query budget — was the whole of the complication, and it existed only to repair what the pooling broke.

**A connection error SHALL therefore be reported as the router being unavailable on the first failure**, as every other client error already is. There SHALL be no retry.

The request timeout SHALL still apply, per request. It is the point at which something is wrong rather than slow, and that is a property of a request rather than of a session.

The query budget SHALL be unchanged in meaning and in value. It bounds the questions a search asks, and it SHALL NOT be spent on a retry, because there is none.

#### Scenario: Nothing is reused between requests

- **WHEN** a search issues several hundred router requests
- **THEN** each opens its own connection, and none is reused from a previous request

#### Scenario: A dropped connection is not retried

- **WHEN** a router request fails to connect
- **THEN** the query fails with the router reported unavailable, without a second attempt

#### Scenario: One failure counts once

- **WHEN** a router request fails to connect
- **THEN** exactly one request has been counted against the query budget

#### Scenario: A slow router still times out

- **WHEN** a router does not answer within the timeout
- **THEN** the request fails with the router reported unavailable

#### Scenario: The budget still bounds the search

- **WHEN** a search reaches the query budget
- **THEN** it stops, as it did before, and the budget's value is unchanged
