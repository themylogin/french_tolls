#!/usr/bin/env python3
"""How much of one route ran along another.

The question this capability exists to answer is whether Google drove the road
this project told it to. Comparing totals cannot answer it: a detour of similar
length reads as agreement, and that is the failure worth catching. So the
measure is geometric — what proportion of Google's route lies within a corridor
of ours.

Weighted by length, not by number of points. Google's geometry is dense through
bends and sparse along a motorway, so counting points would let one roundabout
outweigh fifty kilometres of autoroute.
"""
import math

__all__ = ["decode_polyline", "encode_polyline", "overlap", "SegmentIndex"]

# Half-width of the corridor, in metres. Wide enough to absorb the two networks
# disagreeing about where a carriageway lies, narrow enough that the road beside
# it is outside.
DEFAULT_CORRIDOR_M = 50.0

# Grid cell size in degrees, about 400 m of latitude. A point is tested against
# the segments in its own cell and the eight around it, so the cell wants to be
# comfortably larger than the corridor and small enough that a cell holds few
# segments.
CELL_DEGREES = 0.005

EARTH_RADIUS_M = 6371000.0


def decode_polyline(encoded, precision=5):
    """Google's encoded polyline to a list of (lat, lon).

    Precision 5 is what the Routes API returns for ENCODED_POLYLINE.
    """
    coordinates = []
    index = lat = lon = 0
    factor = 10 ** precision

    while index < len(encoded):
        for is_longitude in (False, True):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if is_longitude:
                lon += delta
            else:
                lat += delta
        coordinates.append((lat / factor, lon / factor))

    return coordinates


def encode_polyline(coordinates, precision=5):
    """A list of (lat, lon) to an encoded polyline.

    Used to store this project's own route geometry in the bought corpus. As a
    JSON array of floats an 11 800-node route is 263 KB; encoded it is 24 KB,
    and across 2 450 journeys that is the difference between a corpus of 972 MB
    and one of 614 MB.

    Nothing that matters is lost. Precision 5 rounds to about a metre, and the
    corridor the geometry is measured against is fifty.
    """
    out = []
    previous = [0, 0]
    factor = 10 ** precision

    for point in coordinates:
        for axis, value in enumerate(point):
            scaled = round(value * factor)
            delta = scaled - previous[axis]
            previous[axis] = scaled
            delta = ~(delta << 1) if delta < 0 else (delta << 1)
            while delta >= 0x20:
                out.append(chr((0x20 | (delta & 0x1F)) + 63))
                delta >>= 5
            out.append(chr(delta + 63))

    return "".join(out)


def _metres_per_degree(latitude):
    """Local scale, so distances can be computed in a flat projection.

    France spans 42 to 51 degrees north, where a degree of longitude is between
    83 and 70 km. Projecting locally rather than using haversine per point is
    what keeps this fast enough for 2 450 routes; over a 50 m corridor the error
    of the flat approximation is millimetres.
    """
    lat_m = math.pi * EARTH_RADIUS_M / 180.0
    lon_m = lat_m * math.cos(math.radians(latitude))
    return lat_m, lon_m


def _point_to_segment_m(point, a, b, scale):
    """Distance in metres from `point` to the segment `a`-`b`."""
    lat_m, lon_m = scale
    px = (point[1] - a[1]) * lon_m
    py = (point[0] - a[0]) * lat_m
    bx = (b[1] - a[1]) * lon_m
    by = (b[0] - a[0]) * lat_m

    length_squared = bx * bx + by * by
    if length_squared == 0.0:
        return math.hypot(px, py)

    t = max(0.0, min(1.0, (px * bx + py * by) / length_squared))
    return math.hypot(px - t * bx, py - t * by)


class SegmentIndex:
    """The segments of a route, in a grid, so a point can find the near ones.

    Without this the measure is every Google point against every one of our
    segments: about 5 000 by 7 000 for a long journey, times 2 450 journeys.
    With it, a point is tested against the handful of segments in its own cell
    and the eight around it.
    """

    def __init__(self, coordinates, cell=CELL_DEGREES):
        self.cell = cell
        self.segments = []
        self.grid = {}

        for a, b in zip(coordinates, coordinates[1:]):
            index = len(self.segments)
            self.segments.append((a, b))
            # A segment is registered in every cell its bounding box touches, so
            # a long segment is found from anywhere along it.
            lo_lat, hi_lat = sorted((a[0], b[0]))
            lo_lon, hi_lon = sorted((a[1], b[1]))
            for cy in range(int(lo_lat / cell), int(hi_lat / cell) + 1):
                for cx in range(int(lo_lon / cell), int(hi_lon / cell) + 1):
                    self.grid.setdefault((cy, cx), []).append(index)

    def within(self, point, corridor_m):
        """Is any segment within `corridor_m` of `point`?

        A predicate rather than a distance, and it stops at the first segment
        that satisfies it. The measure only ever asks whether the point is in
        the corridor, and for the majority of points that are, the first
        candidate answers it. Computing the true minimum instead means testing
        every segment in the neighbourhood every time: measured, 776 000
        point-to-segment tests per journey against 60 000 with the early exit.
        """
        cy = int(point[0] / self.cell)
        cx = int(point[1] / self.cell)
        scale = _metres_per_degree(point[0])

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for index in self.grid.get((cy + dy, cx + dx), ()):
                    a, b = self.segments[index]
                    if _point_to_segment_m(point, a, b, scale) <= corridor_m:
                        return True

        return False

    def distance_m(self, point):
        """Metres from `point` to the nearest segment, or None if none is near.

        Not used by `overlap`, which asks the cheaper question above. Kept
        because it is the natural thing to reach for when looking at why a
        particular journey scored badly.
        """
        cy = int(point[0] / self.cell)
        cx = int(point[1] / self.cell)
        scale = _metres_per_degree(point[0])

        best = None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for index in self.grid.get((cy + dy, cx + dx), ()):
                    a, b = self.segments[index]
                    d = _point_to_segment_m(point, a, b, scale)
                    if best is None or d < best:
                        best = d

        return best


def _segment_length_m(a, b):
    lat_m, lon_m = _metres_per_degree((a[0] + b[0]) / 2)
    return math.hypot((b[1] - a[1]) * lon_m, (b[0] - a[0]) * lat_m)


def overlap(theirs, ours, corridor_m=DEFAULT_CORRIDOR_M):
    """The proportion of `theirs`, by length, running within the corridor of `ours`.

    Both are lists of (lat, lon). Returns a float in [0, 1], and the total length
    of `theirs` in metres, so a caller can weight or report it.

    A piece of `theirs` counts as inside when its midpoint is within the
    corridor. The midpoint rather than either end: a segment straddling the
    point where the two routes part company is half in and half out, and taking
    an end would round it to one or the other by an accident of direction.
    """
    if len(theirs) < 2 or len(ours) < 2:
        return 0.0, 0.0

    index = SegmentIndex(ours)

    inside = 0.0
    total = 0.0
    for a, b in zip(theirs, theirs[1:]):
        length = _segment_length_m(a, b)
        if length == 0.0:
            continue
        total += length
        midpoint = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if index.within(midpoint, corridor_m):
            inside += length

    return (inside / total if total else 0.0), total
