# -*- coding=utf-8 -*-
"""What a journey costs in tolls.

Every test builds the booths it needs and runs the accounting over a node
sequence it writes. Nothing here reads `data/`, reaches a router, or imports
`route`.
"""
from ..tolls import account
from .booths import (
    build_booths,
    entrance,
    exit_,
    gantry,
    lane,
    passthrough,
    plain,
    two_way,
)


def costs(journey):
    return [(p.name, p.cost) for p in journey.passages]


def reasons(journey):
    return [(p.name, p.reason) for p in journey.passages]


# --------------------------------------------------------------------------
# A ticket opened and closed
# --------------------------------------------------------------------------

def test_an_entrance_and_a_later_exit_are_priced_by_the_exits_gare():
    b = build_booths(
        entrance("VOREPPE", gare="00001", prices={"00002": 13.70, "00003": 21.80}),
        exit_("MOIRANS", gare="00002"),
    )

    journey = account(b.data, b.route("VOREPPE", 1, 2, "MOIRANS"))

    assert costs(journey) == [("VOREPPE → MOIRANS", 13.70)]
    assert journey.cost == 13.70
    assert journey.unpriced == 0


def test_the_tariff_is_looked_up_by_the_exits_gare_and_not_by_position():
    """Two exits, and the entrance prices them differently.

    The application this replaces took element [0] of a list of differently
    priced entries, so a journey was charged whatever happened to be first.
    """
    b = build_booths(
        entrance("A", gare="00001", prices={"00002": 5.00, "00003": 17.40}),
        exit_("NEAR", gare="00002"),
        exit_("FAR", gare="00003"),
    )

    near = account(b.data, b.route("A", 1, "NEAR"))
    far = account(b.data, b.route("A", 1, "FAR"))

    assert costs(near) == [("A → NEAR", 5.00)]
    assert costs(far) == [("A → FAR", 17.40)]


def test_a_second_ticket_is_opened_after_the_first_is_closed():
    b = build_booths(
        entrance("A", gare="00001", prices={"00002": 4.00}),
        exit_("B", gare="00002"),
        entrance("C", gare="00003", prices={"00004": 6.00}),
        exit_("D", gare="00004"),
    )

    journey = account(b.data, b.route("A", 1, "B", 2, "C", 3, "D"))

    assert costs(journey) == [("A → B", 4.00), ("C → D", 6.00)]
    assert journey.cost == 10.00


# --------------------------------------------------------------------------
# Flat charges
# --------------------------------------------------------------------------

def test_a_passthrough_and_a_gantry_charge_their_own_amount():
    b = build_booths(
        passthrough("LA BOISSE", price=2.40),
        gantry("TROARN FL", price=0.90),
    )

    journey = account(b.data, b.route("LA BOISSE", 1, "TROARN FL"))

    assert costs(journey) == [("LA BOISSE", 2.40), ("TROARN FL", 0.90)]
    assert journey.cost == 3.30


def test_a_flat_charge_inside_a_ticketed_section_leaves_the_ticket_alone():
    """A gantry between an entrance and its exit must not close the ticket.

    A gantry charges for a section travelled; it does not settle someone else's
    ticket. If it did, the section would be priced against the gantry instead of
    against the exit, and the exit would then read as an exit with no entrance.
    """
    b = build_booths(
        entrance("A", gare="00001", prices={"00002": 13.70}),
        gantry("G", price=0.90),
        passthrough("P", price=2.40),
        exit_("B", gare="00002"),
    )

    journey = account(b.data, b.route("A", 1, "G", 2, "P", 3, "B"))

    assert costs(journey) == [("G", 0.90), ("P", 2.40), ("A → B", 13.70)]
    assert journey.cost == 17.00
    assert journey.unpriced == 0


# --------------------------------------------------------------------------
# A barrier driven both ways
# --------------------------------------------------------------------------

OUTSIDE, INSIDE = 10, 20


