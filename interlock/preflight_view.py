"""Render validated declarations without suggesting they were executed."""
import json
from .report_cards import render_report


def render_preflight(report):
    rows=[]
    for key,value in report.items():
        if key in ('scope','format'):
            continue
        group='Not checked' if key in ('source_verification','event_legality','execution_scope') else 'Recorded metadata'
        rows.append({'group':group,'cells':[key.replace('_',' '),json.dumps(value,sort_keys=True) if isinstance(value,(dict,list)) else str(value)]})
    return render_report('Interlock witness preflight',report['scope']+' This is a structural intake report, not an execution result.',
                         ['Declaration / boundary','Recorded value'],rows,payload=report,summary="Structural intake only. Model execution, installed source identity and event legality are not checked.")
