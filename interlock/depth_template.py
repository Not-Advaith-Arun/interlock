"""Explicit bounded run intent bound to unchanged complete declarations."""
from pathlib import Path
from .model_cases import validated_cases
from .scenario import fingerprint
from .case_depths import validate_depth_budget
from .report_cards import render_report


def depth_template(manifest):
    cases=validated_cases(manifest)
    return {'plan':{'format':'interlock-case-depth-plan/v1','manifest_sha256':fingerprint(manifest),'case_ids':[],'depths':[],'max_states':5000},'cases':[{'id':row['id'],'scenario_sha256':fingerprint(row['scenario']),'expected_status':row['expected_status']}for row in cases],
        'scope':'Explicit bounded model-run intent only. Every declaration validates, including cases later omitted. Choose case IDs,1..8 distinct depths0..64 and a uniform per-cell state budget with total requested budget at most200000. Native check-case-depths --plan FILE requires the same complete canonical manifest before any search. No model, handler, source pin, run report or witness produced here; metadata hashes are consistency guards, not authenticity, execution or safety evidence. Actual execution remains model-only with independent bounds/coverage/incomplete verdicts and no hard wall-time/memory guarantee.'}


def consume_depth_plan(manifest,plan):
    if(not isinstance(plan,dict)or set(plan)!={'format','manifest_sha256','case_ids','depths','max_states'}or plan['format']!='interlock-case-depth-plan/v1'or plan['manifest_sha256']!=fingerprint(manifest)):
        raise ValueError('depth plan belongs to different or changed complete declarations')
    if not isinstance(plan['case_ids'],list):raise ValueError('depth plan requires explicit case IDs')
    cases=validated_cases(manifest,plan['case_ids']);validate_depth_budget(plan['depths'],plan['max_states'],len(cases))
    return plan['case_ids'],plan['depths'],plan['max_states']


def resume_depth_plan(manifest,plan):
    from copy import deepcopy
    consume_depth_plan(manifest,plan)
    result=depth_template(manifest)
    result['plan']=deepcopy(plan);result['resumed']=True
    order={key:i for i,key in enumerate(plan['case_ids'])}
    result['cases']=sorted(result['cases'],key=lambda row:(0,order[row['id']])if row['id']in order else(1,row['id']))
    result['scope']='Explicit saved plan validated against the unchanged complete canonical manifest before reopening. Original chosen case/depth array order and budget are restored, without refreshing the manifest guard or performing search. These arrays express captured input selection, not a promise of execution order; native execution retains its canonical traversal. Changing declarations requires a fresh inspected plan. '+result['scope']
    return result


def render_depth_template(report):
    rows=[{'group':'Available declaration','cells':[r['id'],r['expected_status'],r['scenario_sha256']]}for r in report['cases']]
    return render_report('Interlock bounded run planner',report['scope'],['Case ID','Declared expected classification','Canonical scenario identity'],rows,payload=report,summary=('Original explicit run choices restored; no search or guard refresh performed.'if report.get('resumed')else'Choose explicit declarations, depths and state budgets. No cases run and no result or safety verdict produced.'),extra_script=Path(__file__).with_name('ui').joinpath('depth_planner.js').read_text())
