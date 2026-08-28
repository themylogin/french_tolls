# -*- coding=utf-8 -*-
"""Building a booth table by hand, for the accounting tests.

The real inventory keys everything by OSM node id, which is right for the
pipeline and unreadable in a test: a journey written as `[126236, 3788960639]`
says nothing about what it crosses. Here a booth is given a name, the builder
allocates its node id, and a test reads as the journey it describes.

Building the table rather than loading `data/` is also what makes the awkward
states reachable. An exit whose entrance does not price it, a gantry carrying no
amount, a two-way barrier whose neighbours are on neither side -- each is one
line here, and a hunt through 1 295 real booths otherwise.
"""
from ..data import Booth, BoothData

__all__ = [
    "Spec",
    "build_booths",
    "entrance",
    "exit_",
    "gantry",
    "lane",
    "node",
    "passthrough",
    "plain",
    "two_way",
]

# Node ids are allocated from here upwards, one per booth, in the order the
# booths are declared. Well clear of the small integers a test uses for ordinary
# road nodes, so a booth id and a road node id are never confused by eye.
FIRST_BOOTH_NODE = 1000


class Spec:
    """One declared booth, before the builder gives it a node id."""

    def __init__(self, name, **fields):
        self.name = name
        self.fields = fields
        # Set by build_booths for a lane; names the booth it is a lane of.
        self.parent = fields.pop("parent", None)


def entrance(name, *, gare=None, prices=None):
    """A booth that opens a ticket, and the tariffs it charges by exit gare."""
    return Spec(name, type="enter", gare=gare, prices=prices or {})


def exit_(name, *, gare=None):
    """A booth that closes a ticket. Its gare is what the entrance prices."""
    return Spec(name, type="exit", gare=gare)


def passthrough(name, *, price=None, gare=None):
    """A barrier paid where it stands, opening and closing nothing."""
    return Spec(name, type="passthrough", price=price, gare=gare)


def gantry(name, *, price=None, gare=None):
    """A free-flow gantry, charged for the section travelled."""
    return Spec(name, type="gantry", price=price, gare=gare)


def two_way(name, *, gare=None, prices=None, inside=(), outside=()):
    """A barrier driven both ways.

    `inside` and `outside` are the road nodes beside it. A vehicle at an inside
    node holds a ticket, so crossing from there is an exit; a vehicle at an
    outside node circulates freely, so crossing from there is an entrance.
    """
    return Spec(
        name,
        type="bidirectional",
        gare=gare,
        prices=prices or {},
        inside_nodes=frozenset(inside),
        outside_nodes=frozenset(outside),
    )


def plain(name, *, gare=None):
    """A booth in the inventory that the price file does not carry."""
    return Spec(name, type=None, gare=gare)


def lane(name, *, of):
    """A plaza lane, recorded as an alias of another booth.

    It never carries a type or a tariff of its own: a route crossing it is
    charged against the booth it belongs to.
    """
    return Spec(name, type=None, parent=of)


class Booths:
    """A built booth table, and the names that reach into it."""

    def __init__(self, data, ids):
        self.data = data
        self._ids = ids

    def __getitem__(self, name):
        """The node id of a declared booth, so a test can write its name."""
        return self._ids[name]

    def booth(self, name):
        return self.data.booths[self._ids[name]]

    def route(self, *names_or_nodes):
        """A node sequence, taking booth names and bare road node ids alike."""
        return [
            self._ids[n] if isinstance(n, str) else n
            for n in names_or_nodes
        ]


def node(n):
    """An ordinary road node, for readability at a call site."""
    return n


def build_booths(*specs):
    """Turn declared booths into a `BoothData` the accounting can read."""
    ids = {}
    next_id = FIRST_BOOTH_NODE
    for spec in specs:
        ids[spec.name] = next_id
        next_id += 1

    booths = {}
    booth_of_node = {}

    for spec in specs:
        node_id = ids[spec.name]

        if spec.parent is not None:
            # A lane is not a booth of its own. It appears only in the node map,
            # pointing at the booth it belongs to, which is exactly how the real
            # inventory records an alias.
            booth_of_node[node_id] = ids[spec.parent]
            continue

        booths[node_id] = Booth(
            node_id=node_id,
            # Coordinates take no part in accounting; a distinct pair per booth
            # keeps them from comparing equal by accident.
            latlon=(45.0 + node_id / 100000.0, 4.0 + node_id / 100000.0),
            # The operator's name, because that is the one that wins where a
            # booth has both, and a test that writes a name means the name the
            # accounting will use.
            operator_name=spec.name,
            **spec.fields,
        )
        booth_of_node[node_id] = node_id

    return Booths(
        BoothData(booths=booths, booth_of_node=booth_of_node, fingerprint="test"),
        ids,
    )
