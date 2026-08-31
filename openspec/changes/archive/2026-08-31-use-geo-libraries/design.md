## Context

See proposal.md — Why.

Four facts about the current code shape the approach.

**There are two different distance problems here.** Point-to-point great-circle
distance is what `refine.py`, `drive.py` and `equivalence.py` compute. Distance
from a point to a *polyline* is what the corridor measure asks — 26 666 times per
`overlap()` — and it is why `geometry.py` grew a local flat projection, a
point-to-segment routine, a grid index and a ring-walking search. The two
problems want different libraries: `pyproj` for the first, `shapely` for the
second.

**`shapely` is planar.** GEOS knows nothing about the earth. Every operation
needs coordinates already in metres, so the choice of projection is the load-
bearing decision of this design, not a detail.

**`SegmentIndex` has two methods that are not interchangeable**, and
`test_geometry.py` exists because shipping them as though they were was a real
bug: `within` searches only the adjacent cells, so it answers "no" at *every*
radius beyond about one cell, and a caller binary-searching it for a distance
gets its own upper bound back. Whatever replaces it must keep those two
questions distinct or must make the distinction unnecessary.

**The test fixtures are synthetic and extreme.** `test_geometry.py` uses a line
along a parallel with 0.5°-long segments — 37 km each. `test_refine.py` builds
routes **along the equator**, because "a metre of longitude at the equator is a
metre of route" makes its expected values round numbers. Neither resembles route
geometry, and both interact badly with projection.

## Goals / Non-Goals

**Goals:**

- Delete the hand-written computational geometry rather than maintain it.
- Keep encoded polylines byte-identical, so the 2 450-journey corpus needs no
  migration.
- No hidden geographic assumption in the geometry module.
- Verify against the real corpus, not only against synthetic fixtures.

**Non-Goals:**

- `equivalence.py`. See decision 6.
- `builder/`. See proposal.md — Impact.
- Changing any measure's definition. The corridor stays 50 m, overlap stays
  length-weighted.
- Optimising the image size. The change makes it substantially bigger and says so.

## Decisions

### 1. A route-local projection, not a national one

The metric frame is an azimuthal equidistant projection centred on the route's
own centroid, built per `Corridor`:

```
+proj=aeqd +lat_0=<centroid lat> +lon_0=<centroid lon> +datum=WGS84 +units=m
```

*Alternative rejected — Lambert-93 (EPSG:2154).* This was the first choice: it is
the official French projection, metre units, designed for this country. It is
wrong for two reasons.

It writes "France" into `geometry.py` as an invisible assumption. Measured scale
error against the geodesic: Paris −0.0105%, Corsica +0.1218%, Brussels +0.1984%,
Barcelona +0.2935%. It degrades smoothly with distance and never announces that
it has, so a route extending past the border would be measured slightly wrong
with nothing to show for it.

And it is not merely inaccurate off-domain, it is nonsense. At the equator —
where `test_refine.py` builds every one of its fixtures — Lambert-93 turns one
degree of longitude into **148 858 m against a true 111 320 m, a 34% error**. A
geometry module that silently returns numbers like that outside one country is
worse than the sphere it replaced.

The route-local projection has neither problem. Measured scale error for a 1 km
segment at increasing distance from the centre:

| distance from centre | centred in France | centred at the equator |
|---|---|---|
| 100 km | +0.0000% | +0.0000% |
| 300 km | +0.0001% | +0.0000% |
| 500 km | +0.0007% | −0.0000% |
| 700 km | +0.0026% | −0.0000% |

It is more accurate than Lambert-93 everywhere, including inside France, and it
is correct anywhere on earth. On the real corpus the two produce overlap shares
that agree exactly; the choice costs 83 ms per journey against 60 ms, because
building the transformer costs 7.4 ms.

*Cost mitigation.* Cache transformers on the centroid rounded to two decimals.
`refine.py` builds a corridor more than once per journey, and a cache turns the
second and later ones free. Do not cache unboundedly — an `lru_cache(maxsize=32)`
is enough, since a process works on one journey at a time.

### 2. A prepared buffer, not `shapely.distance`

The obvious call is `shapely.dwithin(points, line, 50)`. It is **8.6× slower than
the code it would replace.** GEOS scans the linestring's segments linearly per
point, and our routes have thousands of them.

Measured over 40 real journeys, mean per journey:

