"""Explicit partial schedule execution, distinct from full replay output paging."""
from .engine import replay, validate_witness
from .fixture import replay_fixture, validate_witness_fixture
from .scenario import fingerprint


def replay_prefix(witness, through_step, *, fixture=None, require_pin=False):
    validate_witness(witness)
    if type(through_step) is not int or not 0 <= through_step <= len(witness["events"]):
        raise ValueError("through step must be0..witness event count")
    if require_pin and fixture is None:
        raise ValueError("source pin requirement needs a fixture")
    provenance = "not_checked"
    if fixture is not None:
        provenance = validate_witness_fixture(witness, fixture)
        if require_pin and provenance != "verified":
            raise ValueError("source-pinned witness required by --require-pin")
    events = witness["events"][:through_step]
    result = replay_fixture(witness["scenario"], events, fixture) if fixture is not None else replay(witness["scenario"], events)
    return {"format": "interlock-prefix-replay-v1", "witness_sha256": fingerprint(witness),
            "original_event_count": len(witness["events"]), "executed_event_count": through_step,
            "remaining_event_count": len(witness["events"])-through_step,
            "complete_witness_executed": through_step == len(witness["events"]),
            "execution_scope": "bundled_handlers" if fixture is not None else "model_only",
            "source_verification": provenance, "result": result,
            "scope": "Original envelope/configuration/fingerprints validated; selected source binding checked before any chosen handlers. Only this prefix executed. Its outcomes/verdict do not describe the unexecuted suffix: remaining event legality/outcomes and full-witness interaction are not checked. No publishable witness, shortest-failure proof, full search or general branch safety established. Output includes selected trace states and may be private."}
