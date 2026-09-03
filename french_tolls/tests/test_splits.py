# -*- coding=utf-8 -*-
"""Choosing where to break a ticket, and refusing to when it is not worth it.

The advice file says where stopping is cheaper and what it costs in time. It
carries no money at all, so everything about euros here is derived from the
price file -- which is the point: there is one place a tariff is written down,
and a stale second copy cannot disagree with it.
"""
import pytest

from .. import splits
from ..splits import Advice, Candidate, Stop
from ..tolls import account, closed_sections, fare
from .booths import build_booths, entrance, exit_, gantry, node, two_way


def candidate(exit_node, enter_node, extra_time):
    return Candidate(stops=(Stop(exit_node=exit_node, enter_node=enter_node),),
                     extra_time=extra_time)


def advice(**by_pair):
    return Advice(by_pair={tuple(k.split("__")): v for k, v in by_pair.items()})


# --------------------------------------------------------------------------
# Which sections a route buys
# --------------------------------------------------------------------------

def test_a_route_reports_the_tickets_it_buys():
    b = build_booths(
        entrance("A", gare="0001", prices={"0002": 10.0}),
        exit_("B", gare="0002"),
    )
    sections = closed_sections(b.data, b.route("A", node(1), "B"))
    assert [(x.label, z.label) for x, z in sections] == [("A", "B")]


def test_an_entrance_no_exit_closes_is_not_a_section():
    b = build_booths(entrance("A", gare="0001", prices={"0002": 10.0}))
    assert closed_sections(b.data, b.route("A", node(1))) == []


def test_an_exit_with_no_entrance_is_not_a_section():
    b = build_booths(exit_("B", gare="0002"))
    assert closed_sections(b.data, b.route(node(1), "B")) == []


def test_two_sections_are_reported_separately():
    b = build_booths(
        entrance("A", gare="0001", prices={"0002": 10.0}),
        exit_("B", gare="0002"),
        entrance("C", gare="0003", prices={"0004": 5.0}),
        exit_("D", gare="0004"),
    )
    sections = closed_sections(
        b.data, b.route("A", node(1), "B", node(2), "C", node(3), "D"))
    assert [(x.label, z.label) for x, z in sections] == [("A", "B"), ("C", "D")]


def test_a_two_way_barrier_is_read_by_the_side_it_is_crossed_from():
    b = build_booths(
        two_way("T", gare="0001", prices={"0002": 8.0}, inside=(2,), outside=(1,)),
        exit_("B", gare="0002"),
    )
    sections = closed_sections(b.data, b.route(node(1), "T", node(2), "B"))
    assert [(x.label, z.label) for x, z in sections] == [("T", "B")]


def test_a_section_opened_at_a_gantry_is_reported():
    """Both walks must report the same sections.

    `account` charges a section that starts at a gantry. If this walk missed
    that section, the advice would offer a split against a fare that nobody is
    charged, or skip a real one.
    """
    b = build_booths(
        gantry("CHAMBERY NORD", gare="03008", prices={"03012": 5.60}),
        exit_("ANNECY CENTRE", gare="03012"),
    )
    sections = closed_sections(b.data, b.route("CHAMBERY NORD", node(1), "ANNECY CENTRE"))
    assert [(x.label, z.label) for x, z in sections] == [
        ("CHAMBERY NORD", "ANNECY CENTRE")]


def test_every_reported_section_has_a_fare():
    """`closed_sections` and `fare` must agree on every section.

    They are read together: `route` takes each reported section and asks what it
    costs, then looks for a cheaper split. A section it reports but cannot price
    is skipped in silence, and the split for it is never offered -- even though
    `account` charges the driver for it.

    The gantry here is the case that failed. Its own map does not price the
    exit; the booth beside it, of the same gare, does.
    """
    b = build_booths(
        gantry("CHAMBERY NORD gantry", gare="03008", prices={"03011": 3.60}),
        entrance("CHAMBERY NORD", gare="03008", prices={"03012": 5.60}),
        exit_("ANNECY CENTRE", gare="03012"),
    )
    route = b.route("CHAMBERY NORD gantry", node(1), "ANNECY CENTRE")

    sections = closed_sections(b.data, route)
    assert [(x.label, z.label) for x, z in sections] == [
        ("CHAMBERY NORD gantry", "ANNECY CENTRE")]

    assert [fare(b.data, x, z) for x, z in sections] == [5.60]
    assert [p.cost for p in account(b.data, route).passages] == [5.60]


