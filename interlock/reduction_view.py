"""Captured model reduction decisions without scenario, events, states or handlers."""
from .report_cards import render_report


def reduction_metadata(result):
    fields=('input_sha256','scenario_sha256','removed_events','attempts','max_attempts','decisions','max_diagnostics','omitted_decisions','decision_scope','status','one_event_deletion_minimal','execution_scope','source_verification','scope')
    return {'format':'interlock-reduction-review/v1',**{key:result[key]for key in fields},'original_event_count':len(result['original_events']),'reduced_event_count':len(result['reduced_events'])}


def render_reduction(result):
    data=reduction_metadata(result)
    rows=[{'group':decision['outcome'],'cells':[decision['attempt'],decision['removed_index'],decision['candidate_length'],decision['outcome']]}for decision in data['decisions']]
    return render_report('Interlock model trace reduction',data['scope']+' '+data['decision_scope']+' Event identifiers, scenario and replay states are omitted. This metadata cannot be replayed or published as a witness. No handlers or pinned sources verified.',
        ['Attempt','Current sequence removal index','Candidate event count','Captured outcome'],rows,payload=data,
        summary=f"Captured {data['status']}: {data['original_event_count']} to {data['reduced_event_count']} events, {data['attempts']} of {data['max_attempts']} attempts; {data['omitted_decisions']} decisions omitted. One-event deletion minimal: {data['one_event_deletion_minimal']}. Budget exhaustion remains incomplete, not a passing safety result. Minimality is not globally shortest or full search completeness.")
