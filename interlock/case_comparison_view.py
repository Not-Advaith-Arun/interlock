"""A read-only recorded result matrix, distinct from fresh verification."""
from .report_cards import render_report


def render_case_comparison(report):
    rows=[]
    for row in report['cases']:
        before,after=row['before'],row['after']
        def label(value):
            return 'Absent' if value is None else value['observed_status']+' / expected '+value['expected_status']+' / '+value['verdict']
        rows.append({'group':'changed' if row['changed'] else 'unchanged','cells':[row['id'],label(before),label(after),', '.join(row['changes']) or 'None',
                    before['scenario_sha256'] if before else 'Absent',after['scenario_sha256'] if after else 'Absent']})
    return render_report('Interlock recorded case comparison',report['scope'],['Case ID','Before','After','Changed fields','Before scenario identity','After scenario identity'],rows,payload=report,summary="Recorded case comparison only. No new execution or safety verification; changed scenario identities remain separate from behavioral regressions.")