| approach | time | agrees with |
|---|---|---|
| current `SegmentIndex` | 354 ms | — |
| `shapely.distance(points, line) <= 50` | 3 267 ms | — |
| `shapely.dwithin(points, line, 50)` | 2 931 ms | — |
| `STRtree` of segments, `dwithin` predicate | 55 ms | exactly the above |
| **prepared buffer + `intersects`** | **37 ms** | exactly the above |

So the corridor is built once as a polygon and prepared:

```python
band = LineString(projected_ours).buffer(corridor_m)
shapely.prepare(band)
inside = shapely.intersects(band, shapely.points(midpoints))   # vectorised
```

`shapely.prepare` builds GEOS's internal index once, and the point-in-polygon
test is then logarithmic. Round joins and caps are the default, which is exactly
the corridor's meaning — every point within `corridor_m` of the line.

*On the buffer's polygonal approximation of round joins:* it does not matter.
`quad_segs=8` (the default) and `quad_segs=32` gave **identical** shares on all
60 journeys tested, and both agreed exactly with the `STRtree` `dwithin` result,
which uses no approximation at all. The default stands.

### 3. `pyproj.Geod` for every length, not the projected plane

Lengths do not go through the projection. `Geod(ellps="WGS84").inv` vectorised
over whole coordinate arrays gives the exact WGS84 geodesic in one call:

| computing a 35 156-point route's length | time | result |
|---|---|---|
| current haversine loop | 21.24 ms | 698.454 km (−0.2203%) |
| projected plane | 3.66 ms | 699.537 km (−0.0657%) |
| **`Geod.inv` vectorised** | **11.45 ms** | **699.996 km (exact)** |

The projected plane is faster still, but there is no reason to accept 0.066% of
error for 8 ms on an operation this size when the exact answer is already faster
than what runs today. Keeping lengths off the projection also means the only
thing the projection choice can affect is the corridor predicate.

This applies to `refine._cumulative`, `refine._nearest_index`, `refine._measure`,
`drive.midpoint`, and the segment lengths inside `overlap`.

### 4. `Corridor` replaces `SegmentIndex`, and the trap disappears

```python
class Corridor:
    def __init__(self, coordinates, corridor_m=DEFAULT_CORRIDOR_M): ...
    def within(self, points):     # -> numpy bool array, vectorised
    def distance_m(self, point):  # -> float, exact, unbounded
```

`within` takes *all* the midpoints at once rather than one per call, which is
what makes the prepared buffer worth building. Callers loop over the returned
array instead of calling into the index.

The distinction `test_geometry.py` guards stops being a trap. `distance_m` is
now `shapely.distance(point, line)` — an exact unbounded distance with no radius,
no rings, and no upper bound to be mistaken for a measurement. Measured on a
point 300 km from a route: 486 ms and ring-limited before, 0.27 ms and exact now.
The 60 lines of `_ring` and bounds-walking are deleted.

The corridor width moves from a `within(point, corridor_m)` argument to a
constructor argument, because the buffer must be built at one width. All three
call sites already construct per call with a fixed width.

### 5. `polyline` for the codec

`polyline` 2.0.4 has the same signature, the same `(lat, lon)` order and the same
default precision as the code it replaces. Verified on a 40 000-point trace:
`encode` produced a **byte-identical** string, all 141 008 characters, and
`decode` an element-identical list, maximum difference 0.0.

The two names stay exported from `geometry.py` as re-exports, so the nine call
sites across `refine.py`, `evaluation/` and `data/` are untouched and
`geometry.py` remains the one place that decides the project's polyline
precision.

### 6. `equivalence.py` moves too, and the matcher is what says it is safe

This decision was first taken the other way: leave `optimize()` (then `thin()`)
alone, because it is the one loop here that cannot be vectorised — it measures
from the last point *kept* — and moving it is slower and changes which points
survive. The user reversed it, and the reversal is right: the alternative was
one hand-rolled sphere and one `EARTH_RADIUS_M` surviving in the package purely
because it was awkward to remove, which is how a second earth model gets kept.

**It costs, and the cost is stated rather than hidden.** Projecting 35 000
points is more work than measuring 35 000 spherical distances: 26.9 ms against
20.7 ms on a Google geometry, 34.7 ms cold. Over 210 journeys, thinning went
from 1.24 s to 3.31 s while matching stayed at ~16 s. Ten milliseconds a journey
against an ~80 ms match request and a paid Google request is not a price worth
keeping a second distance model to avoid.

