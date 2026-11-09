# -*- coding=utf-8 -*-
"""What the bot decides to send, tested without a bot.

Nothing here substitutes an object for a library. `drive` is a generator that
yields the things it needs and receives the answers back, so a test states a
journey and a list of answers and reads off the messages. There is no Telegram
client, no session, no network, and no clock.

`run` below is the whole harness: eleven lines that push prepared answers into
the generator and collect what it asked for. If that ever needs to grow into
something that patches a module or intercepts a socket, the decision has stopped
being a decision and started doing the work itself.

Routes here run along a parallel so that halving by distance halves by index too,
and the midpoint a test expects is the one arithmetic gives.
"""
from .. import drive as D
from ..drive import AskGoogle, AskRoute, MAX_DEPTH, Opinion, Part, Stop, drive, midpoint

FITS = 0.98

# The booths a part's own route crosses, where a test cares. Plain integers: what
# a booth is identified by is the accounting's business, and the decision only
# ever asks whether one set is contained in another.
OURS = frozenset({1, 2, 3})


def fits(share):
    return share >= FITS


def link(points):
    """A directions link, reduced to what a test needs to read."""
    return "|".join(points)


def route(n=201, lat=45.0, lon0=1.0, step=0.01):
    """A route along a parallel, `n` nodes, evenly spaced."""
    return tuple((lon0 + i * step, lat) for i in range(n))


def part(cost=10.0, depth=0, waypoints=(), nodes=None, booths=None, fast_booths=None, stops=()):
    nodes = route() if nodes is None else nodes
    return Part(origin=nodes[0], destination=nodes[-1], cost=cost,
                waypoints=waypoints, nodes=nodes, depth=depth, booths=booths,
                fast_booths=fast_booths, stops=stops)


def run(p, budget, answers):
    """Drive the decision with prepared answers. Returns (outcome, requests)."""
    answers = list(answers)
    asked = []
    gen = drive(p, budget, fits, link)
    try:
        request = next(gen)
        while True:
            asked.append(request)
            request = gen.send(answers.pop(0) if answers else None)
    except StopIteration as stop:
        return stop.value, asked


def google(share, waypoints=(), booths=None):
    """What one Google request bought.

    `booths` defaults to None -- the tolls could not be established -- so that
    every test written before the toll criterion existed still states the case it
    was written to state: a route judged on the road it drove.
    """
    return Opinion(share=share, waypoints=waypoints, booths=booths)


def half_of(p, cost, depth, booths=None, fast_booths=None):
    """The near half of a part, as the shell would return it."""
    at = midpoint(p.nodes)
    cut = p.nodes.index(at)
    return Part(origin=p.nodes[0], destination=at, cost=cost,
                nodes=p.nodes[:cut + 1], depth=depth,
                booths=booths, fast_booths=fast_booths)


def far_of(p, cost, depth):
    at = midpoint(p.nodes)
    cut = p.nodes.index(at)
    return Part(origin=at, destination=p.nodes[-1], cost=cost,
                nodes=p.nodes[cut:], depth=depth)


# --- the rules, one at a time -------------------------------------------------

def test_a_toll_free_part_costs_nothing_and_says_how_to_drive_it():
    outcome, asked = run(part(cost=0.0), budget=100, answers=[])

    assert asked == [], "a toll-free route must not be asked about"
    assert outcome.spent == 0
    assert len(outcome.messages) == 1
    assert D.AVOID_TOLLS in outcome.messages[0].text
    assert outcome.pending == []


def test_toll_free_is_decided_before_the_budget():
    """Order matters: the cheapest answer is also the most correct one."""
    outcome, asked = run(part(cost=0.0), budget=0, answers=[])

    assert asked == []
    assert D.AVOID_TOLLS in outcome.messages[0].text
    assert D.UNVERIFIED not in outcome.messages[0].text


def test_a_part_whose_two_routes_pay_the_same_tolls_is_not_asked_about():
    """Both of our graphs pick a road paying these booths, so there is no
    cheaper road left for a waypoint to steer onto."""
    outcome, asked = run(part(cost=10.0, booths=OURS, fast_booths=OURS),
                         budget=100, answers=[])

    assert asked == [], "nothing is worth asking when our own routes agree"
    assert outcome.spent == 0
    assert len(outcome.messages) == 1
    assert outcome.pending == []
    assert D.AVOID_TOLLS not in outcome.messages[0].text
    assert D.UNVERIFIED not in outcome.messages[0].text


