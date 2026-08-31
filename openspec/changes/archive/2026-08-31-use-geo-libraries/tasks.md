## 1. Dependencies

- [x] 1.1 Add `polyline`, `shapely`, and `pyproj` to the `dependencies` list in
      `pyproject.toml`, each with a comment saying what it replaces. Note that
      `numpy` arrives transitively via `shapely` and is not requested directly.
      Verify the file parses: `python3 -c "import tomllib,pathlib;
      tomllib.loads(pathlib.Path('pyproject.toml').read_text())"`.
- [x] 1.2 Run `make requirements`. Verify the diff adds exactly `polyline`,
      `shapely`, `pyproj`, `numpy`, and `certifi` (a `pyproj` dependency already
      present via `httpx`), and nothing else.
- [x] 1.3 Rebuild: `sudo docker compose --profile test build tests`. Record the
      image size before and after — expected 215 MB → about 331 MB. If it is far
      larger, something pulled a source build instead of a wheel.
- [x] 1.4 Verify `pyproj` needs nothing at run time. In the rebuilt image with
      `--network none`, `PROJ_NETWORK=OFF`, and `warnings.simplefilter("error")`,
      build a WGS84→AEQD transformer and transform a point. It must succeed and
      emit no warning. This is what makes the geometry safe inside a container
      with no egress.

## 2. The projection and the length model

- [x] 2.1 In `french_tolls/geometry.py`, add a module-level
      `Geod(ellps="WGS84")` and a `_projection(lat0, lon0)` helper returning a
      `pyproj.Transformer` for `+proj=aeqd +lat_0=.. +lon_0=.. +datum=WGS84
      +units=m`, wrapped in `functools.lru_cache(maxsize=32)` on the centroid
      rounded to two decimals. Verify a cached call is at least 100× cheaper than
      the first (7.4 ms uncached).
- [x] 2.2 Add `lengths_m(coordinates)` returning the vectorised
      `Geod.inv` geodesic length of each consecutive segment. Verify it returns
      699.996 km for the route in
      `data/google_routes/12670271392-1373899564.json`, against the current
      `refine._cumulative`'s 698.454 km — the new figure is the exact one and the
      old one ran 0.22% short.
- [x] 2.3 Verify the projection is not France-specific: assert that a 1 km
      east-west segment measures within 0.001% at the equator, at 46.5N/2.5E, and
      500 km from each centre. A Lambert-93 implementation would fail the equator
      case by 34%; this assertion is what stops the projection silently
      regressing to a national one.

## 3. `Corridor` replaces `SegmentIndex`

- [x] 3.1 Add `Corridor(coordinates, corridor_m=DEFAULT_CORRIDOR_M)` to
      `geometry.py`, holding the projected `LineString` and a prepared
      `buffer(corridor_m)`. Give it `within(points)` returning a vectorised bool
      array and `distance_m(point)` returning `shapely.distance` to the line.
      Document on the class that it treats projected segments as straight, and
      that this costs 0.16 mm on the corpus's longest real segment (2 884 m) but
      28.5 m on a 37 km one.
- [x] 3.2 Rewrite `overlap()` against `Corridor` and `lengths_m`. Verify against
      the real corpus, not a fixture, on the property that matters: **the
      corridor verdict per segment**, not a share tolerance. Over all 2 450
      journeys, 214 of 74 594 260 segments changed side — 2.9 per million, every
      one of them a midpoint sitting on the 50 m boundary.
      The share tolerance this task first carried (1e-4) was set from a
      40-journey sample and is wrong: the corpus reaches 4.35e-04. That is not a
      disagreement about the corridor. On the worst journey
      (`26692017-26692608`), **zero** of its segments flipped; the whole
      difference is exact geodesics reweighting the lengths, which run +0.12%
      median (+0.009% to +0.26%) longer than the sphere's. Assert flips per
      segment below 1e-5 and shares within 1e-3, and read a rise in the flip
      rate — not in the share difference — as the signal that the corridor
      itself moved.
