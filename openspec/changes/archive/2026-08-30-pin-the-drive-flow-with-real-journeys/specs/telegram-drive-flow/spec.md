## MODIFIED Requirements

### Requirement: The decision is separable from the chat

The rules above SHALL be expressed as a decision over values — the journey, its cost, the budget, and what Google answered — that produces what to send: the text, whether an action follows, and which requests to make.

That decision SHALL be testable without a Telegram client, without a chat, without a network, and without substituting objects for the messaging library. A test SHALL be able to state a journey and a sequence of Google answers and assert the messages and requests that result.

Sending the messages, drawing the action, and receiving the press SHALL be the only part that knows about Telegram, and SHALL hold none of the rules.

**That part SHALL itself be constructible for a test.** Separating the rules from the chat leaves the chat untested, and everything that has gone wrong in this flow went wrong there: a bot started with no token, a bot running a stale image, a bot whose Google settings were never passed to it so it told every driver the link was unchecked. None of those is reachable from a test of the rules.

So the Telegram application SHALL be obtainable from a single call that takes its transport rather than opening one, and a caller SHALL be able to drive it by handing it updates. Nothing SHALL require a network connection, a token that authenticates, or a running chat.

**The state the flow keeps SHALL belong to the application rather than to the module.** The origin a driver has sent and the parts they have been offered but not yet asked for are per-application state. Held in module globals they leak between two applications in one process, which makes a second test depend on what the first one did.

The state carried between a message and the press that answers it SHALL be explicit and serialisable, so that a test can construct it directly rather than reproduce the exchange that would have produced it.

#### Scenario: The rules run without a chat

- **WHEN** the decision is exercised with a journey and a prepared sequence of Google answers
- **THEN** it yields the messages and the requests, with no Telegram client involved

#### Scenario: A split is testable end to end

- **WHEN** a test supplies answers that fail the threshold twice
- **THEN** the decision yields a split, the first part's message, and a pending second part, without a network

#### Scenario: The pending part is a value

- **WHEN** a part is left pending
- **THEN** what is needed to answer it is a value a test can build directly

#### Scenario: The chat runs without a chat

- **WHEN** the application is built with a transport supplied by its caller
- **THEN** it accepts updates and produces the calls it would have sent, without opening a connection and without a token that authenticates

#### Scenario: Two applications do not share a driver

- **WHEN** two applications are built in one process and each is sent an origin by the same user id
- **THEN** neither sees the other's origin, and neither can answer the other's button