def test_an_agreed_part_is_linked_straight_through():
    """No waypoints: they steer a router off its road, and here both roads cost
    the same, so there is nothing to steer away from."""
    p = part(cost=10.0, waypoints=((1.5, 45.0), (1.8, 45.0)),
             booths=OURS, fast_booths=OURS)
    outcome, _asked = run(p, budget=100, answers=[])

    assert outcome.messages[0].link == link([
        "Current Location", f"{p.destination[1]:.6f},{p.destination[0]:.6f}"])


def test_an_agreed_part_records_that_nobody_paid_for_the_answer():
    outcome, _asked = run(part(cost=10.0, booths=OURS, fast_booths=OURS),
                          budget=100, answers=[])

    assert outcome.messages[0].basis == D.Basis.AGREED
    assert outcome.messages[0].basis != D.Basis.TOLLS, \
        "a link nobody paid for must not read like one that was bought"


def test_toll_free_is_decided_before_the_routes_agreeing():
    """A toll-free part crosses nothing by either road, so its two sets are both
    empty and equal. It still owes the avoid-tolls instruction: the sets are
    ours, and the setting governs the driver's own application."""
    empty = frozenset()
    outcome, asked = run(part(cost=0.0, booths=empty, fast_booths=empty),
                         budget=100, answers=[])

    assert asked == []
    assert D.AVOID_TOLLS in outcome.messages[0].text
    assert outcome.messages[0].basis is None


def test_settle_tells_a_toll_free_part_to_avoid_tolls():
    message = D.settle(part(cost=0.0), link)

    assert "Please enable Avoid tolls before driving." in message.text


def test_settle_links_an_agreed_part_straight_through():
    p = part(cost=10.0, waypoints=((1.5, 45.0),), booths=OURS, fast_booths=OURS)

    message = D.settle(p, link)

    assert message.link == "Current Location|45.000000,3.000000"
    assert message.basis == "our own two routes agreeing"


def test_settle_leaves_a_part_that_needs_google():
    assert D.settle(part(cost=10.0, booths=OURS, fast_booths=OURS | {4}), link) is None


def test_a_fastest_route_that_adds_a_booth_is_asked_about():
    outcome, asked = run(part(cost=10.0, booths=OURS, fast_booths=OURS | {4}),
                         budget=100, answers=[google(0.99)])

    assert [type(a) for a in asked] == [AskGoogle], \
        "our two graphs disagree, so the plain link is not settled"
    assert outcome.spent == 1


def test_a_fastest_route_crossing_fewer_booths_is_asked_about():
    """Equality, not containment. A strict subset means our two graphs chose
    different roads, which is exactly when the plain link is unsettled."""
    outcome, asked = run(part(cost=10.0, booths=OURS, fast_booths=frozenset({1, 2})),
                         budget=100, answers=[google(0.99)])

    assert [type(a) for a in asked] == [AskGoogle]


def test_two_unknown_booth_sets_are_not_an_agreement():
    """`None == None` is true, and it must not be read as our routes agreeing."""
    outcome, asked = run(part(cost=10.0, booths=None, fast_booths=None),
                         budget=100, answers=[google(0.99)])

    assert [type(a) for a in asked] == [AskGoogle]
    assert outcome.spent == 1


def test_one_unknown_booth_set_is_not_an_agreement():
    outcome, asked = run(part(cost=10.0, booths=OURS, fast_booths=None),
                         budget=100, answers=[google(0.99)])

    assert [type(a) for a in asked] == [AskGoogle]


def test_an_exhausted_budget_still_produces_a_link():
    outcome, asked = run(part(cost=10.0), budget=0, answers=[])

    assert asked == []
    assert len(outcome.messages) == 1
    assert D.UNVERIFIED in outcome.messages[0].text
    assert outcome.messages[0].link


def test_a_route_google_follows_is_sent_after_one_ask():
    outcome, asked = run(part(), budget=100, answers=[google(0.99, ((1.5, 45.0),))])

    assert len(asked) == 1 and isinstance(asked[0], AskGoogle)
    assert outcome.spent == 1
    assert len(outcome.messages) == 1
    assert outcome.messages[0].text == ""
    assert outcome.pending == []


# --- judged by what it costs ---------------------------------------------------

