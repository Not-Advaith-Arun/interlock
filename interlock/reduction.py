"""Bounded one-event deletion diagnostics, separate from witness publication."""

from .engine import replay, replay_witness
from .scenario import fingerprint


def reduce_witness(witness, max_attempts=500):
    if type(max_attempts) is not int or not 1 <= max_attempts <= 10000:
        raise ValueError("max_attempts must be an integer between 1 and 10000")
    current = replay_witness(witness)
    if not current["interaction_reproduced"]:
        raise ValueError("input does not reproduce a schedule-local merge interaction")
    original = list(witness["events"])
    events = list(original)
    attempts = 0
    index = 0
    while index < len(events) and attempts < max_attempts:
        candidate = events[:index] + events[index + 1:]
        attempts += 1
        try:
            checked = replay(witness["scenario"], candidate)
        except ValueError:
            # Removing an enabling event can make a later event illegal.
            index += 1
            continue
        if checked["interaction_reproduced"]:
            events = candidate
            current = checked
            index = 0
        else:
            index += 1
    complete = index == len(events)
    return {"format": "interlock-trace-reduction-v1",
            "input_sha256": fingerprint(witness),
            "scenario_sha256": current["scenario_sha256"],
            "original_events": original, "reduced_events": events,
            "removed_events": len(original) - len(events), "attempts": attempts,
            "max_attempts": max_attempts,
            "status": "complete" if complete else "budget_exhausted",
            "one_event_deletion_minimal": complete,
            "execution_scope": "model_only", "source_verification": "not_checked",
            "replay": current,
            "scope": "Diagnostic only: preserves interaction on this sequence, not full branch safety. "
                     "One-event deletion minimality is not globally shortest or bounded search completeness. "
                     "Pinned sources and actual handlers are not checked; this is not a publishable witness."}
