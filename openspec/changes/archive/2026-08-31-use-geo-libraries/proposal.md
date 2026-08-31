## Why

`french_tolls/geometry.py` carries a hand-written Google polyline codec, a
hand-written spherical distance, a hand-written local map projection, a
hand-written point-to-segment distance, and a hand-written grid spatial index
with a ring-walking nearest-neighbour search. That is about 170 lines of
computational geometry maintained here because nothing was reached for instead.
Three more modules carry private copies of the same spherical distance.

All of it is solved work. `shapely` does planar geometry over GEOS, `pyproj`
does projection and exact geodesic distance over PROJ, and `polyline` does the
codec.

Measured against the real corpus of 2 450 bought journeys, the libraries are
also **faster and more accurate** than what they replace:

- `overlap()` goes from 354 ms to 83 ms per journey.
- The unbounded nearest-segment distance goes from 486 ms to 0.27 ms.
- Route lengths become exact WGS84 geodesics, computed 1.9× faster than the
  current sphere approximation, which was running 0.22% short.

## What Changes

- Add `polyline`, `shapely`, and `pyproj` to `pyproj.toml`; recompile
  `requirements.txt`. `numpy` arrives as a `shapely` dependency.
- **Delete** from `french_tolls/geometry.py`: `SegmentIndex`, `_ring`,
  `_point_to_segment_m`, `_metres_per_degree`, `_segment_length_m`,
  `CELL_DEGREES`, `EARTH_RADIUS_M`, and the bodies of `decode_polyline` and
  `encode_polyline`.
- Add a `Corridor` class in their place, holding a route projected into a
  **route-local** metric frame and a prepared 50 m buffer around it.
- **BREAKING (internal):** `SegmentIndex` is removed from `geometry.__all__`.
  Its three consumers — `refine.py`, `evaluation/prototype_reinsert.py`, and
  `french_tolls/tests/test_geometry.py` — move to `Corridor`.
- Replace `refine.py`'s and `drive.py`'s private `_metres` and `EARTH_RADIUS_M`
  with vectorised `pyproj.Geod` calls.
- Replace `equivalence.py`'s `_metres` and `EARTH_RADIUS_M` too, so that **no
  hand-rolled sphere survives anywhere in `french_tolls/`**. Its `optimize()` is
  the one loop that cannot be vectorised — it measures from the last point
  *kept* — so it thins in the projection and skips ahead using distance along
  the trace as a bound. It costs about 10 ms a journey and changes which points
  survive; over 210 journeys matched and priced against their own node ids, both
  the old and the new thinning recover the same booths and the same bill.
- **`haversine` is not adopted.** An earlier draft of this change proposed it;
  `pyproj.Geod` gives the exact geodesic, vectorised, faster.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. The measures keep their definitions: the corridor is still 50 m, overlap
is still length-weighted, thinning is still 250 m from the last point kept.
`google-route-comparison` and `toll-equivalence` state requirements this change
does not alter, and encoded polylines stay byte-identical so the bought corpus
needs no migration.

This change sets `skip_specs: true` in its `.openspec.yaml`.

## Impact

**Dependencies added:**

| package | version | why |
|---|---|---|
| `polyline` | 2.0.4 | the codec; byte-identical to what it replaces |
| `shapely` | 2.1.2 | GEOS: buffers, prepared predicates, point-to-line distance |
| `pyproj` | 3.7.2 | PROJ: the route-local projection, and exact geodesic lengths |
| `numpy` | 2.4.6 | transitive, via `shapely` |

**Image size: 215 MB → 331 MB (+54%).** `numpy` is 45 MB, `pyproj` 20 MB (it
bundles PROJ's database), `shapely` 6.7 MB. This is the real price of the change
and it is not small. Verified that `pyproj` needs no network and no grid files at
run time: with `--network none` the transformation resolves as a null datum shift
and emits no warning.

**Code:** `french_tolls/geometry.py` (largely rewritten), `french_tolls/refine.py`,
`french_tolls/drive.py`, `french_tolls/equivalence.py`,
`evaluation/prototype_reinsert.py`, `pyproject.toml`, `requirements.txt`.

**Tests:** `french_tolls/tests/test_geometry.py` is rewritten against `Corridor`.
`french_tolls/tests/test_refine.py` derives `M_PER_DEGREE` from
`refine.EARTH_RADIUS_M`, which this change deletes.
`french_tolls/tests/test_equivalence.py` gains four tests for what thinning in a
projection may not cost: no coordinate altered, both ends kept exactly, every gap
honoured against the exact geodesic, and the skip-ahead agreeing with the walk it
shortcuts.

**`builder/` is out of scope.** Its Dockerfile installs only Debian packages so
its build needs no pip index. Six more copies of the spherical formula and a
second polyline codec live there; that is a separate change.

**Measured:**

| operation | before | after |
|---|---|---|
| `overlap()` per journey | 347 ms | 70 ms |
| nearest distance to a route, 300 km away | 486 ms | 0.27 ms |
| a journey's 20 position queries | 442 ms | 56 ms |
| `_cumulative` over 35 156 points | 21.2 ms | 11.5 ms |
| thinning a Google geometry | 20.7 ms | 26.9 ms |

Over **all 2 450** stored journeys: overlap shares move by at most 4.35e-04, and
**214 of 74 594 260 corridor verdicts change** — 2.9 per million, every one a
midpoint sitting on the 50 m boundary. Route lengths move +0.12% median,
**towards** the geodesic truth rather than away from it. One journey crosses the
0.98 faithfulness line, with none of its corridor verdicts changing; see
tasks.md 7.1.

Over 210 journeys matched and priced against their own node ids, the new
thinning recovers our own booths and our own bill on **210/210**, as the old one
did, with **0** journeys where the two disagree about booths.
