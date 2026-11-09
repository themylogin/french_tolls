"""A locked gate is not an escape from a tolled road, even on a through-road.

The router keeps such a gate as a last resort. If the extent graph opened it
like the router does, a region would stop at a fork no driver can take.
"""

import osmium

import build_toll_extent as te


PROFILE = te.Profile(
    "access_tag_blacklist = Set { 'no' }\n"
    "service_access_tag_blacklist = Set { 'private' }\n"
    "barrier_whitelist = Set { 'toll_booth' }\n"
    "barrier_penalties = {\n"
    "  gate = 60,\n"
    "}\n"
)


def write_extract(path):
    header = osmium.io.Header()
    header.set("sorting", "Type_then_ID")
    writer = osmium.SimpleWriter(str(path), 1024 * 1024, header)
    nodes = {
        1: {"barrier": "gate"},
        2: {"barrier": "gate", "locked": "yes"},
        3: {"barrier": "gate"},
        4: {"barrier": "toll_booth", "locked": "yes"},
    }
    for node_id in range(1, 15):
        writer.add_node(osmium.osm.mutable.Node(
            id=node_id, location=(5.0, 45.0 + node_id / 1000),
            tags=nodes.get(node_id, {})))
    writer.add_way(osmium.osm.mutable.Way(
        id=100, nodes=[10, 1, 2, 4, 11], tags={"highway": "residential"}))
    writer.add_way(osmium.osm.mutable.Way(
        id=101, nodes=[12, 3, 13], tags={"highway": "service"}))
    writer.close()


def test_a_locked_gate_on_a_through_road_is_impassable(tmp_path):
    extract = tmp_path / "ways.osm.pbf"
    write_extract(extract)

    blocked, counts = te.impassable_nodes(str(extract), PROFILE, set())

    assert blocked == {2, 3}
    assert counts["of them locked"] == 1