def test_a_flat_gantry_opens_no_section():
    b = build_booths(
        entrance("A", gare="0001", prices={"0002": 10.0}),
        gantry("FLAT", gare="0009", price=0.90),
        exit_("B", gare="0002"),
    )
    sections = closed_sections(b.data, b.route("A", node(1), "FLAT", node(2), "B"))
    assert [(x.label, z.label) for x, z in sections] == [("A", "B")]


# --------------------------------------------------------------------------
# Whether the trade is worth offering
# --------------------------------------------------------------------------

def test_a_split_above_the_threshold_is_offered():
    a = advice(**{"0001__0002": (candidate(50, 51, 150),)})
    # 24.40 direct against 22.00 split is 2.40 for 150 s -- 57.6 EUR/h.
    chosen = a.best("0001", "0002", 24.40, lambda c: 22.00, threshold=20.0)
    assert chosen is not None
    assert chosen[1] == pytest.approx(2.40)


def test_a_split_below_the_threshold_is_not_offered():
    a = advice(**{"0001__0002": (candidate(50, 51, 3600),)})
    # 2.40 for a whole hour is 2.40 EUR/h.
    assert a.best("0001", "0002", 24.40, lambda c: 22.00, threshold=20.0) is None


def test_a_split_that_saves_nothing_is_not_offered():
    a = advice(**{"0001__0002": (candidate(50, 51, 150),)})
    assert a.best("0001", "0002", 22.00, lambda c: 22.00, threshold=20.0) is None


def test_the_best_earner_wins_not_the_biggest_saving():
    # The slow one saves more in total; the quick one is worth more per hour,
    # and per hour is what is being traded.
    a = advice(**{"0001__0002": (candidate(50, 51, 150),
                                 candidate(60, 61, 3600))})
    fares = {150: 22.00, 3600: 19.00}
    chosen = a.best("0001", "0002", 24.40,
                    lambda c: fares[c.extra_time], threshold=20.0)
    assert chosen[0].extra_time == 150


def test_a_candidate_whose_tickets_are_not_all_sold_is_skipped():
    a = advice(**{"0001__0002": (candidate(50, 51, 150),)})
    assert a.best("0001", "0002", 24.40, lambda c: None, threshold=20.0) is None


def test_a_pair_with_no_advice_offers_nothing():
    assert advice().best("0001", "0002", 24.40, lambda c: 1.0, 20.0) is None


# --------------------------------------------------------------------------
# Reading the file
# --------------------------------------------------------------------------

def test_an_absent_file_stops_the_service(tmp_path):
    # Step 12 runs in every build and the file is carried in the repository, so
    # a tree without it has lost an artefact. Reading that as "nothing can be
    # saved" would answer every journey as though the tariff were additive.
    with pytest.raises(OSError):
        splits.load(str(tmp_path / "nothing.yaml"))


def test_nodes_are_read_two_per_stop(tmp_path):
    path = tmp_path / "cost-cutting.yaml"
    path.write_text(
        "toll_booths:\n"
        "  '0001':\n"
        "    '0002':\n"
        "      - nodes: [10, 11, 20, 21]\n"
        "        extra_time: 300\n",
        encoding="utf-8",
    )
    loaded = splits.load(str(path))
    (found,) = loaded.by_pair[("0001", "0002")]
    assert found.extra_time == 300
    assert found.stops == (Stop(exit_node=10, enter_node=11),
                           Stop(exit_node=20, enter_node=21))


def test_an_odd_node_list_is_dropped_rather_than_guessed(tmp_path):
    path = tmp_path / "cost-cutting.yaml"
    path.write_text(
        "toll_booths:\n"
        "  '0001':\n"
        "    '0002':\n"
        "      - nodes: [10, 11, 20]\n"
        "        extra_time: 300\n",
        encoding="utf-8",
    )
    assert splits.load(str(path)).by_pair == {}


def test_leading_zeros_of_a_gare_survive_the_read(tmp_path):
    path = tmp_path / "cost-cutting.yaml"
    path.write_text(
        "toll_booths:\n"
        "  '04344':\n"
        "    '04224':\n"
        "      - nodes: [10, 11]\n"
        "        extra_time: 150\n",
        encoding="utf-8",
    )
    assert ("04344", "04224") in splits.load(str(path)).by_pair


# --------------------------------------------------------------------------
# The threshold
# --------------------------------------------------------------------------

def test_the_threshold_is_what_an_hour_is_worth():
    # The same rate step 10 weighted the graph with, so the router and the
    # advice cannot disagree about whether a detour is a good trade.
    from ..config import config
    assert splits.threshold() == config.eur_per_hour
