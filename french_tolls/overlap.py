#!/usr/bin/env python3
"""How much of one route ran along another.
"""

import numpy as np
import shapely
from pyproj import CRS, Geod, Transformer
from shapely import LineString, Point

from polyline import decode as decode_polyline, encode as encode_polyline

__all__ = [
    "Corridor", "DEFAULT_CORRIDOR_M", "decode_polyline", "encode_polyline",
    "lengths_m", "overlap", "project", "total_length_m",
]

# Half-width of the corridor, in metres. Wide enough to absorb the two networks
# disagreeing about where a carriageway lies, narrow enough that the road beside
# it is outside.
DEFAULT_CORRIDOR_M = 50.0

GEOD = Geod(ellps="WGS84")


def _projection(lat0, lon0):
    """A tool to convert (lat, lon) coordinates to (x, y) coordinates in metres.

    Works well only within a 500 km radius of the point `(lat0, lon0)`, which is
    good enough for our purposes.
    """
    return Transformer.from_crs(
        "EPSG:4326",
        CRS.from_proj4(
            f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m"
        ),
        always_xy=True,
    )


def project(coordinates, projection=None):
    """`(lat, lon)` pairs to an (n, 2) array of metres.
    """
    points = np.asarray(coordinates, dtype=float)
    if projection is None:
        projection = _projection(float(points[:, 0].mean()),
                                 float(points[:, 1].mean()))
    x, y = projection.transform(points[:, 1], points[:, 0])
    return np.column_stack([x, y])


def lengths_m(coordinates):
    """The geodesic length of each segment of `coordinates`, in metres.
    """
    a = np.asarray(coordinates, dtype=float)
    if len(a) < 2:
        return np.zeros(0)
    return GEOD.inv(a[:-1, 1], a[:-1, 0], a[1:, 1], a[1:, 0])[2]


def total_length_m(coordinates):
    """The geodesic length of a whole route, in metres."""
    return float(lengths_m(coordinates).sum())


class Corridor:
    """A route, and the band of `corridor_m` metres around it.
    """

    def __init__(self, coordinates, corridor_m=DEFAULT_CORRIDOR_M):
        self.corridor_m = corridor_m
        points = np.asarray(coordinates, dtype=float)
        if len(points) < 2:
            self.projection = None
            self.points = None
            self.line = None
            self._band = None
            return

        self.projection = _projection(float(points[:, 0].mean()),
                                      float(points[:, 1].mean()))
        self.points = project(points, self.projection)
        self.line = LineString(self.points)
        self._band = None

    @property
    def band(self):
        """The buffered corridor, built the first time it is asked for.
        """
        if self._band is None and self.line is not None:
            self._band = self.line.buffer(self.corridor_m)
            shapely.prepare(self._band)
        return self._band

    def nearest_index(self, target):
        """The index of the route vertex closest to `target`.
        """
        if self.points is None:
            return 0
        tx, ty = project([target], self.projection)[0]
        return int(np.argmin(np.hypot(self.points[:, 0] - tx,
                                      self.points[:, 1] - ty)))

    def within(self, coordinates):
        """Which of `coordinates` lie inside the corridor, as a bool array.
        """
        if self.band is None:
            return np.zeros(len(coordinates), dtype=bool)
        if len(coordinates) == 0:
            return np.zeros(0, dtype=bool)
        projected = project(coordinates, self.projection)
        return shapely.intersects(self.band, shapely.points(projected))

    def distance_m(self, point):
        """Metres from `point` to the nearest part of the route.

        None when the route has fewer than two points, so there is no line.
        """
        if self.line is None:
            return None
        return float(self.line.distance(Point(project([point], self.projection)[0])))


def overlap(theirs, ours, corridor_m=DEFAULT_CORRIDOR_M):
    """The proportion of `theirs`, by length, running within the corridor of `ours`.

    Both are lists of (lat, lon). Returns a float in [0, 1], and the total length
    of `theirs` in metres, so a caller can weight or report it.

    A piece of `theirs` counts as inside when its midpoint is within the
    corridor.
    """
    if len(theirs) < 2 or len(ours) < 2:
        return 0.0, 0.0

    points = np.asarray(theirs, dtype=float)
    lengths = lengths_m(points)
    real = lengths > 0.0
    total = float(lengths[real].sum())
    if total == 0.0:
        return 0.0, 0.0

    midpoints = ((points[:-1] + points[1:]) / 2.0)[real]
    inside = Corridor(ours, corridor_m).within(midpoints)

    return float(lengths[real][inside].sum() / total), total
