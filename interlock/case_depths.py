"""Independent bounded model regression checks at explicit depths; no handlers."""
from .model_cases import validated_cases,check_cases
from .report_cards import render_report


def check_case_depths(manifest,depths,*,max_states=5000,selected_ids=None):
    cases=validated_cases(manifest,selected_ids)
    if(not isinstance(depths,list)or not 1<=len(depths)<=8 or any(type(d)is not int or not 0<=d<=64 for d in depths)or len(set(depths))!=len(depths)):
        raise ValueError('select1..8 distinct depths0..64')
    if type(max_states)is not int or max_states<1 or max_states*len(depths)*len(cases)>200000:
        raise ValueError('total requested cases times depths times state budget must be1..200000')
    rows=[]
    for depth in sorted(depths):
        checked=check_cases(manifest,max_depth=depth,max_states=max_states,selected_ids=selected_ids)
        for row in checked['cases']:
            result=row['report'];rows.append({'depth':depth,'id':row['id'],'scenario_sha256':row['scenario_sha256'],'expected_status':row['expected_status'],'observed_status':result['status'],'verdict':row['verdict'],'bounds':result['bounds'],'coverage':result['coverage']})
    incomplete=any(row['verdict']=='incomplete'for row in rows);unexpected=any(row['verdict']=='unexpected'for row in rows)
    return {'format':'interlock-case-depths-v1','status':'incomplete'if incomplete else'unexpected'if unexpected else'passed','any_incomplete':incomplete,'any_unexpected':unexpected,'manifest_cases':len(manifest['cases']),'selected_cases':len(cases),'omitted_cases':len(manifest['cases'])-len(cases),'depths':sorted(depths),'results':rows,'execution_scope':'model_only','source_verification':'not_checked',
        'scope':'Independent model-only checks at explicitly requested depths, keeping caller expectations unchanged and separate bounds/coverage/verdict per case/depth. Every declaration validates, including omitted cases. Total requested state budget capped200000; not a hard wall-time/memory guarantee. No handlers, source pins, imported code or publishable witnesses. Detailed schedules/states omitted. A shallow match or expected unsafe class is not safety; incomplete never passes and unexpected results remain explicit even if another row is incomplete.'}


def render_case_depths(report):
    rows=[{'group':row['verdict'],'cells':[row['id'],row['depth'],row['expected_status'],row['observed_status'],row['coverage']['states_explored'],row['coverage']['complete_up_to_depth']]}for row in report['results']]
    return render_report('Interlock regression depth comparison',report['scope'],['Case ID','Requested depth','Declared expectation','Observed classification','States explored','Complete within bound'],rows,payload=report,summary=f"{report['selected_cases']} explicit cases at {len(report['depths'])} depths; {report['omitted_cases']} cases omitted. Result: {report['status']}. Matching expected unsafe outcomes is not safety approval.")
