## 1. The decision

- [x] 1.1 Add a field to `drive.Part` carrying the fastest route's booth set, `frozenset | None`, defaulting to None, with a comment saying None means nobody established it — the same distinction `booths` already draws; verify `tests/test_drive.py` still passes with every existing `part()` helper call unchanged
- [x] 1.2 Add a basis constant beside `ROAD` and `TOLLS` for a link accepted because the two routes agree, with a comment saying what distinguishes it from `TOLLS`: nobody paid to learn it; verify it is exported in `drive.__all__`
- [x] 1.3 Add the rule to `_part`, immediately after the `part.cost <= 0` branch and before the budget branch: where both booth sets are known and equal, append a `Message` with `prefix.strip()` as its text, a link built with no waypoints, and the new basis, then return; verify the branch tests both sets for being known before comparing, so two Nones do not read as agreement
- [x] 1.4 Update the ordered rule list in the `drive` module docstring to name the new rule in its place, and state why rule 1 is tried first; verify the docstring's order matches the order of the branches beneath it

## 2. The bot

- [x] 2.1 Read `answer["fast"]["booths"]` in `bot.part_of` and pass it to the new `Part` field, converting to a frozenset only when the key is present; verify a `Part` built from a real `get_route` answer carries both sets
- [x] 2.2 Name the new basis in `bot.send_outcome`'s log mapping, with wording that distinguishes it from a link accepted on a paid request; verify driving the pinned journey from 4.1 logs the new wording

## 3. Unit tests

- [x] 3.1 Test that a part with a toll and equal booth sets is answered with one message, no request, and a link carrying no waypoints; verify by asserting the request list is empty
- [x] 3.2 Test that a toll-free part still receives the avoid-tolls instruction even though its two booth sets are both empty and therefore equal; verify the message text, which proves rule 1 is tried first
- [x] 3.3 Test that a part whose fastest route crosses one booth the optimal route does not falls through to the Google request; verify a request is yielded
- [x] 3.4 Test that a part whose fastest booth set is unknown falls through rather than matching; verify a request is yielded, which proves two unknowns are not read as agreement
- [x] 3.5 Test that a part whose fastest booth set is a strict subset falls through; verify a request is yielded, which pins the equality decision against containment
- [x] 3.6 Test that the message carries the new basis; verify by reading `Message.basis`
- [x] 3.7 Test that a half produced by a split is answered by the rule when its own two sets agree; verify the whole journey resolves with fewer requests than the same split whose halves disagree

## 4. Integration tests

- [x] 4.1 Add a pinned journey to `integration/journeys.py` for Perpignan (2.8953121, 42.6985304) to Béziers (3.2131307, 43.3426562), named by its outcome, pinned at `asks=0` and `parts=1`, with the outcome line saying the two routes cross the same booths; verify the existing parametrised tests pick it up and pass
- [x] 4.2 Add a test asserting that this journey's one message carries a link with no waypoints and does not carry the avoid-tolls instruction; verify it fails if the rule is removed
- [x] 4.3 Add a cassette for the new journey holding an empty list of answers, as `toll-free.json` does, naming the journey and the routing quality; verify no answer is recorded in it and that `replay.spent` for the journey is zero

## 5. Verification

- [x] 5.1 Run the unit suite and verify every test passes, including the ones that existed before this change
- [x] 5.2 Run the integration suite and verify every test passes and that no journey's pinned request count changed — a rule that fires where it should not would lower one
- [x] 5.3 Drive Perpignan to Béziers against the running bot and verify one link arrives, immediately, carrying no waypoints, and that the log names the new basis