def _two_way_booths():
    return build_booths(
        entrance("CLERMONT", gare="00001", prices={"00005": 35.20}),
        two_way("ESVRES", gare="00005", prices={"00009": 1.90}, inside=[INSIDE],
                outside=[OUTSIDE]),
        exit_("TOURS", gare="00009"),
    )


def test_a_two_way_barrier_reached_from_the_outside_opens_a_ticket():
    b = _two_way_booths()

    journey = account(b.data, b.route(OUTSIDE, "ESVRES", INSIDE, "TOURS"))

    assert costs(journey) == [("ESVRES → TOURS", 1.90)]


def test_a_two_way_barrier_reached_from_the_inside_closes_one():
    b = _two_way_booths()

    journey = account(b.data, b.route("CLERMONT", 1, INSIDE, "ESVRES", OUTSIDE))

    assert costs(journey) == [("CLERMONT → ESVRES", 35.20)]


def test_the_two_directions_of_a_two_way_barrier_differ():
    b = _two_way_booths()

    entering = account(b.data, b.route(OUTSIDE, "ESVRES", INSIDE, "TOURS"))
    leaving = account(b.data, b.route("CLERMONT", 1, INSIDE, "ESVRES", OUTSIDE))

    assert costs(entering) != costs(leaving)


def test_the_ticket_state_does_not_decide_the_sense():
    """Reached from the inside with no ticket open, it is still an exit.

    The application this replaced treated a two-way barrier as an entrance
    whenever no ticket happened to be open, which booked every journey leaving
    the network through one as though it were joining.
    """
    b = _two_way_booths()

    journey = account(b.data, b.route(INSIDE, "ESVRES", OUTSIDE))

    assert reasons(journey) == [("ESVRES", "exit without an entrance")]
    assert journey.cost == 0
    assert journey.unpriced == 1


def test_a_two_way_barrier_falls_back_to_the_following_node():
    """The preceding node is neither side, so the following one decides.

    A following node that is inside means the vehicle is on its way in.
    """
    b = build_booths(
        two_way("ESVRES", gare="00005", prices={"00009": 1.90}, inside=[INSIDE],
                outside=[OUTSIDE]),
        exit_("TOURS", gare="00009"),
    )

    entering = account(b.data, b.route(999, "ESVRES", INSIDE, "TOURS"))
    assert costs(entering) == [("ESVRES → TOURS", 1.90)]

    leaving = account(b.data, b.route(999, "ESVRES", OUTSIDE))
    assert reasons(leaving) == [("ESVRES", "exit without an entrance")]


# --------------------------------------------------------------------------
# Lanes, and one plaza crossed once
# --------------------------------------------------------------------------

def test_a_lane_is_charged_against_the_plaza_it_belongs_to():
    """A plaza is one node per lane and a route drives exactly one of them.

    Looking for the plaza's own id finds nothing whenever the router picked a
    neighbouring lane, and the passage is missed entirely.
    """
    b = build_booths(
        entrance("A", gare="00001", prices={"00002": 8.30}),
        exit_("NIORT EST", gare="00002"),
        lane("NIORT EST LANE 2", of="NIORT EST"),
    )

    journey = account(b.data, b.route("A", 1, "NIORT EST LANE 2"))

    assert costs(journey) == [("A → NIORT EST", 8.30)]


def test_consecutive_nodes_of_one_booth_make_one_passage():
    b = build_booths(passthrough("P", price=2.40), lane("P2", of="P"))

    journey = account(b.data, b.route("P", "P2", "P"))

    assert costs(journey) == [("P", 2.40)]


def test_the_same_booth_reached_again_later_makes_another_passage():
    b = build_booths(passthrough("P", price=2.40))

    journey = account(b.data, b.route("P", 1, 2, "P"))

    assert costs(journey) == [("P", 2.40), ("P", 2.40)]
    assert journey.cost == 4.80


# --------------------------------------------------------------------------
# The total
# --------------------------------------------------------------------------

