"""Compare validated model replays of two schedules, without executing code."""
from .engine import replay_witness
from .scenario import fingerprint


def compare_witnesses(left, right):
    one, two = replay_witness(left), replay_witness(right)
    identity = fingerprint(left["scenario"])
    if identity != fingerprint(right["scenario"]):
        raise ValueError("witnesses must describe the same scenario")
    shared = 0
    for a,b in zip(left["events"],right["events"]):
        if a != b:
            break
        shared += 1
    divergence = None
    if left["events"] != right["events"]:
        def side(witness, replayed):
            ended = shared == len(witness["events"])
            frame = replayed["trace"][shared if ended else shared + 1]
            return {"ended": ended, "event": None if ended else witness["events"][shared],
                    "outcomes": frame["outcomes"]}
        divergence = {"event_number": shared + 1, "left": side(left, one), "right": side(right, two)}
    before, after = one["trace"][-1]["outcomes"], two["trace"][-1]["outcomes"]
    changes = [{"version": key, "left": before[key], "right": after[key]}
               for key in ("base","left","right","merged") if before[key] != after[key]]
    return {"scenario_sha256": identity, "left_events": left["events"], "right_events": right["events"],
            "common_event_prefix_length": shared,
            "identical_events": left["events"] == right["events"], "first_event_difference": divergence,
            "final_outcome_changes": changes,
            "left_interaction_reproduced": one["interaction_reproduced"],
            "right_interaction_reproduced": two["interaction_reproduced"],
            "source_verification": "not_checked", "execution_scope": "model_only",
            "scope": "Both witnesses validated and replayed in the same declared model. First unequal event (or end of one schedule), with each side after that event or at its retained terminal state, plus final outcomes. This is ordinal comparison, not alignment of causally equivalent events, executable handler evidence, shortest failure or complete branch safety."}
