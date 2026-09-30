"""Captured actual bundled regression outcomes, not an external or historical safety study."""
from .suite import suite_summary
from .report_cards import render_report


def render_suite(report):
    data=suite_summary(report)
    rows=[{'group':case['verdict'],'cells':[case['fixture'],case['verdict'],case['expected_status'],case['observed_status'],case['model_coverage']['termination_reason'],(case['handler_coverage']or{}).get('termination_reason','Not reported'),case['handler_status']]}for case in data['cases']]
    return render_report('Interlock bundled regression suite',data['scope']+' Requested bounds '+str(data['bounds'])+'. This captured display does not execute further handlers or refresh verification. Detailed native reports remain separate.',
        ['Bundled fixture','Captured verdict','Expected model class','Observed model class','Model termination','Handler termination','Handler agreement status'],rows,payload=data,
        summary=f"Captured suite {data['status']}: {data['summary']['passed']} of {data['summary']['cases']} cases passed. Incomplete or disagreeing coverage never passes. Trusted bundled handlers only; no arbitrary-source, general safety or independent historical-case evaluation.")
