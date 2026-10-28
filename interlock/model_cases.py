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


def compare_case_manifests(left,right):
    from .scenario import fingerprint
    a=validated_cases(left);b=validated_cases(right);first={row['id']:(i,row)for i,row in enumerate(a,1)};second={row['id']:(i,row)for i,row in enumerate(b,1)}
    rows=[]
    for key in sorted(first.keys()|second.keys()):
        one=first.get(key);two=second.get(key)
        old={'ordinal':one[0],'expected_status':one[1]['expected_status'],'scenario_sha256':fingerprint(one[1]['scenario'])}if one else None
        new={'ordinal':two[0],'expected_status':two[1]['expected_status'],'scenario_sha256':fingerprint(two[1]['scenario'])}if two else None
        rows.append({'id':key,'presence':'both'if one and two else'left_only'if one else'right_only','left':old,'right':new,'expectation_changed':bool(old and new and old['expected_status']!=new['expected_status']),'scenario_changed':bool(old and new and old['scenario_sha256']!=new['scenario_sha256'])})
    return {'format':'interlock-case-manifest-comparison-v1','left_cases':len(a),'right_cases':len(b),'cases':rows,
            'scope':'Complete structural validation of both manifests only. Declared expectation changes are separate from scenario-identity and order changes; no expected/observed result, search, source-pin check or handler execution. Private scenario names/configuration omitted. Neither label changes nor identical definitions establish passing behavior, safety, authenticity or an approved test update.'}


def render_manifest_comparison(report):
    from .report_cards import render_report
    rows=[{'group':row['presence'],'cells':[row['id'],row['left']['expected_status']if row['left']else'Absent',row['right']['expected_status']if row['right']else'Absent',row['expectation_changed'],row['scenario_changed']]}for row in report['cases']]
    return render_report('Interlock regression declaration comparison',report['scope'],['Case ID','Left expectation','Right expectation','Expectation differs','Scenario identity differs'],rows,payload=report,summary='Declared expectations, scenario identities and case presence compared without execution. Changing an expected classification is not evidence of a passing or safer implementation.')


def select_cases(manifest, selected_ids):
    """Narrow explicit declarations without execution or inferred expectations."""
    if selected_ids is None:
        raise ValueError('select explicit existing case IDs')
    from copy import deepcopy
    return {'format':manifest.get('format') if isinstance(manifest,dict) else None,
            'cases':deepcopy(validated_cases(manifest,selected_ids))}


def render_case_selection(manifest, original_count, *, interactive=False):
    from .scenario import fingerprint
    from .report_cards import render_report
    rows=[{'group':case['expected_status'],'cells':[case['id'],case['scenario']['model'],case['expected_status'],fingerprint(case['scenario'])]}for case in manifest['cases']]
    return render_report('Interlock selected regression declarations',
        'All input declarations validated, including omitted cases. Selected cases keep their original order, complete scenario definitions and caller-declared expectations. Full private selected configuration is embedded in this page and native JSON download. Run check-cases separately with explicit bounds. No search, source-pin check, handlers, observed outcomes or safety conclusion. Omitted declarations are not included or assessed by a later selected run.',
        ['Case ID','Declared model','Declared expectation','Scenario identity'],rows,payload=manifest,
        summary=f"Selected {len(rows)} of {original_count} declarations; {original_count-len(rows)} omitted. Download report JSON includes all shown scenarios. Choose explicit cases below for a separate subset. No execution or safety approval."if interactive else f"Selected {len(rows)} of {original_count} declarations; {original_count-len(rows)} omitted. Download report JSON is a runnable manifest, not a passing-run report. Incomplete searches never pass.",extra_script=__import__('pathlib').Path(__file__).with_name('ui').joinpath('case_picker.js').read_text()if interactive else'')


def combine_case_manifests(left,right):
    """Combine explicit declarations, never resolve changed expectations by guessing."""
    from copy import deepcopy
    a=validated_cases(left);b=validated_cases(right);combined={case['id']:case for case in a}
    for case in b:
        if case['id']in combined and combined[case['id']]!=case:
            raise ValueError('same case ID has conflicting scenario or expectation; review both declarations explicitly')
        combined.setdefault(case['id'],case)
    result={'format':'interlock-model-cases-v1','cases':deepcopy(list(combined.values()))}
    validated_cases(result)  # Combined cap and canonical scenario uniqueness still apply.
    return result


def render_case_combination(manifest,input_count):
    from .scenario import fingerprint
    from .report_cards import render_report
    rows=[{'group':case['expected_status'],'cells':[case['id'],case['scenario']['model'],case['expected_status'],fingerprint(case['scenario'])]}for case in manifest['cases']]
    return render_report('Interlock combined regression declarations',
        'Both complete manifests structurally validated. Identical same-ID declarations coalesced; conflicting same-ID expectations/scenarios refused instead of overwritten. Original left order then new right IDs retained, with at most8 distinct canonical scenarios. Full private declared configurations are embedded in this page and native download. No search, handlers, source verification or observed outcome; combining expected labels is not passing-run evidence or safety approval. Run check-cases separately with explicit bounds.',
        ['Case ID','Declared model','Declared expectation','Scenario identity'],rows,payload=manifest,
        summary=f"Combined {input_count} supplied declarations into {len(rows)} cases; {input_count-len(rows)} identical same-ID declarations coalesced. Native manifest download is runnable, not a test result. Incomplete searches never pass.")
