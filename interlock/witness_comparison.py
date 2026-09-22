"""Compare validated model replays of two schedules, without executing code."""
from .engine import replay_witness
from .scenario import fingerprint


def compare_witnesses(left, right, *, fixture=None):
    one, two = replay_witness(left), replay_witness(right)
    identity = fingerprint(left["scenario"])
    if identity != fingerprint(right["scenario"]):
        raise ValueError("witnesses must describe the same scenario")
    provenance = None
    if fixture is not None:
        from .fixture import validate_witness_fixture, replay_fixture
        # Validate both bindings before constructing either set of handlers.
        provenance = {"left": validate_witness_fixture(left, fixture),
                      "right": validate_witness_fixture(right, fixture)}
        one = replay_fixture(left["scenario"], left["events"], fixture)
        two = replay_fixture(right["scenario"], right["events"], fixture)
    def outcomes(frame):
        return frame["observed"] if fixture is not None else frame["outcomes"]
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
                    "outcomes": outcomes(frame)}
        divergence = {"event_number": shared + 1, "left": side(left, one), "right": side(right, two)}
    before, after = outcomes(one["trace"][-1]), outcomes(two["trace"][-1])
    changes = [{"version": key, "left": before[key], "right": after[key]}
               for key in ("base","left","right","merged") if before[key] != after[key]]
    return {"scenario_sha256": identity, "left_events": left["events"], "right_events": right["events"],
            "common_event_prefix_length": shared,
            "identical_events": left["events"] == right["events"], "first_event_difference": divergence,
            "final_outcome_changes": changes,
            "left_interaction_reproduced": one["interaction_reproduced"],
            "right_interaction_reproduced": two["interaction_reproduced"],
            "source_verification": provenance if fixture is not None else "not_checked",
            "execution_scope": "bundled_handlers" if fixture is not None else "model_only",
            **({"fixture": fixture, "model_agreement": {"left": one["agreement"], "right": two["agreement"]}}
               if fixture is not None else {}),
            "scope": ("Explicit trusted bundled handlers; observed outcomes and per-side source binding/model agreement reported. Imported paths are inert. "
                      if fixture is not None else "Both witnesses validated and replayed in the same declared model; no handler execution. ") +
                     "First unequal event (or end of one schedule), with each side after that event or at its retained terminal state, plus final outcomes. Ordinal comparison only, not causal alignment, shortest failure, full search or general branch safety."}
