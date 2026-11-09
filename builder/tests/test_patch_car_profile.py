"""The locked gate weight must survive the line that sets the turn weight.

process_turn sets `turn.weight = turn.duration` before the routability block.
A weight raised above that line is lost, and the locked gate is open again.
"""

import pytest

import patch_car_profile as p


PROFILE = (
    "function process_node(profile, node, result, relations)\n"
    "  local barrier = node:get_value_by_key('barrier')\n"
    "  if barrier then\n"
    "      local barrier_penalty = profile.barrier_penalties[barrier]\n"
    "  end\n"
    "end\n"
    "\n"
    "function process_turn(profile, turn)\n"
    "  for _, obs in pairs(obstacle_map:get(turn.from, turn.via)) do\n"
    "    turn.duration = turn.duration + obs.duration\n"
    "  end\n"
    "  turn.weight = turn.duration\n"
    "  if profile.properties.weight_name == 'routability' then\n"
    "  end\n"
    "end\n"
)


def test_locked_gate_weight_is_read_in_the_stock_obstacle_loop():
    patched = p.patch(PROFILE, [], {7}, {7})

    loop = patched.index("for _, obs in pairs(obstacle_map:get(turn.from, turn.via)) do")
    read = patched.index("obstacle_weight = math.max(obstacle_weight, obs.weight)")
    assert patched.index("local obstacle_weight = 0") < loop < read
    assert read < patched.index("turn.duration = turn.duration + obs.duration")
    assert patched.count("obstacle_map:get(") == 1


def test_locked_gate_weight_is_raised_after_the_turn_weight_is_set():
    patched = p.patch(PROFILE, [], {7}, {7})

    raised = patched.index("turn.weight = math.max(turn.weight, obstacle_weight)")
    assert patched.index("turn.weight = turn.duration") < raised
    assert raised < patched.index("if profile.properties.weight_name == 'routability'")


def test_a_profile_without_the_routability_block_is_refused():
    profile = PROFILE.replace(
        "  if profile.properties.weight_name == 'routability' then\n", "")

    with pytest.raises(p.Abort, match="expected exactly one"
                       " \"if profile.properties.weight_name == 'routability' then\""):
        p.patch(profile, [], {7}, {7})