- [x] 3.3 Verify the prepared buffer is the fast path and stays that way. Time
      `overlap()` over those journeys: expected about 83 ms per journey against
      the current 354 ms. If it comes out near 3 000 ms, the implementation is
      calling `shapely.distance`/`dwithin` against the LineString instead of
      testing points against the prepared buffer.
- [x] 3.4 Delete `SegmentIndex`, `_ring`, `_point_to_segment_m`,
      `_metres_per_degree`, `_segment_length_m`, `CELL_DEGREES`, and
      `EARTH_RADIUS_M` from `geometry.py`. Update `__all__`. Verify
      `grep -n "SegmentIndex\|_ring\|CELL_DEGREES\|EARTH_RADIUS_M"
      french_tolls/geometry.py` returns nothing.

## 4. The polyline codec

- [x] 4.1 Replace the bodies of `decode_polyline` and `encode_polyline` with
      `from polyline import decode as decode_polyline, encode as encode_polyline`.
      Keep both in `__all__`. Move the still-true reasoning — why precision 5,
      and the 972 MB against 614 MB corpus-size argument — into a comment above
      the import.
- [x] 4.2 Verify byte-identity rather than mere function. Encode a 40 000-point
      trace with the old implementation from
      `git show HEAD:french_tolls/geometry.py` and the new one, and assert the
      strings are equal and the decoded lists are equal.
- [x] 4.3 Verify a real stored answer round-trips: decode `ours.polyline` from a
      file under `data/google_routes/`, re-encode, assert the string matches the
      stored one. This is what proves the bought corpus needs no migration.

## 5. `refine.py` and `drive.py`

- [x] 5.1 In `refine.py`, delete `_metres` and `EARTH_RADIUS_M`. Rewrite
      `_cumulative` as a `numpy.cumsum` over `lengths_m`, and `_nearest_index`
      over the **projected** coordinates followed by `argmin`. Verify it returns
      the same index as before on a real route, and is about 5× faster.
      Projected, not `Geod.inv`: the exact form measured 42 ms against 24 ms on
      a 67 468-point route, this runs twice per drift stretch, and picking the
      nearest of thousands of vertices cannot turn on 0.0007% of scale error.
      This is the one place the change trades exactness for speed, and
      `Corridor.nearest_index` says so at the definition.
      **Ask by batch, not by point.** Projecting the route is nearly all of what
      a position query costs, so a per-call helper re-projects twenty thousand
      points once per waypoint and measured *slower* than the loop it replaced
      (24 ms against 21 ms). One `Corridor` reused across a journey's queries is
      what makes it faster: measured 55.7 ms against 442.1 ms for a journey's
      twenty positions, 7.9×, with every index identical. `Corridor` therefore
      builds its buffer lazily, so a caller wanting only positions never pays
      for one.
- [x] 5.2 Rewrite `refine.drift_sections` against `Corridor`: build it once, call
      `within` on all midpoints at once, then loop over the boolean array to
      accumulate sections. Verify it returns the same section count on 20 real
      journeys, and that section lengths agree within 0.3% **except where a
      section's endpoint moved**, which means one segment at the corridor edge
      changed side and is not a length disagreement at all. Measured: 102 of 106
      sections within 0.3%, median 0.155% (the sphere-to-geodesic correction);
      the 4 outliers are one 914.5 m section in four sibling journeys, each with
      a moved `from` endpoint, at 0.91%. Assert the *median* is under 0.3% and
      that every outlier has a moved endpoint — that is the real property, and
      the flat 0.3% bound this task first carried was derived from the length
      correction alone.
- [x] 5.3 Rewrite `refine._measure` to take its total length from `lengths_m`.
      Verify the faithfulness it reports matches the implementation it replaces
      to within 1e-4, on the stored **refined** geometry. Not against the stored
      `before.overlap` as this task first said: that figure describes the
      *unrefined* route, whose geometry `google-route-comparison` deliberately
      does not keep, so it cannot be recomputed from the corpus. Comparing the
      two implementations on geometry that is stored tests the same property and
      is not confounded by the old code having produced the stored number.
      Measured over 20 journeys: max 5.85e-05.
