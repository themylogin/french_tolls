"""The three rules that decide whether a split is real.

Each of these was a live bug during the investigation that produced the step, so
they are tested rather than assumed:

  - the re-entry check passed everything, because a path's first node is the
    exit booth it starts from;
  - it then rejected real re-entries, because a plaza's other lanes are aliases
    and only the group representative was being looked for;
  - and the ranking was topped by a 522 EUR/h entry whose measured drive was
    0.36 min *faster* than going straight on -- snapping noise with no floor.
"""

import build_cost_cutting as cc


# --------------------------------------------------------------------------
# Re-entry
# --------------------------------------------------------------------------

class StubOsrm:
    """Answers with a canned node sequence, and counts nothing else."""

    workers = 1

    def __init__(self, drives):
        self.drives = drives

    def leg(self, a, b, want_nodes):
        answer = self.drives.get((a, b))
        if answer is None:
            return None, ()
        seconds, nodes = answer
        return seconds, (nodes if want_nodes else ())


# Gare "A" is a plaza of two lanes: 10 is the representative, 11 an alias.
# Gare "B" is a two-way booth: one node, 20, for both directions.
ENTER = {"A": (0.0, 0.0), "B": (1.0, 1.0), "Z": (2.0, 2.0)}
EXIT = {"A": (0.1, 0.1), "B": (1.0, 1.0), "Z": (2.1, 2.1)}
NODES_OF = {"A": {10, 11}, "B": {20}, "Z": {30}}


def measure(drives, legs):
    return cc.measure(StubOsrm(drives), legs, ENTER, EXIT, NODES_OF,
                      report_every=10 ** 9)


def test_a_leg_that_never_re_enters_is_dropped():
    # Leaves the plaza and drives to Z without crossing a booth of A again:
    # the cross-country case, where no second ticket was ever bought.
    drives = {(EXIT["A"], EXIT["Z"]): (600.0, [10, 900, 901, 30])}
    seconds, rejected = measure(drives, [(False, "A", "Z")])
    assert seconds[(False, "A", "Z")] is None
    assert rejected == 1


def test_the_starting_booth_does_not_prove_re_entry():
    # 10 is the node the leg starts from. On its own it proves nothing, and
    # testing the whole path rather than the path after the start made every
    # leg pass.
    drives = {(EXIT["A"], EXIT["Z"]): (600.0, [10, 901, 30])}
    seconds, _ = measure(drives, [(False, "A", "Z")])
    assert seconds[(False, "A", "Z")] is None


def test_re_entry_through_an_alias_lane_counts():
    # 11 is another lane of the same plaza. A driver re-entering may cross it,
    # and rejecting that discards a real manoeuvre.
    drives = {(EXIT["A"], EXIT["Z"]): (600.0, [10, 901, 11, 902, 30])}
    seconds, rejected = measure(drives, [(False, "A", "Z")])
    assert seconds[(False, "A", "Z")] == 600.0
    assert rejected == 0


def test_a_two_way_booth_crossed_twice_counts():
    drives = {(EXIT["B"], EXIT["Z"]): (600.0, [20, 901, 20, 902, 30])}
    seconds, rejected = measure(drives, [(False, "B", "Z")])
    assert seconds[(False, "B", "Z")] == 600.0
    assert rejected == 0


def test_a_first_leg_is_not_asked_to_re_enter():
    # It starts at an entrance; there is nothing to come back to.
    drives = {(ENTER["A"], EXIT["Z"]): (600.0, [])}
    seconds, rejected = measure(drives, [(True, "A", "Z")])
    assert seconds[(True, "A", "Z")] == 600.0
    assert rejected == 0


def test_an_unroutable_leg_is_not_counted_as_a_rejection():
    seconds, rejected = measure({}, [(False, "A", "Z")])
    assert seconds[(False, "A", "Z")] is None
    assert rejected == 0


# --------------------------------------------------------------------------
# The frontier
# --------------------------------------------------------------------------

def test_a_dearer_but_faster_candidate_is_kept():
    front = []
    assert cc.pareto_add(front, 1000, 600, ("a",))
    assert cc.pareto_add(front, 1200, 300, ("b",))
    assert len(front) == 2


def test_a_candidate_beaten_on_both_counts_is_dropped():
    front = []
    assert cc.pareto_add(front, 1000, 600, ("a",))
    assert not cc.pareto_add(front, 1100, 700, ("b",))
    assert len(front) == 1


def test_a_candidate_that_beats_another_on_both_counts_evicts_it():
    front = []
    cc.pareto_add(front, 1200, 700, ("a",))
    assert cc.pareto_add(front, 1000, 600, ("b",))
    assert [entry[2] for entry in front] == [("b",)]


def test_an_equal_candidate_does_not_displace_the_one_already_kept():
    front = []
    cc.pareto_add(front, 1000, 600, ("a",))
    assert not cc.pareto_add(front, 1000, 600, ("b",))
    assert [entry[2] for entry in front] == [("a",)]


# --------------------------------------------------------------------------
# Growing the sequences
# --------------------------------------------------------------------------

EDGES = {"A": {"G": 1000, "Z": 3000}, "G": {"Z": 1500}}


def test_a_split_is_found_where_the_tickets_are_cheaper():
    seconds = {
        (True, "A", "G"): 1000.0,
        (True, "A", "Z"): 2000.0,
        (False, "G", "Z"): 1100.0,
    }
    labels = cc.candidates_from("A", EDGES, seconds, lambda g: 60, 4)
    paths = {entry[2] for entry in labels["Z"]}
    assert ("A", "G", "Z") in paths
    fare = next(e[0] for e in labels["Z"] if e[2] == ("A", "G", "Z"))
    assert fare == 2500          # cheaper than the 3000 direct ticket


def test_a_stop_whose_onward_leg_never_re_enters_is_not_reachable():
    seconds = {
        (True, "A", "G"): 1000.0,
        (True, "A", "Z"): 2000.0,
        (False, "G", "Z"): None,   # dropped by the re-entry rule
    }
    labels = cc.candidates_from("A", EDGES, seconds, lambda g: 60, 4)
    assert all(entry[2] != ("A", "G", "Z") for entry in labels["Z"])


def test_the_stop_cost_lands_on_the_journey():
    seconds = {
        (True, "A", "G"): 1000.0,
        (True, "A", "Z"): 2000.0,
        (False, "G", "Z"): 1100.0,
    }
    labels = cc.candidates_from("A", EDGES, seconds, lambda g: 180, 4)
    entry = next(e for e in labels["Z"] if e[2] == ("A", "G", "Z"))
    assert entry[1] == 1000.0 + 1100.0 + 180


def test_the_stop_bound_is_honoured():
    edges = {"A": {"B": 1}, "B": {"C": 1}, "C": {"D": 1}}
    seconds = {(True, "A", "B"): 1.0, (False, "B", "C"): 1.0, (False, "C", "D"): 1.0}
    assert cc.candidates_from("A", edges, seconds, lambda g: 0, 1).get("D") in (None, [])
    assert cc.candidates_from("A", edges, seconds, lambda g: 0, 2)["D"]