def test_a_route_on_a_different_road_but_the_same_tolls_is_sent_as_it_is():
    """72 of the 100 journeys the share rejects are this one.

    Every one of them is corrected today, and may be split into four links, for a
    difference that costs the driver nothing.
    """
    p = part(booths=OURS)
    outcome, asked = run(p, budget=100, answers=[google(0.60, booths=OURS)])

    assert len(asked) == 1, "no correcting ask, and no route for a half"
    assert outcome.spent == 1
    assert outcome.pending == [], "and no split"
    assert outcome.messages[0].basis == D.Basis.TOLLS


def test_a_route_paying_fewer_of_our_tolls_is_not_a_fault():
    """Containment, not equality. A cheaper route costs the driver less."""
    p = part(booths=OURS)
    outcome, asked = run(p, budget=100, answers=[google(0.60, booths=frozenset({1, 2}))])

    assert len(asked) == 1
    assert outcome.messages[0].basis == D.Basis.TOLLS


def test_a_route_that_adds_a_toll_is_not_accepted_however_well_it_followed():
    """At the bound, so what it does *not* do is the whole of what is asserted."""
    p = part(depth=MAX_DEPTH, booths=OURS)
    outcome, asked = run(p, budget=100, answers=[
        google(0.999, booths=OURS | {4}),       # drove our road, pays one more
        google(0.999, booths=OURS | {4}),
    ])

    assert len(asked) == 2, "a route that adds a booth is corrected, not accepted"
    assert outcome.messages[0].basis is None, "and is sent as the best there was"


def test_the_tolls_are_asked_before_the_road():
    """A route can pass one test and fail the other. The tolls decide."""
    p = part(booths=OURS)
    outcome, _ = run(p, budget=100, answers=[
        google(0.10, booths=OURS),              # nowhere near our road, same bill
    ])

    assert outcome.messages[0].basis == D.Basis.TOLLS


def test_a_route_whose_tolls_are_unknown_is_judged_on_the_road():
    p = part(booths=OURS)
    outcome, _ = run(p, budget=100, answers=[google(0.99, booths=None)])

    assert outcome.messages[0].basis == D.Basis.ROAD


def test_a_part_whose_own_tolls_are_unknown_is_judged_on_the_road():
    """Unknown on either side falls back. An answer needs both to compare."""
    p = part(booths=None)
    outcome, _ = run(p, budget=100, answers=[google(0.99, booths=OURS)])

    assert outcome.messages[0].basis == D.Basis.ROAD


# --- a route that leaves the motorway and joins it again -------------------------

def stop_at(index, booths=frozenset({3, 4})):
    """A stop on the route of `route()`, at node `index`."""
    return Stop(location=route()[index], booths=booths, index=index)


def test_a_route_that_makes_every_stop_is_accepted_on_its_tolls():
    p = part(booths=frozenset({1, 2, 3, 4}), stops=(stop_at(100),))

    basis = D.accepts(p, google(0.50, booths=frozenset({1, 2, 3, 4})), fits)

    assert basis == "the tolls it pays"


def test_a_route_that_skips_a_stop_is_not_accepted():
    """It pays fewer of our booths, which accepts a route without stops."""
    p = part(booths=frozenset({1, 2, 3, 4}), stops=(stop_at(100),))

    assert D.accepts(p, google(0.99, booths=frozenset({1, 2})), fits) is None


def test_a_route_that_makes_every_stop_and_adds_a_toll_is_not_accepted():
    p = part(booths=frozenset({1, 2, 3, 4}), stops=(stop_at(100),))

    assert D.accepts(p, google(0.99, booths=frozenset({1, 2, 3, 4, 9})), fits) is None


def test_a_route_with_stops_is_not_accepted_on_the_road():
    p = part(booths=frozenset({1, 2, 3, 4}), stops=(stop_at(100),))

    assert D.accepts(p, google(1.0, booths=None), fits) is None


# --- a refuel plan: gas stations are stops without booths ----------------------

def station_at(index):
    """A gas station on the route of `route()`, at node `index`."""
    return Stop(location=route()[index], booths=frozenset(), index=index)


def test_a_toll_free_plan_is_linked_through_its_stations_with_no_request():
    p = part(cost=0.0, stops=(station_at(50), station_at(150)))

    outcome, asked = run(p, budget=100, answers=[])

    assert asked == []
    assert outcome.messages[0].link == (
        "Current Location|45.000000,1.500000|45.000000,2.500000|45.000000,3.000000")
    assert D.AVOID_TOLLS in outcome.messages[0].text


