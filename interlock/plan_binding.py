"""Inspect retained observations against explicit bounded run intent, without executing."""
from .depth_template import consume_depth_plan
from .depth_comparison import _grid
from .depth_binding import inspect_depth_binding
from .report_cards import render_report


def inspect_plan_binding(manifest,plan,report):
    cases,depths,states=consume_depth_plan(manifest,plan)
    grid=_grid(report)
    binding=inspect_depth_binding(manifest,report,cases)
    missing=sorted(set(depths)-set(report['depths']));extra=sorted(set(report['depths'])-set(depths))
    recorded_states=next(iter(grid.values()))['bounds']['max_states']
    return {'format':'interlock-planned-run-binding/v1','matches_plan':binding['matches_declarations']and not missing and not extra and states==recorded_states,
            'manifest_sha256':plan['manifest_sha256'],'planned_case_ids':list(cases),'planned_depths':list(depths),'planned_max_states':states,
            'missing_depths':missing,'extra_depths':extra,'recorded_max_states':recorded_states,'state_budget_matches':states==recorded_states,
            'declaration_binding':binding,'recorded_status':report['status'],'recorded_any_incomplete':report['any_incomplete'],
            'execution_scope':'none','source_verification':'not_checked',
            'scope':'Original plan guard, complete declarations and every retained grid cell validate before binding selected case identities/expectations, original declaration totals, exact requested depth set and uniform per-cell state cap. Input array order does not prescribe traversal order. Missing/extra depths and different budgets stay explicit. Matching plan intent does not authenticate execution, origin, witnesses, freshest results, source pins or safety; a caller can fabricate matching report claims. Original incomplete/unexpected verdicts remain unchanged and expected unsafe observations remain unsafe. Exit0 means only that retained claims match declared intent. No search, handlers, replay, plan/declaration edits or guard refresh.'}


def render_plan_binding(result):
    rows=[{'group':'Declaration matches'if r['matches_declaration']else'Declaration mismatch','cells':[r['id'],r['depth'],', '.join(r['differences'])or'Identity/expectation match',r['recorded']['observed_status']if r['recorded']else'Missing']}for r in result['declaration_binding']['cells']]
    rows +=[{'group':'Missing requested depth','cells':['All planned cases',d,'No retained depth','Unknown']}for d in result['missing_depths']]
    return render_report('Interlock bounded plan result handoff',result['scope'],['Case ID','Depth','Intent binding','Recorded classification'],rows,payload=result,
                         summary=f"Plan intent matches: {result['matches_plan']}. State cap matches: {result['state_budget_matches']}; missing depths {result['missing_depths']}, extra depths {result['extra_depths']}. Retained status stays {result['recorded_status']}; no cases executed.")
