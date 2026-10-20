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
    before, after = one["trace"][-1]["outcomes"], two["trace"][-1]["outcomes"]
    changes = [{"version": key, "left": before[key], "right": after[key]}
               for key in ("base","left","right","merged") if before[key] != after[key]]
    return {"scenario_sha256": identity, "left_events": left["events"], "right_events": right["events"],
            "common_event_prefix_length": shared,
            "identical_events": left["events"] == right["events"], "final_outcome_changes": changes,
            "left_interaction_reproduced": one["interaction_reproduced"],
            "right_interaction_reproduced": two["interaction_reproduced"],
            "source_verification": "not_checked", "execution_scope": "model_only",
            "scope": "Both witnesses validated and replayed in the same declared model. Event-prefix and final outcomes only, not alignment of causally equivalent events, executable handler evidence, shortest failure or complete branch safety."}
