## 1. Shared geometry

- [x] 1.1 Move `evaluation/geometry.py` to `french_tolls/geometry.py`; verify the corridor measure, the grid index, and the codec still pass the constructed cases — identical 1.0, parallel-road detour 0.659, 500 dense off-route points 0.977
- [x] 1.2 Put the `french_tolls` package on the evaluation image's path and repoint its imports; verify `report.py` prints the same overlap figures as before the move — median 87.7% over the ten long independent journeys
- [x] 1.3 Confirm nothing keeps a second copy of the corridor measure; verify by searching both trees for a duplicate implementation

## 2. One database

- [x] 2.1 Write `french_tolls/db.py` opening `/cache/database.db` with WAL and a busy timeout, creating the four tables if absent; verify a fresh container creates the file and all four tables
- [x] 2.2 Rename an existing `autocomplete.sqlite` to `database.db` on first open, keeping its rows; verify the autocomplete cache survives the rename and a second start is a no-op
- [x] 2.3 Point `french_tolls/autocomplete.py` at the shared database; verify a query is cached and read back, and that `AUTOCOMPLETE_CACHE` no longer names a separate file
- [x] 2.4 Move route answers from the per-fingerprint JSON files into the `routes` table, keyed by fingerprint and the two coordinates; verify a journey is answered, stored, and read back, and that a changed fingerprint misses
- [x] 2.5 Delete the file-cache code and the `/cache/<fingerprint>/` directories; verify no code writes an answer to a file and the service still answers from a cold cache

## 3. The monthly budget

- [x] 3.1 Implement the `google_requests` counter keyed on `YYYY-MM`, incremented atomically; verify two concurrent reservations raise the count by two, and that a new month starts from zero with nothing reset by hand
- [x] 3.2 Commit the increment before the HTTP call is made; verify a request that fails still leaves the month's count raised
- [x] 3.3 Read the ceiling from `GOOGLE_DIRECTIONS_MAX_REQUEST_PER_MONTH`, treating unset or zero as "never refine"; verify each of the three settings

## 4. Refinement

- [x] 4.1 Add the Routes API client to the application — `TRAFFIC_UNAWARE`, no departure time, no alternatives, no reordering, tolls not avoided, requesting only the fields used; verify the built body against `google-route-refinement` before any request is issued
- [x] 4.2 Port the drift-to-waypoint step from `evaluation/prototype_reinsert.py`; verify against the stored Bayeux–Apt answer that it still yields 48.364290,0.566290 and 46.341340,3.381880
- [x] 4.3 Compute the waypoint budget as nine less what the route needs, and skip refinement at zero; verify a nine-waypoint journey makes no Google request and says the waypoint budget was full
- [x] 4.4 Merge new waypoints into the existing list in driven order; verify a waypoint falling between the third and fourth existing ones lands in that position
- [x] 4.5 Store the refinement against the journey and fingerprint, and reuse it; verify a second request makes no Google call and leaves the month's count unchanged
- [x] 4.6 Report which budget stopped a refinement, and leave the journey answerable either way; verify the two exhausted cases and the Google-already-agreed case

## 5. The endpoints and the links

- [x] 5.1 Add `POST /api/refine` returning the refined link, the refined waypoints, Google's geometry, and the budget outcome; verify it against a real journey
- [x] 5.2 Add `GET /go/{form}` for the three forms, redirecting to Google Maps; verify each redirects with the refined waypoints and its own origin
- [x] 5.3 Make the redirect work when refinement did not happen; verify it still redirects, to the unrefined link, with a budget exhausted
- [x] 5.4 Change the three link keys to address this service, and add the direct Google link under its own key; verify `french_tolls/bot.py` is unmodified and its links now point at us
- [x] 5.5 Confirm the bot's three links resolve end to end; verify each redirects to a Google Maps route

## 6. The page

- [x] 6.1 Make the icon beside each link a control — pointer cursor, a title saying what it does — that calls `/api/refine` and draws the returned geometry; verify a calculated journey issues no refinement until the control is used
- [x] 6.2 Draw Google's route in orange above the optimal route and below the fast one, thinner than both, with the sent waypoints marked; verify the stacking and that a new journey clears it
- [x] 6.3 Say why when nothing could be refined; verify the two exhausted budgets each produce a message rather than silence
- [x] 6.4 Remove `french_tolls/google_debug.py`, `GOOGLE_DIRECTIONS_DEBUG` from the compose file and `.env.example`, and the flag's use in the page; verify no reference to it remains anywhere in the tree

## 7. Verification

- [x] 7.1 Refine Bayeux–Apt for real and measure the result; verify against the 74.4% already recorded and report whether the two inserted waypoints improved it
- [x] 7.2 Confirm one journey costs at most one Google request; verify by asking for it from the bot's link, the page's control, and the API, and reading the month's count
- [x] 7.3 Confirm the ceiling holds; verify with the ceiling set to one that a second distinct journey is answered unrefined
- [x] 7.4 Confirm the service starts and answers with no Google key configured; verify every journey comes back unrefined
- [x] 7.5 Run the unit suite and the evaluation report; verify 47 tests pass and the report's figures are unchanged by the move
- [x] 7.6 Confirm `make all` and `make test` are untouched by any of this; verify by dry run