**The walk skips ahead.** Distance along the trace bounds distance across it, so
any point still within `spacing_m` of the last kept one *by path* cannot be
`spacing_m` away in a straight line. A `searchsorted` over the cumulative length
jumps to the first candidate that could qualify, leaving one hop per point kept
rather than one per point. It is an optimisation, not a different rule, and a
test pins it against the one-at-a-time walk.

**The trace does change, and that is what had to be tested.** A 0.2% shift in
measured distance compounds through a greedy walk: not one of 210 traces came
out identical, 366 236 points against 365 793. So the test is not "is the trace
the same" — it is "does the answer change", asked of the matcher:

| over 210 journeys, at 250 m | sphere | projection |
|---|---|---|
| recovers our own booths | 210/210 | **210/210** |
| recovers our own bill | 210/210 | **210/210** |
| matched in pieces or failed | 0/210 | **0/210** |
| journeys whose booths differ between the two | — | **0** |

Four invariants are asserted per journey and each was zero across all 210: no
coordinate altered, neither endpoint moved, every gap ≥ the spacing when
re-measured against the exact WGS84 geodesic, and the shortcut agreeing exactly
with the naive walk. The unit suite pins all four on synthetic traces as well,
because the router-backed run needs a 30 GB graph and `make test` must not.

### 7. The synthetic fixtures must change, and the reason is not a defect

`test_geometry.py`'s line runs along a parallel with 37 km segments. A parallel
is not a straight line in any projection, so drawn as two straight chords its
true midpoint sits **28.5 m off the chord** — and the test asserting a point on
the line measures 0.0 m instead reads 29.5 m.

This is the projection working correctly on a fixture that is not route geometry.
The sagitta of a chord against the true path:

| segment length | midpoint sits off the chord by |
|---|---|
| 250 m | 0.001 m |
| 1 km | 0.021 m |
| 5 km | 0.520 m |
| 37 km | 28.468 m |

Measured over 400 real geometries from the corpus, the longest single segment is
**2 884 m** (p99 2 779 m, median 708 m), giving 0.16 mm of sagitta against a 50 m
corridor. The fixture is therefore densified to realistic spacing, and the
limitation is documented on `Corridor`.

## Risks / Trade-offs

**The image grows 215 MB → 331 MB (+54%)** → Accepted, and it is the largest
cost of this change. `numpy` is 45 MB of it and arrives only because `shapely`
needs it. Nothing in this design uses `numpy` for its own sake beyond passing
arrays to the two libraries.

**Overlap shares move by up to 6.3e-05** → From the projection model, not from
the buffer (which agreed exactly with the unapproximated `dwithin`). Well below
any reported precision; `report.py` prints shares to four decimals and the
faithfulness threshold is 0.98. No journey in the 60 tested crossed it.

**`distance_m` answers change by up to 0.75% at long range** → It is now correct
and was not. The old answer used a flat projection at the query point's latitude,
which degrades with distance; the new one is exact. Only `test_geometry.py`
consumes it, so no production ranking moves.

**A route longer than ~1 400 km would push the projection's edges past 700 km
from centre** → At 700 km the error is 0.0026%, i.e. 1.3 mm on a 50 m corridor,
and it grows as the square. Mainland France is under 1 100 km end to end.
Mitigation: none needed now, but the limit is a property of the centroid, so a
future continental route degrades gracefully rather than suddenly.

**GEOS and PROJ are compiled dependencies** → Both ship manylinux wheels, so the
Debian image installs them from the index with no build toolchain, exactly as it
installs everything else. Verified in the image this project runs.

**`pyproj` might need network or grid files at run time** → Verified it does not.
With `--network none`, `PROJ_NETWORK=OFF`, and warnings promoted to errors, the
WGS84→AEQD transformation resolves as a null datum shift, transforms correctly,
and emits nothing.

**`evaluation/prototype_reinsert.py` imports `SegmentIndex`** → It is a prototype
and not part of `make test`, so nothing will catch its breakage. It must be
migrated in the same change rather than left to rot.

## Migration Plan

No data migration. Encoded polylines are byte-identical and every file under
`data/google_routes/` stays valid and correctly interpreted.

Ordinary deployment: edit `pyproject.toml`, run `make requirements`, rebuild.
The application image and the evaluation image both take the packages from the
recompiled file with no Dockerfile edit. `builder/` is untouched and keeps its
no-pip-index property.

Rollback is `git revert` plus a rebuild. Nothing written while the change is live
is unreadable by the code before it.

## Open Questions

None. The `thin()` question was resolved by the user in favour of leaving
`equivalence.py` alone; see decision 6.