- [x] 5.4 In `drive.py`, delete `_metres` and `EARTH_RADIUS_M` and rewrite
      `midpoint` over a vectorised cumulative length. Verify the node it picks
      moves by **less than 0.05% of the route's length**, rather than requiring
      the identical index. Exact geodesics make a route 0.22% longer, so the
      halfway *distance* moves and the nearest vertex to it shifts by an index
      or two out of thousands. Measured over 20 real journeys: 13 identical, 7
      moved by 1–4 indices, the largest being 185.6 m on an 832.6 km route
      (0.022%). Requiring an identical index would be pinning the sphere's error.
- [x] 5.5 Migrate `evaluation/prototype_reinsert.py` off `SegmentIndex` onto
      `Corridor`. It is not covered by `make test`, so verify by importing it and
      running its drift path over one stored journey — nothing else will catch it.
- [x] 5.6 ~~Verify `french_tolls/equivalence.py` is **unchanged**~~ — **reversed
      by the user after the rest of the change landed.** Leaving it alone would
      have kept one hand-rolled sphere and one `EARTH_RADIUS_M` in the package
      purely because removing them was awkward. Superseded by section 8. The
      original text read:
      `git diff --stat french_tolls/equivalence.py` is empty. Its `thin()` and
      its `_metres` stay as they are by decision; see design.md decision 6.

## 6. Tests

- [x] 6.1 Rewrite `french_tolls/tests/test_geometry.py` against `Corridor`.
      Keep what the file exists to guard — that a bounded corridor predicate and
      an unbounded distance are different questions — and densify `LINE` to
      realistic spacing (segments of hundreds of metres, not 37 km). Verify the
      point-on-the-line case reads 0 m rather than the 29.5 m a 37 km segment
      produces under any projection.
- [x] 6.2 Add one test pinning the sagitta limitation itself: a deliberately
      sparse line whose midpoint reads tens of metres off. It documents the
      trade rather than leaving the next reader to rediscover it.
- [x] 6.3 In `french_tolls/tests/test_refine.py`, replace
      `M_PER_DEGREE = math.pi * refine.EARTH_RADIUS_M / 180` with the geodesic
      value (`Geod.inv(0, 0, 1, 0)`, about 111 319.5 m against the sphere's
      111 194.9 m). The fixtures run along the equator deliberately; leave that
      alone. Verify the module imports and its assertions still hold.
- [x] 6.4 Run `make test`. Verify the suite passes. A test needing an expected
      *number* changed beyond tasks 6.1 and 6.3 is a finding to report before it
      is edited, not a chore.

## 7. Confirm against reality, not fixtures

- [x] 7.1 Re-run the corpus comparison over **all** 2 450 files in
      `data/google_routes/`, not the 40 used while designing. Report the maximum
      share difference and the count of journeys crossing the 0.98 faithfulness
      threshold in either direction.

      Result, over all 2 450 journeys in 150 s (20 processes):

      - max share difference **4.348e-04**, on `26692017-26692608`
      - corridor verdicts: **214 flipped of 74 594 260 segments**, 2.9 per
        million, across 208 journeys
      - route lengths **+0.1197% median** against the sphere (+0.0087% to
        +0.2621%), towards the geodesic truth
      - **one journey crosses the 0.98 line**: `26691407-26691824`,
        0.980006 → 0.979987, a move of −1.9e-05 with **zero** of its corridor
        verdicts changing

      Raised with the user, who accepted it. One journey of 2 450 (0.04%)
      changes population and the report's per-population averages move
      negligibly; the new figure is the more correct one, and the journey was
      never meaningfully above the line — it sat six millionths over it.

      The investigation found the reason nobody expected a crossing:
      `refine.py` claimed 0.98 sits in an empty band between 97.7% and 99.5%.
      **611 journeys are in that band**, twelve within 0.0002 of the line, the
      closest 0.000004 above it. That claim dated from a corpus of a few dozen
      journeys. The comment is corrected in this change (see 7.5).