def test_an_agreed_plan_is_linked_through_its_stations_only():
    p = part(cost=10.0, waypoints=((1.2, 45.0),), booths=OURS, fast_booths=OURS, stops=(station_at(50),))

    message = D.settle(p, link)

    assert message.link == "Current Location|45.000000,1.500000|45.000000,3.000000"
    assert message.basis == "our own two routes agreeing"


def test_a_superoptimal_part_settles_with_no_waypoints():
    p = part(cost=0.0, waypoints=((1.2, 45.0),), stops=(stop_at(100),))

    assert D.settle(p, link).link == "Current Location|45.000000,3.000000"


def test_a_plan_with_only_stations_and_unknown_tolls_is_judged_on_the_road():
    p = part(booths=OURS, stops=(station_at(50),))

    assert D.accepts(p, google(0.99, booths=None), fits) == "the road it drives"


def test_a_plan_with_a_booth_stop_is_not_accepted_on_the_road():
    p = part(booths=frozenset({1, 2, 3, 4}), stops=(station_at(50), stop_at(100)))

    assert D.accepts(p, google(1.0, booths=None), fits) is None


def halves_asked_for(p):
    """The two `AskRoute` a part makes once Google fails it twice."""
    _outcome, asked = run(p, budget=100, answers=[google(0.50), google(0.55)])
    return [a for a in asked if isinstance(a, AskRoute)]


def test_each_stop_goes_to_the_half_that_drives_it():
    near, far = halves_asked_for(part(stops=(stop_at(40), stop_at(160))))

    assert near.stops == (stop_at(40),)
    assert far.stops == (stop_at(160),)


def test_a_stop_at_the_midpoint_goes_to_the_near_half():
    near, far = halves_asked_for(part(stops=(stop_at(100),)))

    assert near.stops == (stop_at(100),)
    assert far.stops == ()


def test_a_part_without_stops_asks_for_halves_without_stops():
    near, far = halves_asked_for(part())

    assert (near.stops, far.stops) == ((), ())


def test_an_unchecked_link_carries_the_stop():
    p = part(waypoints=(route()[100],), stops=(stop_at(100),))

    outcome, _asked = run(p, budget=0, answers=[])

    assert outcome.messages[0].link == "Current Location|45.000000,2.000000|45.000000,3.000000"


def test_a_correcting_ask_can_be_accepted_on_its_tolls():
    p = part(booths=OURS)
    outcome, asked = run(p, budget=100, answers=[
        google(0.50, waypoints=((1.4, 45.0),), booths=OURS | {9}),
        google(0.50, waypoints=((1.4, 45.0),), booths=OURS),
    ])

    assert len(asked) == 2
    assert outcome.pending == [], "corrected onto our tolls, so not split"
    assert outcome.messages[0].basis == D.Basis.TOLLS


def test_a_route_that_adds_a_toll_and_cannot_be_corrected_is_still_split():
    """Embrun to Ancenis-Saint-Géréon: 72.00 EUR against our 37.80."""
    p = part(booths=OURS)
    near, far = half_of(p, 5.0, 1), far_of(p, 5.0, 1)
    outcome, asked = run(p, budget=100, answers=[
        google(0.99, booths=OURS | {4}), google(0.99, booths=OURS | {4}),
        near, far,
        google(0.99),
    ])

    assert [type(a) for a in asked] == [AskGoogle, AskGoogle, AskRoute, AskRoute, AskGoogle]
    assert outcome.pending == [far]


def test_each_ask_carries_the_route_it_is_measured_against():
    p = part()
    near, far = half_of(p, 5.0, 1), far_of(p, 5.0, 1)
    _outcome, asked = run(p, budget=100, answers=[
        google(0.50), google(0.55), near, far, google(0.99),
    ])

    assert [a.nodes for a in asked if isinstance(a, AskGoogle)] == [p.nodes, p.nodes, near.nodes]


