"""Compare validated model replays of two schedules, without executing code."""
from .engine import replay_witness, validate_witness
from .scenario import fingerprint


def compare_witnesses(left, right, *, fixture=None, require_pin=False):
    if require_pin and fixture is None:
        raise ValueError("source pin requirement needs a fixture")
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
        if require_pin and any(value != "verified" for value in provenance.values()):
            raise ValueError("source-pinned witnesses required by --require-pin")
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


def compare_witness_structure(left, right):
    """Compare validated declarations and event positions without replay."""
    validate_witness(left)
    validate_witness(right)
    if fingerprint(left["scenario"]) != fingerprint(right["scenario"]):
        raise ValueError("witnesses must describe the same scenario")
    shared = 0
    for one, two in zip(left["events"], right["events"]):
        if one != two:
            break
        shared += 1
    identical = left["events"] == right["events"]
    return {"format": "interlock-witness-structure-comparison-v1", "scenario_sha256": left["scenario_sha256"],
            "left_sha256": fingerprint(left), "right_sha256": fingerprint(right),
            "left_event_count": len(left["events"]), "right_event_count": len(right["events"]),
            "identical_events": identical, "common_event_prefix_length": shared,
            "first_event_difference": None if identical else {"event_number": shared+1,
                "left_ended": shared == len(left["events"]), "right_ended": shared == len(right["events"])},
            "source_binding_recorded": {"left": "fixture" in left, "right": "fixture" in right},
            "execution_scope": "none", "source_verification": "not_checked", "event_legality": "not_checked",
            "scope": "Validated envelopes, scenario identity and ordinal event-sequence differences only. No model transitions, handlers or installed source verification. Event names, scenario titles and imported paths omitted; counts/fingerprints may still be sensitive. Event equality does not establish legality, source identity, behavioral equivalence, causal alignment, outcomes or branch safety. Choose explicit replay for execution evidence."}
