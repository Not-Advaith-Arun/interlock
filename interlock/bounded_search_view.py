"""Bounded model metadata, explicitly separate from handlers and safety claims."""
from .report_cards import render_report


def search_metadata(report,kind):
    if report['execution_scope']!='model_only':
        raise ValueError('bounded search HTML requires model-only results')
    source=report['cases'] if kind=='batch' else report['results']
    rows=[]
    for number,entry in enumerate(source,1):
        result=entry['report'] if kind=='batch' else entry
        rows.append({'ordinal':number,'scenario_sha256':entry['scenario_sha256'] if kind=='batch' else report['scenario_sha256'],
                     'status':result['status'],'bounds':result['bounds'],'coverage':result['coverage']})
    return {'format':'interlock-bounded-model-review-v1','kind':kind,'execution_scope':'model_only',
            'source_verification':'not_checked','any_incomplete':report['any_incomplete'],
            'any_failure':report['any_failure'],'requested_state_budget':sum(row['bounds']['max_states'] for row in rows),'results':rows,
            'scope':'Independent bounded model searches only. Classification, requested bounds and coverage metadata are retained; scenario titles/paths, event names, candidate schedules, branch states and measurements are omitted. No handlers, source pin verification, joint-state exploration, behavioral equivalence or general safety proof. Shallow absence is not safety and incomplete work never passes. State ceilings are not hard time/memory guarantees. Use ordinary JSON or the batch --report for full search evidence.'}


def render_search(report,kind):
    data=search_metadata(report,kind)
    rows=[{'group':entry['status'],'cells':[entry['ordinal'],entry['scenario_sha256'],entry['status'],entry['bounds']['max_depth'],entry['bounds']['max_states'],entry['coverage']['termination_reason'],entry['coverage']['states_explored'],entry['coverage']['depth_reached']]} for entry in data['results']]
    return render_report('Interlock bounded '+('scenario batch' if kind=='batch' else 'depth sweep'),data['scope'],
        ['Input/depth ordinal','Scenario identity','Observed model classification','Requested depth','Requested states','Termination reason','Explored states','Reached depth'],rows,payload=data,
        summary=('Incomplete model search remains unknown. ' if data['any_incomplete'] else 'Bounded model classifications only. ')+'No handler execution or source verification; failures and absence within bounds are not general safety judgments.')