- [x] 7.5 Correct `refine.py`'s `FIT_THRESHOLD` comment, which asserts an empty
      band that the full corpus contradicts. State what was measured, and that
      anything touching the measure should expect to move a journey across and
      should say which. Not a behaviour change — `FIT_THRESHOLD` stays 0.98.
- [x] 7.2 Verify the evaluation image builds:
      `sudo docker compose --profile evaluation build evaluation`. Do **not** run
      any evaluation target — every request it makes is paid for.
- [x] 7.3 Verify `builder/` is untouched: `git diff --stat builder/` is empty.
- [x] 7.4 Verify the deletion is real: `git diff --stat french_tolls/geometry.py`
      should show a large net removal. The hand-written geometry going away is the
      point of the change, and a diff that only adds means the old paths are still
      there.

## 8. `equivalence.py`, and proving the thinning lost no precision

Added after the rest of the change landed, when the user reversed decision 6 and
asked for `equivalence.py` too. Section 5.6 is superseded.

- [x] 8.1 Add `project(coordinates)` to `geometry.py`: `(lat, lon)` degrees to an
      (n, 2) array of metres in the route-local frame. `Corridor` uses it too, so
      there is one projection helper rather than two. Verify `Corridor` still
      behaves identically — the geometry suite passes unchanged.
- [x] 8.2 Delete `_metres` and `EARTH_RADIUS_M` from `equivalence.py` and thin in
      the projection. Use distance *along* the trace as a bound on distance
      across it — a `searchsorted` jump to the first candidate that could
      qualify — so the walk costs one hop per point kept rather than one per
      point. Verify `grep -rn "6371\|EARTH_RADIUS\|math.asin(math.sqrt"
      french_tolls/` returns nothing: no hand-rolled sphere anywhere in the
      package.
- [x] 8.3 State the cost rather than hide it. Thinning is **slower**: 26.9 ms
      against 20.7 ms on a 35 156-point Google geometry, 34.7 ms the first time a
      journey is seen and a transformer must be built; 3.31 s against 1.24 s over
      210 journeys, while matching stays at ~16 s. Record it in the docstring, so
      nobody reads the skip-ahead as a speedup.
- [x] 8.4 Add unit tests for what thinning in a projection may not cost, on
      synthetic traces so `make test` still needs no graph: no coordinate
      altered, both ends kept **exactly**, every gap ≥ the spacing when
      re-measured against the exact WGS84 geodesic, and the skip-ahead keeping
      exactly what the one-at-a-time walk keeps. Verify `make test` passes: 124
      tests, up from 120.
- [x] 8.5 Prove precision is not lost where it actually matters, against the
      running routers — free, no Google. For each journey compute our own route,
      thin it both ways, match both, and compare the booths and the bill against
      the route's own node ids.

      Result over 210 journeys at 250 m:

      | | sphere | projection |
      |---|---|---|
      | recovers our own booths | 210/210 | **210/210** |
      | recovers our own bill | 210/210 | **210/210** |
      | matched in pieces or failed | 0/210 | **0/210** |
      | journeys whose booths differ between the two | — | **0** |

      Per-journey invariants, each zero on all 210: coordinates altered, ends
      moved, gap violations (both thinnings), and shortcut-vs-naive mismatches.

      **Not one of the 210 traces came out identical** (366 236 points against
      365 793): a 0.2% shift in measured distance compounds through a greedy
      walk. That is why the test asks the matcher what the trace *means* rather
      than comparing traces.
- [x] 8.6 Note for whoever runs the control next: `data/control_match.py` is
      stale against `osrm.py`. It calls `osrm.session()` and `Routers(session,
      ...)`; `Routers` now takes no session and opens its own per request. Not
      fixed here — it is not part of this change — but it will not run as written.
