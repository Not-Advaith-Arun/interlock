"""Caller-authored model classification regressions, separate from safety claims."""
import re
from .model_batch import check_many

EXPECTED = {"merge_interaction_found", "no_interaction_within_bound", "baseline_failure", "branch_failure"}


def check_cases(manifest, *, max_depth=8, max_states=25000):
    if not isinstance(manifest, dict) or set(manifest) != {"format", "cases"} or manifest["format"] != "interlock-model-cases-v1":
        raise ValueError("expected interlock-model-cases-v1 with cases")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= 8:
        raise ValueError("select1..8 explicit model cases")
    identities = set()
    for case in cases:
        if (not isinstance(case, dict) or set(case) != {"id", "expected_status", "scenario"}
                or not isinstance(case["id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", case["id"])
                or not isinstance(case["expected_status"], str) or case["expected_status"] not in EXPECTED):
            raise ValueError("case requires distinct bounded id, supported expected_status and scenario; incomplete cannot be expected as passing")
        if case["id"] in identities:
            raise ValueError("duplicate model case ID")
        identities.add(case["id"])
    checked = check_many([case["scenario"] for case in cases], max_depth=max_depth, max_states=max_states)
    rows = []
    for case, result in zip(cases, checked["cases"]):
        observed = result["report"]["status"]
        verdict = "incomplete" if observed == "incomplete" else "passed" if observed == case["expected_status"] else "unexpected"
        rows.append({"id":case["id"],"expected_status":case["expected_status"],"verdict":verdict,**result})
    status = "incomplete" if any(row["verdict"] == "incomplete" for row in rows) else "unexpected" if any(row["verdict"] == "unexpected" for row in rows) else "passed"
    return {"format":"interlock-model-cases-report-v1","status":status,"cases":rows,
            "execution_scope":"model_only","source_verification":"not_checked",
            "scope":"Caller-supplied expected bounded model classifications only. Passing means observations matched expectations, including explicitly expected unsafe baseline/branch cases; it is not a safety verdict. Incomplete searches never pass and cannot be configured as expected success. Each full model report retains independent branch results and coverage. No handlers, source pins, imported code, witness publication or general safety proof."}
