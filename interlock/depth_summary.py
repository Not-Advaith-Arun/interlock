"""Preserve shallow recorded completion and deeper incompleteness separately."""
from .depth_comparison import _grid
from .report_cards import render_report


def summarize_depths(report):
    grid=_grid(report);cases=[]
    for key in sorted({key for key,depth in grid}):
        cells=sorted((depth,row)for(id,depth),row in grid.items()if id==key)
        complete=[depth for depth,row in cells if row['coverage']['complete_up_to_depth']]
        incomplete=[depth for depth,row in cells if row['verdict']=='incomplete'];highest=max(complete)if complete else None
        classes={}
        for depth,row in cells:classes.setdefault(row['observed_status'],[]).append(depth)
        cases.append({'id':key,'scenario_sha256':cells[0][1]['scenario_sha256'],'expected_status':cells[0][1]['expected_status'],'requested_depths':[depth for depth,row in cells],
            'recorded_complete_depths':complete,'highest_recorded_complete_depth':highest,'incomplete_depths':incomplete,'deeper_incomplete_depths':[d for d in incomplete if highest is None or d>highest],
            'unexpected_depths':[d for d,row in cells if row['verdict']=='unexpected'],'recorded_classifications':classes})
    return {'format':'interlock-depth-summary/v1','recorded_grid_status':report['status'],'cases':cases,'execution_scope':'none','source_verification':'not_checked',
        'scope':'Complete retained matrix structurally validated before summarizing each explicit case. All requested, caller-recorded complete, incomplete and unexpected depths remain separate. Highest recorded complete depth is one supplied claim, not interpolation, convergence, optimal bound, authenticity or fresh execution evidence. Deeper incomplete results never become passed because a shallow row matched expectation; expected unsafe classifications are not safety approval. No new search, replay, handler/source-pin checks or witness publication occurred. Inspect original recorded grids for detailed counters; no timing/performance comparison.'}


def render_depth_summary(report):
    rows=[{'group':'Has recorded incomplete bounds'if r['incomplete_depths']else'No recorded incomplete row','cells':[r['id'],', '.join(map(str,r['requested_depths'])),r['highest_recorded_complete_depth']if r['highest_recorded_complete_depth']is not None else'None',', '.join(map(str,r['incomplete_depths']))or'None',', '.join(map(str,r['unexpected_depths']))or'None']}for r in report['cases']]
    return render_report('Interlock retained depth coverage summary',report['scope'],['Case ID','Requested depths','Highest caller-recorded complete depth','Recorded incomplete depths','Recorded unexpected depths'],rows,payload=report,summary=f"{len(rows)} explicit recorded cases; grid status {report['recorded_grid_status']}. Shallow recorded completion never clears deeper incompleteness. No new execution or safety verification.")