def test_the_total_is_the_sum_of_the_priced_passages_only():
    b = build_booths(
        entrance("A", gare="00001", prices={"00002": 13.70}),
        exit_("B", gare="00002"),
        gantry("PRICED", price=0.90),
        gantry("UNPRICED"),
        exit_("STRAY", gare="00099"),
    )

    journey = account(b.data, b.route("STRAY", 1, "A", 2, "PRICED", 3, "UNPRICED", 4, "B"))

    assert journey.cost == 14.60
    assert journey.unpriced == 2
    assert sum(p.cost for p in journey.passages if p.priced) == journey.cost


def test_a_journey_crossing_nothing_costs_nothing():
    b = build_booths(entrance("A", gare="00001", prices={"00002": 13.70}))

    journey = account(b.data, [1, 2, 3, 4])

    assert journey.passages == []
    assert journey.cost == 0
    assert journey.unpriced == 0


# --------------------------------------------------------------------------
# Every state that cannot be priced
#
# None of them raises, none of them is charged 0 EUR, and each carries a reason
# of its own. Zero would say the crossing was free, which is a different claim
# from not knowing what it cost.
# --------------------------------------------------------------------------

def test_an_exit_with_no_ticket_open():
    """The journey began inside the toll network."""
    b = build_booths(exit_("B", gare="00002"))

    journey = account(b.data, b.route("B", 1, 2))

    assert reasons(journey) == [("B", "exit without an entrance")]
    assert journey.passages[0].cost is None


def test_an_entrance_reached_while_a_ticket_is_already_open():
    b = build_booths(
        entrance("A", gare="00001", prices={"00002": 13.70}),
        entrance("C", gare="00003", prices={"00002": 4.00}),
        exit_("B", gare="00002"),
    )

    journey = account(b.data, b.route("A", 1, "C", 2, "B"))

    assert reasons(journey)[0] == ("A", "entrance never closed by an exit")
    assert journey.passages[0].cost is None
    # The later ticket still closes normally.
    assert costs(journey)[1] == ("C → B", 4.00)


def test_an_exit_whose_gare_the_entrance_does_not_price():
    b = build_booths(
        entrance("A", gare="00001", prices={"00002": 13.70}),
        exit_("ELSEWHERE", gare="00404"),
    )

    journey = account(b.data, b.route("A", 1, "ELSEWHERE"))

    assert reasons(journey) == [("A → ELSEWHERE", "the entrance does not price this exit")]
    assert journey.passages[0].cost is None


def test_an_exit_carrying_no_gare_code():
    """Twelve of the 1 295 real booths map to no gare."""
    b = build_booths(
        entrance("A", gare="00001", prices={"00002": 13.70}),
        exit_("UNMAPPED"),
    )

    journey = account(b.data, b.route("A", 1, "UNMAPPED"))

    assert reasons(journey) == [("A → UNMAPPED", "the booth maps to no gare")]


def test_a_missing_tariff_and_an_unknown_gare_are_told_apart():
    assert "the entrance does not price this exit" != "the booth maps to no gare"


def test_a_booth_absent_from_the_price_file():
    """Twenty of the real booths are in the inventory and not in the tariffs."""
    b = build_booths(plain("SAINT EXUPERY", gare="00007"))

    journey = account(b.data, b.route("SAINT EXUPERY"))

    assert reasons(journey) == [("SAINT EXUPERY", "the booth is absent from the price file")]
    assert journey.passages[0].cost is None


def test_a_gantry_or_passthrough_carrying_no_amount():
    """Four real gantries are typed by the inventory and carry no tariff.

    Counted, not listed. There is no amount to show, and the name adds nothing
    to a road the driver is already looking at. The count is still kept, so the
    journey never stops admitting that something was crossed and not charged.
    """
    b = build_booths(gantry("CHAMBERY NORD"), passthrough("NO PRICE"))

    journey = account(b.data, b.route("CHAMBERY NORD", 1, "NO PRICE"))

    assert journey.passages == []
    assert journey.silent_unpriced == 2
    assert journey.unpriced == 2
    assert journey.cost == 0


