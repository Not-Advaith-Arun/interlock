"""Explicit reference starter manifests; expectations are frozen, never learned by search."""
from .fixture import fixture_scenario, fixture_catalog
from .scenario import validate_scenario, fingerprint
from .report_cards import render_report

REFERENCE_EXPECTATIONS={row['name']:row['expected_status']for row in fixture_catalog()['fixtures']}


def case_template(names):
    if (not isinstance(names,list) or not 1<=len(names)<=8 or any(not isinstance(name,str)or name not in REFERENCE_EXPECTATIONS for name in names)or len(set(names))!=len(names)):
        raise ValueError('select 1..8 distinct bundled reference fixtures')
    cases=[]
    for name in names:
        scenario=fixture_scenario(name)
        validate_scenario(scenario)
        cases.append({'id':name,'expected_status':REFERENCE_EXPECTATIONS[name],'scenario':scenario})
    return {'format':'interlock-model-cases-v1','cases':cases}


def render_case_template(manifest):
    rows=[{'group':case['expected_status'],'cells':[case['id'],case['scenario']['model'],case['expected_status'],fingerprint(case['scenario'])]}for case in manifest['cases']]
    return render_report('Interlock reference regression draft','Starter declarations from explicitly selected bundled references only. Expectations come from frozen reference contracts, never observed search results. Full bundled scenario definitions are included in this page and its native JSON download. Download that manifest and run check-cases separately with explicit bounds; revise expectations deliberately when changing scenarios. No model search, source-pin verification or handler execution occurred during drafting. No independent historical evaluation or safety conclusion; expected branch failures matching a classification do not make them safe.',
        ['Reference case ID','Declared model','Frozen expected classification','Scenario identity'],rows,payload=manifest,
        summary=f"Drafted {len(rows)} bundled reference cases without search or handler execution. Download report JSON is a native check-cases manifest, not evidence of a passing run. Incomplete searches never pass; expected failures are not safety success.")
