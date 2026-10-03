"""Compare complete caller-recorded case/depth grids without executing models."""
from .case_comparison import _index
from .report_cards import render_report


def _grid(report):
    if not isinstance(report,dict)or report.get('format')!='interlock-case-depths-v1':raise ValueError('expected complete case-depth grid report')
    depths=report.get('depths');results=report.get('results');selected=report.get('selected_cases');manifest=report.get('manifest_cases')
    if(not isinstance(depths,list)or not 1<=len(depths)<=8 or any(type(d)is not int or not 0<=d<=64 for d in depths)or len(set(depths))!=len(depths)
       or type(selected)is not int or type(manifest)is not int or not 1<=selected<=manifest<=8 or type(report.get('omitted_cases'))is not int or report['omitted_cases']!=manifest-selected
       or not isinstance(results,list)or len(results)!=len(depths)*selected):raise ValueError('incomplete or invalid recorded case/depth matrix')
    grouped={depth:[]for depth in depths}
    for row in results:
        if(not isinstance(row,dict)or type(row.get('depth'))is not int or row['depth']not in grouped):raise ValueError('recorded row names an undeclared depth')
        grouped[row['depth']].append(row)
    indexed={};identities=None;state_limits=set()
    for depth,rows in grouped.items():
        if len(rows)!=selected:raise ValueError('each requested depth needs every selected case exactly once')
        wrapped={'format':'interlock-model-cases-report-v1','cases':[{'id':r.get('id'),'scenario_sha256':r.get('scenario_sha256'),'expected_status':r.get('expected_status'),'verdict':r.get('verdict'),'report':{'status':r.get('observed_status'),'bounds':r.get('bounds'),'coverage':r.get('coverage')}}for r in rows]}
        checked=_index(wrapped,True);current={key:(r['scenario_sha256'],r['expected_status'])for key,r in checked.items()}
        if identities is not None and current!=identities:raise ValueError('case identities/expectations must stay fixed across recorded depths')
        identities=current
        for key,value in checked.items():
            if value['bounds']['max_depth']!=depth:raise ValueError('recorded bound disagrees with cell depth')
            state_limits.add(value['bounds']['max_states']);indexed[(key,depth)]=value
    if len(state_limits)!=1 or next(iter(state_limits))*len(indexed)>200000:raise ValueError('recorded grid exceeds or contradicts its uniform state budget')
    incomplete=any(r['verdict']=='incomplete'for r in indexed.values());unexpected=any(r['verdict']=='unexpected'for r in indexed.values())
    status='incomplete'if incomplete else'unexpected'if unexpected else'passed'
    if report.get('any_incomplete')is not incomplete or report.get('any_unexpected')is not unexpected or report.get('status')!=status:raise ValueError('recorded grid summary contradicts cell verdicts')
    return indexed


def compare_depth_results(before,after):
    left,right=_grid(before),_grid(after);rows=[]
    for key,depth in sorted(set(left)|set(right)):
        a,b=left.get((key,depth)),right.get((key,depth))
        changes=['added']if a is None else['removed']if b is None else[field for field in a if a[field]!=b[field]]
        rows.append({'id':key,'depth':depth,'before':a,'after':b,'changes':changes,'changed':bool(changes)})
    return {'format':'interlock-depth-result-comparison/v1','cells':rows,'changed_cells':sum(r['changed']for r in rows),'execution_scope':'none','source_verification':'not_checked',
        'scope':'Complete recorded case/depth matrices validated for identities, fixed expectations, cell coverage/bounds, uniform budgets and consistent incomplete/unexpected summaries before comparison. Added/removed depths and changed scenario identities stay separate from changed observations/coverage. Inputs remain unauthenticated caller claims, not fresh execution, replay, source verification, performance measurements or safety proof. No model, handler or source-pin operations occur. Equal cells do not establish equivalent schedules; expected unsafe outcomes remain unsafe and incomplete is never pass.'}


def render_depth_comparison(report):
    def label(value):return 'Absent'if value is None else value['observed_status']+' / '+value['verdict']
    rows=[{'group':'Changed'if r['changed']else'Unchanged','cells':[r['id'],r['depth'],label(r['before']),label(r['after']),', '.join(r['changes'])or'None']}for r in report['cells']]
    return render_report('Interlock recorded depth-grid comparison',report['scope'],['Case ID','Depth','Before recorded classification','After recorded classification','Changed metadata'],rows,payload=report,summary=f"{report['changed_cells']} changed cells across {len(rows)} recorded case/depth positions. No fresh search, handler execution or safety verification.")