def test_a_route_google_leaves_is_corrected_and_sent():
    corrected = ((1.4, 45.0), (1.6, 45.0))
    outcome, asked = run(part(), budget=100, answers=[
        google(0.60, corrected),      # first ask: does not follow, waypoints added
        google(0.99, corrected),      # second ask: through the corrected set
    ])

    assert len(asked) == 2
    assert asked[1].waypoints == corrected, "the second ask uses the corrected set"
    assert outcome.spent == 2
    assert len(outcome.messages) == 1
    assert outcome.pending == []


def test_a_route_that_cannot_be_corrected_is_split():
    p = part()
    near, far = half_of(p, 5.0, 1), far_of(p, 5.0, 1)
    outcome, asked = run(p, budget=100, answers=[
        google(0.50), google(0.55),   # two asks, neither follows
        near, far,                    # the shell routes the two halves
        google(0.99),                 # the near half is asked about and follows
    ])

    assert [type(a) for a in asked] == [AskGoogle, AskGoogle, AskRoute, AskRoute, AskGoogle]
    assert len(outcome.messages) == 1
    assert D.COMPLEX in outcome.messages[0].text
    assert outcome.pending == [far], "the far half is queued, not sent"


def test_a_toll_free_half_is_driven_by_setting_not_by_waypoints():
    p = part()
    near, far = half_of(p, 0.0, 1), far_of(p, 9.0, 1)
    outcome, asked = run(p, budget=100, answers=[
        google(0.50), google(0.55), near, far,
    ])

    assert not any(isinstance(a, AskGoogle) for a in asked[2:]), \
        "a toll-free half must not be asked about"
    assert D.COMPLEX in outcome.messages[0].text
    assert D.AVOID_TOLLS in outcome.messages[0].text
    assert outcome.pending == [far]


def test_a_half_whose_two_routes_agree_is_not_asked_about():
    """The rule reads a part, so it answers a half on the same terms."""
    p = part()
    near = half_of(p, 5.0, 1, booths=OURS, fast_booths=OURS)
    far = far_of(p, 5.0, 1)
    outcome, asked = run(p, budget=100, answers=[
        google(0.50), google(0.55), near, far,
    ])

    assert not any(isinstance(a, AskGoogle) for a in asked[2:]), \
        "a half whose own two routes agree must not be asked about"
    assert outcome.spent == 2, "the two asks for the whole, and nothing for the half"
    assert D.COMPLEX in outcome.messages[0].text
    assert outcome.messages[0].basis == D.Basis.AGREED
    assert outcome.pending == [far]


def test_the_message_does_not_call_every_part_the_first_half():
    """A journey halved twice sends three parts; none of them is "the first half".

    Measured on Embrun to Ancenis-Saint-Géréon, which resolves into three links:
    the wording announced the first half, then a quarter of it, then the far
    half, all as "the first half of the route".
    """
    p = part()
    near, far = half_of(p, 5.0, 1), far_of(p, 5.0, 1)
    near_near, near_far = half_of(near, 2.0, 2), far_of(near, 2.0, 2)
    outcome, _ = run(p, budget=100, answers=[
        google(0.5), google(0.5), near, far,
        google(0.5), google(0.5), near_near, near_far,
        google(0.99),
    ])

    text = outcome.messages[0].text
    assert "half" not in text.lower(), text
    assert D.COMPLEX in text

    # and the parts it still owes are answered with the same wording, not a
    # second and third claim to be the beginning
    for pending in outcome.pending:
        later, _ = run(pending, budget=100, answers=[google(0.99)])
        for msg in later.messages:
            assert "first half" not in msg.text.lower(), msg.text


def test_a_half_that_splits_again_queues_both_of_what_it_owes():
    """The defect this guards: dropping the far quarter and losing a quarter of the trip."""
    p = part()
    near, far = half_of(p, 5.0, 1), far_of(p, 5.0, 1)
    near_near, near_far = half_of(near, 2.0, 2), far_of(near, 2.0, 2)
    outcome, asked = run(p, budget=100, answers=[
        google(0.50), google(0.55), near, far,          # the whole splits
        google(0.50), google(0.55), near_near, near_far,  # the near half splits too
        google(0.99),                                    # the near quarter follows
    ])

    assert len(outcome.messages) == 1
    assert outcome.pending == [near_far, far], \
        "the near half's far quarter comes before the far half"


def test_splitting_stops_at_the_bound():
    p = part(depth=MAX_DEPTH)
    outcome, asked = run(p, budget=100, answers=[google(0.50), google(0.55)])

    assert [type(a) for a in asked] == [AskGoogle, AskGoogle]
    assert not any(isinstance(a, AskRoute) for a in asked), "a part at the bound is not split"
    assert len(outcome.messages) == 1
    assert outcome.messages[0].link
    assert outcome.pending == []


