"""Bounded model exploration at several independently reported depths."""
from .runner import run_check
from .scenario import fingerprint, validate_scenario


def sweep_depths(scenario, depths, max_states=5000, *, profile=False, fixture=None, max_schedules=None):
    validate_scenario(scenario)
    if (not isinstance(depths,list) or not 1 <= len(depths) <= 8
            or any(type(d) is not int or not 0 <= d <= 64 for d in depths)
            or len(set(depths)) != len(depths)):
        raise ValueError("select 1..8 distinct depths between 0 and 64")
    if type(max_states) is not int or max_states < 1 or max_states * len(depths) > 200000:
        raise ValueError("total requested state budget must be 1..200000")
    if max_schedules is not None and not fixture:
        raise ValueError("--max-schedules requires --fixture")
    rows = []
    for depth in sorted(depths):
        def check():
            return run_check(scenario, max_depth=depth, max_states=max_states,
                             fixture=fixture, max_schedules=max_schedules)
        if profile:
            from .profiling import profile_check
            report = profile_check(check)
        else:
            report = check()
        rows.append({"depth": depth, "status": report["status"], "bounds": report["bounds"],
                     "coverage": report["coverage"], "versions": report["versions"],
                     "candidate_events": report["candidate"]["events"] if report["candidate"] else None})
        if fixture is not None:
            rows[-1].update(model_status=report["model_status"], fixture=report["fixture"])
        if profile:
            rows[-1]["measurements"] = report["measurements"]
    return {"scenario_sha256": fingerprint(scenario), "results": rows,
            "execution_scope": "bundled_handlers" if fixture is not None else "model_only",
            "source_verification": "installed_sources_reported_per_depth" if fixture is not None else "not_checked",
            "any_incomplete": any(r["status"] == "incomplete" for r in rows),
            "any_failure": any(r["status"] not in ("no_interaction_within_bound", "incomplete") for r in rows),
            "scope": ("Explicit bundled handlers: each depth retains separate model and handler-prefix coverage, installed source identities and any diagnostic replays outside those counts. Input is a scenario, not a source-pinned witness. "
                      if fixture is not None else "Independent model-only searches; no handler execution. ") +
                     "Absence at a shallow depth is not safety. No imported code or publishable witnesses. State and schedule budgets apply independently per depth, not a hard time/memory guarantee."}
