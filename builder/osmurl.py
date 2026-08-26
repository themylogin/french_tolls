#!/usr/bin/env python3
"""An openstreetmap.org routing link between two points.

Shared by the throwaway probes so that every row they print can be opened on
the map. The engine is named explicitly: the default engine on the site has
changed before, and a link that silently switches router is a link that stops
agreeing with the number beside it.
"""

import math

BASE = "https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route="

# Distance in kilometres between the two points -> map zoom. Picked so the
# whole route fills the view: a plaza at z17, a 30 km motorway section at z11.
_ZOOM = ((0.5, 17), (1, 16), (2, 15), (5, 14), (10, 13), (25, 12), (60, 11))


def _km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def url(a, b):
    """a and b are (lat, lon). None when either point is unknown."""
    if not a or not b:
        return None
    span = _km(a, b)
    zoom = 10
    for limit, z in _ZOOM:
        if span <= limit:
            zoom = z
            break
    return (f"{BASE}{a[0]:.5f}%2C{a[1]:.5f}%3B{b[0]:.5f}%2C{b[1]:.5f}"
            f"#map={zoom}/{(a[0] + b[0]) / 2:.6f}/{(a[1] + b[1]) / 2:.6f}")


def both(pos, a, b):
    """(there, back) for two node ids, using a node id -> (lat, lon) mapping."""
    return url(pos.get(a), pos.get(b)), url(pos.get(b), pos.get(a))
