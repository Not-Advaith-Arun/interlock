"""Bounded model exploration at several independently reported depths."""
from .runner import run_check
from .scenario import fingerprint, validate_scenario


def sweep_depths(scenario, depths, max_states=5000, *, profile=False):
    validate_scenario(scenario)
    if (not isinstance(depths,list) or not 1 <= len(depths) <= 8
            or any(type(d) is not int or not 0 <= d <= 64 for d in depths)
            or len(set(depths)) != len(depths)):
        raise ValueError("select 1..8 distinct depths between 0 and 64")
    if type(max_states) is not int or max_states < 1 or max_states * len(depths) > 200000:
        raise ValueError("total requested state budget must be 1..200000")
    rows = []
    for depth in sorted(depths):
        def check():
            return run_check(scenario, max_depth=depth, max_states=max_states)
        if profile:
            from .profiling import profile_check
            report = profile_check(check)
        else:
            report = check()
        rows.append({"depth": depth, "status": report["status"], "bounds": report["bounds"],
                     "coverage": report["coverage"], "versions": report["versions"],
                     "candidate_events": report["candidate"]["events"] if report["candidate"] else None})
        if profile:
            rows[-1]["measurements"] = report["measurements"]
    return {"scenario_sha256": fingerprint(scenario), "results": rows,
            "execution_scope": "model_only", "source_verification": "not_checked",
            "any_incomplete": any(r["status"] == "incomplete" for r in rows),
            "any_failure": any(r["status"] not in ("no_interaction_within_bound", "incomplete") for r in rows),
            "scope": "Independent model-only searches at each bound; absence at a shallow depth is not safety. No imported code, pinned handlers or publishable witnesses. Budgets limit explored product states, not a hard time/memory guarantee."}
