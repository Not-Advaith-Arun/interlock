"""Fresh bounded model classifications with explicit caller-expectation scope."""
from .report_cards import render_report
from .model_cases import cases_summary


def render_case_run(report, *, max_depth, max_states):
    summary=cases_summary(report)
    summary['requested_bounds']={'max_depth':max_depth,'max_states_per_case':max_states}
    rows=[{'group':row['verdict'],'cells':[row['id'],row['observed_status'],row['expected_status'],row['verdict'],row['scenario_sha256']]} for row in summary['cases']]
    scope=(report['scope']+f" Requested bounds: depth {max_depth}, states per case {max_states}. Checked {len(rows)} of {summary['manifest_cases']} manifest cases; omitted {summary['omitted_cases']}. "
           +'This page and its JSON download contain classification metadata only. Use --report for full model search evidence. A passed expectation can describe an unsafe branch.')
    return render_report('Interlock bounded model case review',scope,['Case ID','Observed model classification','Caller expected classification','Expectation verdict','Scenario identity'],rows,payload=summary,summary=f"Model-only result: {report['status']}. Expected unsafe cases are not safety success; incomplete searches never pass. No handlers or source verification.")
