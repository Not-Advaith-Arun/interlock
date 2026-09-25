"""Explicit scenario collections with independent model search evidence."""
from .runner import run_check
from .scenario import fingerprint, validate_scenario


def check_many(scenarios, *, max_depth=8, max_states=25000):
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 8:
        raise ValueError("select1..8 distinct scenarios")
    if type(max_depth) is not int or not 0 <= max_depth <= 64:
        raise ValueError("max depth must be0..64")
    if type(max_states) is not int or max_states < 1 or max_states*len(scenarios) > 200000:
        raise ValueError("total requested state budget must be1..200000")
    for scenario in scenarios:
        validate_scenario(scenario)
    identities = [fingerprint(scenario) for scenario in scenarios]
    if len(set(identities)) != len(identities):
        raise ValueError("selected scenarios must have distinct canonical identities")
    rows = [{"scenario_sha256": identity, "report": run_check(scenario, max_depth=max_depth, max_states=max_states)}
            for identity, scenario in zip(identities, scenarios)]
    return {"format": "interlock-model-batch-v1", "cases": rows, "selected_scenarios": len(rows),
            "requested_state_budget": max_states*len(rows),
            "any_incomplete": any(row["report"]["status"] == "incomplete" for row in rows),
            "any_failure": any(row["report"]["status"] not in ("incomplete", "no_interaction_within_bound") for row in rows),
            "execution_scope": "model_only", "source_verification": "not_checked",
            "scope": "All scenario declarations validated before sequential independent model searches. Each case retains its full status, branch outcomes, candidate and coverage. No handlers, imported code or source pin verification executed, no witnesses published. Results concern each declared scenario within its own bounds; no joint-state search, behavioral equivalence or general safety proof. Sum of requested state ceilings is not a hard time/memory bound."}
