# -*- coding=utf-8 -*-
"""That a distance is a distance, at any range.

`Corridor` answers two questions that look alike and are not. `within` asks
whether points lie inside a band of tens of metres. `distance_m` asks how far
away the route is, with no bound.

Reusing the first for the second is the trap these tests exist to catch. The
index this class replaced searched only the grid cells beside the point, so it
answered "outside" at *every* radius beyond one cell: a caller binary-searching
it for a distance got its own upper bound handed back as a measurement, every
distant candidate measured the same, and any ordering built on them silently
became the order they happened to be visited in.

`shapely` makes the trap unbuildable -- there is no radius in `distance_m` to be
mistaken for an answer -- so these tests now pin that the property holds rather
than watching for its loss.

Every route here runs along a parallel, so a degree of longitude is a fixed
distance and the expected answers are round numbers. The points are a few
hundred metres apart, as route geometry is; `test_a_sparse_line_sags` says what
happens when they are not, and why.
"""
import pytest
from pyproj import Geod

from ..overlap import Corridor

GEOD = Geod(ellps="WGS84")

# A degree of latitude at 48N, which is what separates the points from the line
# below. Taken from the geodesic rather than from a sphere, because that is what
# the module measures with.
M_PER_DEGREE_LAT = GEOD.inv(2.2, 47.0, 2.2, 48.0)[2]


def along_parallel(lat, lon_from, lon_to, step=0.005):
    """A line at constant latitude, with a vertex every ~370 m.

    Densified on purpose. A parallel is not a straight line in any projection,
    so drawn as a few long chords it sags away from itself -- see
    `test_a_sparse_line_sags`. Real route geometry has a vertex every few
    hundred metres and does not.
    """
    count = int(round((lon_to - lon_from) / step)) + 1
    return [(lat, lon_from + i * step) for i in range(count)]


LINE = along_parallel(48.0, 2.0, 3.0)


def test_distance_beyond_the_corridor_predicate_is_measured():
    """The case that was shipped broken: a point a hundred kilometres away."""
    corridor = Corridor(LINE)
    point = (47.0, 2.2)

    # The predicate says no, which is correct: it is a band of 50 m.
    assert corridor.within([point])[0] == False        # noqa: E712

    # The distance is still a distance. A degree of latitude, since the nearest
    # point on the line is directly north of it.
    assert corridor.distance_m(point) == pytest.approx(M_PER_DEGREE_LAT, rel=1e-4)


def test_distant_points_are_ordered_rather_than_tied():
    """The property whose loss made the placement rule pick by iteration order.

    Three points at different large distances. A saturating implementation
    returns the same value for all three and this fails.
    """
    corridor = Corridor(LINE)
    far = corridor.distance_m((47.0, 2.2))
    middling = corridor.distance_m((47.5, 2.2))
    near = corridor.distance_m((47.9, 2.2))

    assert far > middling > near
    assert far / middling == pytest.approx(2.0, rel=1e-3)


def test_a_point_on_the_route_is_at_no_distance():
    assert Corridor(LINE).distance_m((48.0, 2.25)) == pytest.approx(0.0, abs=0.01)


def test_an_empty_route_has_no_distance():
    assert Corridor([]).distance_m((48.0, 2.0)) is None
    assert Corridor([(48.0, 2.0)]).distance_m((48.0, 2.0)) is None


def test_an_empty_route_holds_nothing():
    assert list(Corridor([]).within([(48.0, 2.0), (48.0, 2.5)])) == [False, False]


def test_the_corridor_predicate_is_unchanged():
    """`overlap` depends on this one, and the rewrite must not have moved it."""
    inside = Corridor(LINE).within([
        (48.0, 2.25),        # on the line
        (48.0004, 2.25),     # ~44 m off
        (48.001, 2.25),      # ~111 m off
    ])
    assert list(inside) == [True, True, False]


def test_within_takes_a_batch_and_keeps_its_order():
    """The signature changed from one point per call to all of them at once.

    A caller reads the answers back positionally, so an implementation that
    returned them in the order `shapely` happened to test would corrupt every
    drift section without failing anything else.
    """
    points = [(48.0, 2.25), (47.0, 2.2), (48.0, 2.75), (47.5, 2.2)]
    assert list(Corridor(LINE).within(points)) == [True, False, True, False]
    assert len(Corridor(LINE).within([])) == 0


def test_a_sparse_line_sags():
    """The one limitation of doing this in a projection, pinned deliberately.

    `Corridor` joins its projected points with straight segments. A parallel is
    an arc, so given only its ends the chord cuts the corner and a point that is
    genuinely *on* the parallel measures tens of metres away from the chord.

    This is not a defect to be fixed -- it is what a projection does, and the
    cost is set by how coarse the input is. Measured over the bought corpus the
    longest real segment is 2 884 m, which sags 0.16 mm against a 50 m corridor.
    A caller feeding this something that is not route geometry should densify it
    first, and this test is here so that the next reader is told so.
    """
    sparse = [(48.0, 2.0), (48.0, 2.5), (48.0, 3.0)]   # 37 km between vertices
    on_the_parallel = (48.0, 2.25)

    assert Corridor(sparse).distance_m(on_the_parallel) > 20.0
    assert Corridor(LINE).distance_m(on_the_parallel) == pytest.approx(0.0, abs=0.01)
