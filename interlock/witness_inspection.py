"""Inspect witness identity before choosing any replay execution mode."""
from .engine import validate_witness
from .scenario import fingerprint


def inspect_witness(witness):
    validate_witness(witness)
    return {"format":"interlock-witness-inspection-v1", "witness_format":witness["format"],
            "witness_canonical_sha256":fingerprint(witness),
            "scenario_sha256":witness["scenario_sha256"], "model":witness["scenario"]["model"],
            "event_count":len(witness["events"]), "distinct_event_names":len(set(witness["events"])),
            "source_binding_recorded":"fixture" in witness,
            "execution_scope":"none", "source_verification":"not_checked", "event_legality":"not_checked",
            "scope":"Envelope, configuration and canonical fingerprints checked without model state transitions or bundled application handlers. Recorded source binding is untrusted metadata: installed source identity, event legality, outcomes and branch safety are not checked. Use explicit replay for those checks. Scenario title, source paths and event names omitted; counts and fingerprints may still be sensitive."}
