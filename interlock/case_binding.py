"""Compare caller-recorded case identities to explicit declarations; no execution."""
from .model_cases import validated_cases
from .case_comparison import _index
from .scenario import fingerprint
from .report_cards import render_report


def inspect_case_binding(manifest,report,selected_ids=None):
    declared=validated_cases(manifest,selected_ids)
    recorded=_index(report,True)  # Every supplied row validates, including extras.
    expected={row['id']:{'scenario_sha256':fingerprint(row['scenario']),'expected_status':row['expected_status']}for row in declared}
    rows=[]
    for key in sorted(set(expected)|set(recorded)):
        a,b=expected.get(key),recorded.get(key)
        differences=['unexpected_record']if a is None else['missing_record']if b is None else[k for k in a if a[k]!=b[k]]
        rows.append({'id':key,'differences':differences,'matches_declaration':not differences,
            'declared':a,'recorded':b})
    return {'format':'interlock-case-binding-v1','matches_declarations':all(row['matches_declaration']for row in rows),'cases':rows,
        'manifest_cases':len(manifest['cases']),'selected_declarations':len(declared),'recorded_cases':len(recorded),
        'execution_scope':'none','source_verification':'not_checked',
        'scope':'Structural comparison of explicit declarations against caller-recorded case IDs, canonical scenario hashes and expected classifications. Missing/extra records remain visible. All manifest declarations and recorded classifications/bounds/coverage validate; hashes, outcomes and counters remain unauthenticated caller claims, not proof of execution, freshness, report origin, source verification or safety. Matching an expected unsafe result is not safety; no search, replay or handler execution occurred.'}


def render_case_binding(result):
    rows=[{'group':'Matches'if row['matches_declaration']else'Review mismatch','cells':[row['id'],', '.join(row['differences'])or'Identity and expectation match',row['recorded']['observed_status']if row['recorded']else'No recorded observation']}for row in result['cases']]
    return render_report('Interlock recorded case handoff',result['scope'],['Case ID','Declaration comparison','Caller-recorded classification'],rows,payload=result,
        summary=f"{sum(not row['matches_declaration']for row in result['cases'])} declaration mismatches. Matching identities do not authenticate a run or establish safety; no cases executed.")