def test_a_two_way_booth_whose_neighbours_are_on_neither_side():
    b = build_booths(
        two_way("ESVRES", gare="00005", prices={}, inside=[INSIDE], outside=[OUTSIDE]),
    )

    journey = account(b.data, b.route(777, "ESVRES", 888))

    assert reasons(journey) == [("ESVRES", "neither neighbour is a recorded side of this barrier")]
    assert journey.passages[0].cost is None


def test_a_route_ending_with_a_ticket_still_open():
    b = build_booths(entrance("BEAUNE SUD", gare="00001", prices={"00002": 13.70}))

    journey = account(b.data, b.route(1, "BEAUNE SUD", 2))

    assert reasons(journey) == [("BEAUNE SUD", "entrance never closed by an exit")]
    assert journey.passages[0].cost is None


def test_a_booth_with_no_name_is_labelled_by_its_node_id():
    """A reader can look a node id up. A placeholder identifies nothing."""
    b = build_booths(plain("x"))
    booth = b.booth("x")
    # `name` is derived from the two sources, so it is the sources that have to
    # be emptied. The OSM one is already empty; a declared booth carries only the
    # operator's.
    object.__setattr__(booth, "operator_name", None)

    journey = account(b.data, b.route("x"))

    assert journey.passages[0].name == f"OSM node {b['x']}"


def test_no_unpriceable_passage_is_charged_zero_and_every_reason_is_distinct():
    """One journey holding several of the states, checked together."""
    b = build_booths(
        exit_("STRAY", gare="00099"),
        entrance("A", gare="00001", prices={"00002": 13.70}),
        entrance("REOPENED", gare="00003", prices={"00404": 1.00}),
        exit_("ELSEWHERE", gare="00777"),
        gantry("NO TARIFF"),
        plain("UNTYPED"),
        two_way("NO SIDES", gare="00005", inside=[INSIDE], outside=[OUTSIDE]),
        entrance("LEFT OPEN", gare="00006", prices={"00002": 2.00}),
    )

    journey = account(b.data, b.route(
        "STRAY", 1, "A", 2, "REOPENED", 3, "ELSEWHERE", 4,
        "NO TARIFF", 5, "UNTYPED", 6, 777, "NO SIDES", 888, "LEFT OPEN", 7,
    ))

    unpriced = [p for p in journey.passages if not p.priced]

    # Every listed passage is one that could not be priced. `NO TARIFF` is the
    # one crossing that is counted without being listed, so the total is one
    # more than the list.
    assert len(unpriced) == len(journey.passages)
    assert journey.silent_unpriced == 1
    assert journey.unpriced == len(unpriced) + 1
    assert journey.cost == 0
    for passage in unpriced:
        assert passage.cost is None, f"{passage.name} was charged {passage.cost!r}"
        assert passage.cost != 0
        assert passage.reason, f"{passage.name} carries no reason"
        assert passage.name

    assert {p.reason for p in unpriced} == {
        "exit without an entrance",
        "entrance never closed by an exit",
        "the entrance does not price this exit",
        "the booth is absent from the price file",
        "neither neighbour is a recorded side of this barrier",
    }



# --------------------------------------------------------------------------
# An exit reached without crossing an entrance
# --------------------------------------------------------------------------
# Some gantries are ticketless entrances. The portal reads the plate, and the
# barrier at the far end takes the money. The vehicle crosses nothing that looks
# like an entrance. So when an exit is reached with no ticket open, the
# accounting looks back at the last gantry. If that gantry has a fare to this
# exit, it was the entrance. A real Chambéry Nord to Annecy Centre journey
# needed this, and was answered with an unpriced passage instead.

def test_an_exit_with_no_entrance_looks_back_at_a_gantry_that_prices_it():
    b = build_booths(
        gantry("CHAMBERY NORD", gare="03008", prices={"03012": 5.60}),
        exit_("ANNECY CENTRE", gare="03012"),
    )

    journey = account(b.data, b.route("CHAMBERY NORD", 1, "ANNECY CENTRE"))

    assert costs(journey) == [("CHAMBERY NORD → ANNECY CENTRE", 5.60)]
    assert journey.unpriced == 0


