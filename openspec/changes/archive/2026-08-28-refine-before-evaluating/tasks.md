## 1. The evaluation refines for itself

- [x] 1.1 Import `drift_sections` and `waypoints_for` from `french_tolls.refine` into the evaluation rather than reimplementing them; verify the imported functions reproduce the prototype's Bayeux–Apt result — 17 stretches, 258.6 km, waypoints at 48.364290,0.566290 and 46.341340,3.381882
- [x] 1.2 Confirm the evaluation makes its own Google requests and never calls the application's `/api/refine`; verify by searching the evaluation for the endpoint and by running a fetch with the application stopped

## 2. Two phases per journey

- [x] 2.1 Ask Google through the optimal route's own waypoints, measure the drift, and place the refined waypoints; verify the refined set matches what the application produces for the same journey
- [x] 2.2 Ask Google again through the refined waypoints and store that response whole; verify every refined waypoint lies within a few metres of the stored route
- [x] 2.3 Keep the unrefined route's measurements — overlap, drift, distance, duration — and discard its geometry; verify a stored file carries both sets of numbers and one geometry, and record the resulting median file size
- [x] 2.4 Skip the second request where the first found nothing to correct; verify such a journey costs one request and stores the route already obtained
- [x] 2.5 Store each phase as it completes; verify a run interrupted between the two resumes rather than re-buying, and that a journey holding only an unrefined answer costs one request rather than two
- [x] 2.6 Confirm a journey costs at most two Google requests ever; verify by fetching one, re-running, and reading the request count

## 3. The guard counts requests

- [x] 3.1 Remove `USD_PER_1000_ADVANCED` and the "Advanced tier" comment; verify no dollar figure is printed anywhere by the fetch
- [x] 3.2 Report requests and the share of the monthly free cap a run would consume, and what it leaves; verify the wording for a full sweep — 4 900 requests against a cap of 10 000
- [x] 3.3 Confirm the guard still refuses without `--yes`, refuses with no key naming the variable, and honours `--limit` and `--longest-independent`; verify all four without issuing a request

## 4. The report

- [x] 4.1 Analyse the refined route rather than the unrefined one throughout sections 1 and 2; verify Bayeux–Apt now reports its refined overlap rather than 74.4%
- [x] 4.2 Split section 3 into faithful and diverging populations, each with count, mean and spread, and print the threshold; verify both figures and both counts appear
- [x] 4.3 Print the mixed average alongside, labelled as mixing the two; verify it is present and named as such
- [x] 4.4 Make the threshold settable, defaulting to 0.98; verify 0.95 and 0.99 produce the splits the data implies
- [x] 4.5 Report, for each diverging journey, whether its waypoint budget could have covered its drift; verify Hendaye–Wissembourg is reported as budget-limited
- [x] 4.6 Show the before and after faithfulness together for each journey; verify a journey's improvement is readable without consulting an earlier run
- [x] 4.7 Confirm the report still makes no Google request; verify by running it with the network unavailable

## 5. Bringing the corpus up to date

- [x] 5.1 Top up the twenty stored journeys with their second phase — 20 requests; verify each gains a refined route and keeps its unrefined measurements
- [x] 5.2 Confirm the corpus size projection for a full sweep from the new median file size; verify against the 660 MB the single-phase corpus projected to

## 6. Verification

- [x] 6.1 Run the report and record what it says. Over 29 refined journeys (1 excluded as optimal==fast) at a 0.98 threshold: **FAITHFUL n=15, x0.9303, sd 0.0200** — **DIVERGING n=14, x0.9364, sd 0.0252** — mixed x0.9333. The predicted 15/5 split did not hold: it is 15/14, because 10 further journeys were bought after the prediction and because the model assumed a waypoint removes its stretch's drift entirely. Only 2 of the 14 divergent journeys are budget-limited; the other 12 had budget to spare, so the ceiling is **not** the main limit — placement is
- [x] 6.2 **The prediction was wrong, and in the opposite direction.** The pre-refinement corpus showed the ratio rising with faithfulness (x0.9087 below 80% overlap, x0.9447 above 90%), so the faithful population was expected to sit *above* the mixed figure. Measured after refining, the faithful population is x0.9303 and the diverging one x0.9364 — the faithful group is **lower**, not higher. The two are also much closer than the pre-refinement spread suggested (0.006 apart, against 0.036). Stated as measured; no explanation is offered here because none was tested
- [x] 6.3 Confirm `make all`, `make test` and the application are untouched; verify the unit suite passes and a dry run mentions none of this