def test_a_route_too_short_to_halve_is_not_halved():
    p = part(nodes=route(n=2))
    outcome, asked = run(p, budget=100, answers=[google(0.50), google(0.55)])

    assert not any(isinstance(a, AskRoute) for a in asked)
    assert len(outcome.messages) == 1


def test_a_failed_request_is_answered_like_an_exhausted_budget():
    outcome, asked = run(part(), budget=100, answers=[None])

    assert len(asked) == 1
    assert D.UNVERIFIED in outcome.messages[0].text
    assert outcome.messages[0].link


def test_the_budget_stops_the_second_ask():
    """One request left is enough to ask once and not enough to correct."""
    outcome, asked = run(part(), budget=1, answers=[google(0.50)])

    assert len(asked) == 1, "the correcting ask must not be made"
    assert outcome.spent == 1
    assert len(outcome.messages) == 1


# --- the properties the whole thing rests on ----------------------------------

def test_every_link_starts_where_the_driver_is():
    p = part()
    near, far = half_of(p, 5.0, 1), far_of(p, 5.0, 1)
    outcome, _ = run(p, budget=100, answers=[
        google(0.50), google(0.55), near, far, google(0.99),
    ])

    for message in outcome.messages:
        assert message.link.startswith("Current Location|"), message.link


def test_the_worst_case_is_bounded():
    """Fourteen requests for a journey, across every press it takes to drive it."""
    p = part()
    near, far = half_of(p, 5.0, 1), far_of(p, 5.0, 1)
    near_near, near_far = half_of(near, 2.0, 2), far_of(near, 2.0, 2)
    far_near, far_far = half_of(far, 2.0, 2), far_of(far, 2.0, 2)

    first, _ = run(p, budget=100, answers=[
        google(0.5), google(0.5), near, far,
        google(0.5), google(0.5), near_near, near_far,
        google(0.5), google(0.5),
    ])
    second, _ = run(first.pending[0], budget=100, answers=[google(0.5), google(0.5)])
    third, _ = run(first.pending[1], budget=100, answers=[
        google(0.5), google(0.5), far_near, far_far, google(0.5), google(0.5),
    ])
    fourth, _ = run(third.pending[0], budget=100, answers=[google(0.5), google(0.5)])

    assert first.spent + second.spent + third.spent + fourth.spent == 14
    assert [second.pending, fourth.pending] == [[], []]


def test_a_journey_resolves_into_at_most_four_parts():
    """Counted across every press, not at any one of them.

    A press sends what it settled and queues what it owes; the far half is not
    split until someone asks for it, so the total is only visible at the end.
    """
    p = part()
    near, far = half_of(p, 5.0, 1), far_of(p, 5.0, 1)
    near_near, near_far = half_of(near, 2.0, 2), far_of(near, 2.0, 2)
    far_near, far_far = half_of(far, 2.0, 2), far_of(far, 2.0, 2)

    sent, queue = 0, [p]
    supply = {
        p: [google(0.5), google(0.5), near, far,
            google(0.5), google(0.5), near_near, near_far, google(0.5), google(0.5)],
        near_far: [google(0.5), google(0.5)],
        far: [google(0.5), google(0.5), far_near, far_far, google(0.5), google(0.5)],
        far_far: [google(0.5), google(0.5)],
    }
    while queue:
        head, queue = queue[0], queue[1:]
        outcome, _ = run(head, budget=100, answers=supply[head])
        sent += len(outcome.messages)
        queue = outcome.pending + queue

    assert sent == 4


def test_the_pending_part_is_a_value_a_test_can_build():
    """No exchange has to be replayed to test the second half of a journey."""
    standalone = Part(origin=(1.0, 45.0), destination=(2.0, 45.0), cost=0.0)
    outcome, asked = run(standalone, budget=100, answers=[])

    assert asked == []
    assert D.AVOID_TOLLS in outcome.messages[0].text


def test_the_decision_reaches_no_network():
    """Driven with no answers at all, it asks and stops rather than calling out."""
    outcome, asked = run(part(), budget=100, answers=[])

    assert len(asked) == 1
    assert outcome.messages, "it still produces something to send"