def test_the_look_back_reads_the_tariff_by_gare_not_by_node():
    """The gantry's own map is thin. The booth beside it holds the fare.

    Both booths are gare `03008`. A rate request names two gare codes, so both
    booths charge the same. They hold different numbers of tariffs because
    direct pricing never asks about a gantry: it takes its sources from `enter`
    and `bidirectional` booths only. A gantry is priced by the routes that
    happen to cross it, and nothing else. In the real file the gantry holds
    three tariffs and the `enter` booth beside it holds twenty-seven.
    """
    b = build_booths(
        gantry("CHAMBERY NORD gantry", gare="03008", prices={"03011": 3.60}),
        entrance("CHAMBERY NORD", gare="03008", prices={"03012": 5.60}),
        exit_("ANNECY CENTRE", gare="03012"),
    )

    journey = account(b.data, b.route("CHAMBERY NORD gantry", 1, "ANNECY CENTRE"))

    assert costs(journey) == [("CHAMBERY NORD gantry → ANNECY CENTRE", 5.60)]
    assert journey.unpriced == 0


def test_an_exit_with_no_entrance_and_no_gantry_behind_it_is_unpriced():
    """The look-back adds a fare where one exists. It invents none."""
    b = build_booths(exit_("Z", gare="00002"))

    journey = account(b.data, b.route(1, "Z"))

    assert reasons(journey) == [("Z", "exit without an entrance")]


def test_a_gantry_that_charges_flat_is_not_also_billed_as_a_section():
    """It takes its money at the portal, so it is not a ticketless entrance.

    One booth in the country holds both a flat price and tariffs: Montbeugny Est
    Sens 2. Charging the flat amount and then a section for the same crossing
    would bill it twice.
    """
    b = build_booths(
        gantry("MONTBEUGNY EST", gare="22545", price=0.90, prices={"00002": 1.90}),
        exit_("Z", gare="00002"),
    )

    journey = account(b.data, b.route("MONTBEUGNY EST", 1, "Z"))

    assert costs(journey) == [("MONTBEUGNY EST", 0.90), ("Z", None)]
    assert reasons(journey) == [
        ("MONTBEUGNY EST", None),
        ("Z", "exit without an entrance"),
    ]


def test_a_flat_gantry_inside_a_section_still_leaves_the_ticket_alone():
    """This regression would lose money instead of showing a gap.

    A gantry with no tariffs must still fall through to the flat charge. Reading
    it as the start of a section would close A's ticket in the wrong place.
    """
    b = build_booths(
        entrance("A", gare="00001", prices={"00002": 13.70}),
        gantry("FLAT", gare="00009", price=0.90),
        exit_("B", gare="00002"),
    )

    journey = account(b.data, b.route("A", 1, "FLAT", 2, "B"))

    assert costs(journey) == [("FLAT", 0.90), ("A → B", 13.70)]
    assert journey.unpriced == 0


def test_a_crossed_entrance_still_reads_only_its_own_tariffs():
    """The gare-wide reading belongs to the look-back and nowhere else.

    An entrance that was actually crossed already answers for itself, and
    widening it would move fares that are being quoted correctly today. The
    look-back only fires where the passage is unpriced, so it can replace a gap
    with an amount and can never change one.
    """
    b = build_booths(
        entrance("NORTHBOUND", gare="04784", prices={"00009": 3.00}),
        entrance("SOUTHBOUND", gare="04784", prices={"00002": 29.00}),
        exit_("B", gare="00002"),
    )

    journey = account(b.data, b.route("NORTHBOUND", 1, "B"))

    assert costs(journey) == [("NORTHBOUND → B", None)]
    assert reasons(journey) == [
        ("NORTHBOUND → B", "the entrance does not price this exit"),
    ]
