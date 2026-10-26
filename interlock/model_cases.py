"""Caller-authored model classification regressions, separate from safety claims."""
import re
from .model_batch import check_many

EXPECTED = {"merge_interaction_found", "no_interaction_within_bound", "baseline_failure", "branch_failure"}


def validated_cases(manifest, selected_ids=None):
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
    if selected_ids is not None:
        if (not isinstance(selected_ids,list) or not 1 <= len(selected_ids) <= 8
                or any(not isinstance(key,str) or key not in identities for key in selected_ids)
                or len(set(selected_ids)) != len(selected_ids)):
            raise ValueError("select1..8 distinct existing model case IDs")
    # Validate every declaration, including omitted cases, without running search.
    from .scenario import fingerprint, validate_scenario
    for case in cases:
        validate_scenario(case["scenario"])
    hashes = [fingerprint(case["scenario"]) for case in cases]
    if len(set(hashes)) != len(hashes):
        raise ValueError("selected scenarios must have distinct canonical identities")
    return [case for case in cases if selected_ids is None or case["id"] in selected_ids]


def check_cases(manifest, *, max_depth=8, max_states=25000, selected_ids=None):
    cases=validated_cases(manifest,selected_ids)
    checked = check_many([case["scenario"] for case in cases], max_depth=max_depth, max_states=max_states)
    rows = []
    for case, result in zip(cases, checked["cases"]):
        observed = result["report"]["status"]
        verdict = "incomplete" if observed == "incomplete" else "passed" if observed == case["expected_status"] else "unexpected"
        rows.append({"id":case["id"],"expected_status":case["expected_status"],"verdict":verdict,**result})
    status = "incomplete" if any(row["verdict"] == "incomplete" for row in rows) else "unexpected" if any(row["verdict"] == "unexpected" for row in rows) else "passed"
    return {"format":"interlock-model-cases-report-v1","status":status,"cases":rows,
            "execution_scope":"model_only","source_verification":"not_checked",
            "selected_case_ids":[case["id"] for case in cases],"manifest_cases":len(manifest["cases"]),
            "omitted_cases":len(manifest["cases"])-len(cases),
            "scope":"Omitted cases are not executed or assessed; all declarations still validate. Caller-supplied expected bounded model classifications only. Passing means observations matched expectations, including explicitly expected unsafe baseline/branch cases; it is not a safety verdict. Incomplete searches never pass and cannot be configured as expected success. Each full model report retains independent branch results and coverage. No handlers, source pins, imported code, witness publication or general safety proof."}


def cases_summary(report):
    """Summarize a freshly checked result; never reinterpret expectations as safety."""
    return {"format":"interlock-model-cases-summary-v1","status":report["status"],
            "execution_scope":report["execution_scope"],"source_verification":report["source_verification"],
            "manifest_cases":report["manifest_cases"],"omitted_cases":report["omitted_cases"],
            "cases":[{"id":row["id"],"scenario_sha256":row["scenario_sha256"],
                      "expected_status":row["expected_status"],"observed_status":row["report"]["status"],
                      "verdict":row["verdict"]} for row in report["cases"]],
            "scope":"Summary of this model-only run, not independently verified input. Full search reports, schedules and state details omitted; use --report for complete evidence. Expected failures matching classifications are not safety success. Omitted cases unassessed and incomplete searches never pass."}


def inspect_cases(manifest, *, selected_ids=None):
    from .scenario import fingerprint
    cases=validated_cases(manifest,selected_ids)
    return {'format':'interlock-model-cases-inspection-v1','manifest_cases':len(manifest['cases']),
            'omitted_cases':len(manifest['cases'])-len(cases),
            'cases':[{'id':case['id'],'model':case['scenario']['model'],
                      'scenario_sha256':fingerprint(case['scenario']),'expected_status':case['expected_status']}for case in cases],
            'scope':'Structural validation of every supplied case, including omitted declarations, only. Expected classifications are caller declarations, not observed outcomes. No search, source-pin verification, handlers or imported code executed. Private scenario names/configuration are omitted; metadata is not a runnable manifest, source authenticity or safety proof.'}


def render_case_inspection(report):
    from .report_cards import render_report
    rows=[{'group':c['expected_status'],'cells':[c['id'],c['model'],c['expected_status'],c['scenario_sha256']]}for c in report['cases']]
    return render_report('Interlock regression manifest inspection',report['scope'],['Case ID','Model','Declared expectation','Scenario identity'],rows,payload=report,summary=f"Inspected {len(rows)} of {report['manifest_cases']} declarations; {report['omitted_cases']} omitted from display. All declarations validated; no search or handler execution, no passing-run evidence.")
