"""Captured bounded model and selected source calibration evidence remain separate."""
from .report_cards import render_report


def calibration_metadata(report):
    return {'format':'interlock-calibration-review/v1','contract':report['contract'],'status':report['status'],'scope':report['scope'],'observations_complete':report.get('observations_complete',False),'manifest_sha256':report.get('source_identity',{}).get('manifest_sha256'),'implementation_sha256':report.get('implementation_sha256'),
        'model_scope':report['model']['scope'],'models':[{key:case[key]for key in ('policy','case','complete','termination','states','prefixes','transitions','depth_limited_prefixes','queued_prefixes','bounds')}|{'violation_observed':case['first_violation']is not None}for case in report['model']['results']],
        'observations':[{key:row.get(key)for key in ('policy','case','status','censored','matches')}for row in report['observations']]}


def render_calibration(report):
    data=calibration_metadata(report)
    rows=[{'group':'Finite model','cells':['Finite model',case['policy'],case['case'],case['termination'],case['complete'],'Not source execution',f"{case['states']} states; {case['prefixes']} prefixes; {case['transitions']} transitions",case['violation_observed']]}for case in data['models']]
    rows += [{'group':'Selected source observation','cells':['Selected source',row['policy'],row['case'],row['status'],'Not model coverage',row['matches']if row['matches']is not None else'Unreported','Censored'if row['censored']else'Not censored','Not a full source-prefix search']}for row in data['observations']]
    return render_report('Interlock historical pair calibration',data['scope']+' '+data['model_scope']+' Paths, runtimes, subprocess output, event sequences and diagnostic details omitted. Metadata is a captured result, never a replayable witness. Source identities apply only where reported; a recorded manifest digest means selected source bytes were checked. Model-only does not execute source functions. No independent historical case study or four-way merge safety conclusion.',
        ['Evidence kind','Pinned policy','Declared case','Termination / observation status','Finite model complete','Source expectation match','Coverage / censorship','Violation / scope'],rows,payload=data,
        summary=f"Captured {data['status']}: {len(data['models'])} finite-model environments and {len(data['observations'])} selected source schedules. Source observations complete: {data['observations_complete']}. Model and source coverage stay separate; incomplete or drifted observations never count as calibrated. Selected extracted sources run on a modern host, not the historical CPython build.")
