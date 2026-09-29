"""Only selected prefix outcome metadata, never private state or unexecuted suffix results."""
from .report_cards import render_report


def prefix_metadata(report):
    if report['execution_scope']!='model_only':raise ValueError('prefix cards require model-only replay')
    return {**{key:report[key]for key in ('witness_sha256','original_event_count','executed_event_count','remaining_event_count','complete_witness_executed','execution_scope','source_verification')},
        'format':'interlock-prefix-outcome-review-v1',
        'versions':[{ 'version':version,'passed':row['passed'],'violation_count':len(row['violations'])} for version,row in report['result']['outcomes'].items()],
        'scope':'Selected model prefix executed only; event names, branch state, traces and violation text omitted. No handler execution or pinned source verification. The unexecuted suffix has no outcome or legality claim; passing a prefix never establishes branch safety, full-witness interaction, shortest failure or exhaustive search. Use explicit JSON for detailed replay evidence.'}


def render_prefix(report):
    data=prefix_metadata(report)
    rows=[{'group':'Passed prefix'if row['passed']else'Failed prefix','cells':[row['version'],row['passed'],row['violation_count']]} for row in data['versions']]
    return render_report('Interlock selected prefix outcomes',data['scope']+f" Witness {data['witness_sha256']}. Executed {data['executed_event_count']} of {data['original_event_count']} events; {data['remaining_event_count']} remain unexecuted.",
        ['Declared version','Passed selected prefix','Violation count'],rows,payload=data,
        summary=f"Selected prefix: {data['executed_event_count']} executed, {data['remaining_event_count']} unexecuted events. Model-only results; no claim about the remaining suffix or general safety.")
