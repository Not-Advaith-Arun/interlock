"""Bounded one-event deletion diagnostics, separate from witness publication."""

from .engine import replay, replay_witness
from .scenario import fingerprint
from .fixture import replay_fixture, validate_witness_fixture


def reduce_witness(witness, max_attempts=500, *, fixture=None):
    if type(max_attempts) is not int or not 1 <= max_attempts <= 10000:
        raise ValueError("max_attempts must be an integer between 1 and 10000")
    current = replay_witness(witness)
    if not current["interaction_reproduced"]:
        raise ValueError("input does not reproduce a schedule-local merge interaction")
    source_verification = "not_checked"
    actual = None
    mismatch = None
    if fixture:
        source_verification = validate_witness_fixture(witness, fixture)
        if source_verification != "verified":
            raise ValueError("handler-backed reduction requires a source-pinned v2 witness")
        actual = replay_fixture(witness["scenario"], witness["events"], fixture)
        if not actual["agreement"]:
            mismatch = actual
        elif not actual["interaction_reproduced"]:
            raise ValueError("trusted handlers do not reproduce the input interaction")
    original = list(witness["events"])
    events = list(original)
    attempts = 0
    index = 0
    while index < len(events) and attempts < max_attempts and mismatch is None:
        candidate = events[:index] + events[index + 1:]
        attempts += 1
        try:
            checked = replay(witness["scenario"], candidate)
        except ValueError:
            # Removing an enabling event can make a later event illegal.
            index += 1
            continue
        candidate_actual = replay_fixture(witness["scenario"], candidate, fixture) if fixture else None
        if candidate_actual is not None and not candidate_actual["agreement"]:
            mismatch = candidate_actual
            break
        if checked["interaction_reproduced"]:
            events = candidate
            current = checked
            actual = candidate_actual
            index = 0
        else:
            index += 1
    complete = index == len(events) and mismatch is None
    return {"format": "interlock-trace-reduction-v1",
            "input_sha256": fingerprint(witness),
            "scenario_sha256": current["scenario_sha256"],
            "original_events": original, "reduced_events": events,
            "removed_events": len(original) - len(events), "attempts": attempts,
            "max_attempts": max_attempts,
            "status": "fixture_mismatch" if mismatch is not None else "complete" if complete else "budget_exhausted",
            "one_event_deletion_minimal": complete,
            "execution_scope": "bundled_handlers" if fixture else "model_only",
            "source_verification": source_verification, "fixture": fixture,
            "handler_replay": actual, "first_mismatch": mismatch,
            "replay": current,
            "scope": "Diagnostic only: preserves interaction on this sequence, not full branch safety. "
                     "One-event deletion minimality is not globally shortest or bounded search completeness. "
                     "This is not a publishable witness. " +
                     ("Pinned allowlisted sources verified and trusted handlers checked for legal deletion candidates; no arbitrary source execution."
                      if fixture else "Pinned sources and actual handlers are not checked.")}
