"""Read declared branch changes before choosing any execution mode."""
import json
from .report_cards import render_report


def render_scenarios(report):
    rows=[]
    for version,row in report['versions'].items():
        changes='\n'.join(change['field']+': '+(json.dumps(change['before']) if change['before_present'] else '(absent)')+' → '+(json.dumps(change['after']) if change['after_present'] else '(absent)') for change in row['changes'])
        rows.append({'group':'changed' if row['changed'] else 'unchanged','cells':[version,changes or 'No declared configuration change']})
    scope=(report['scope']+' Before: '+report['left']['name']+' ('+report['left']['sha256']+'). After: '+report['right']['name']+' ('+report['right']['sha256']+').')
    return render_report('Interlock declared branch changes',scope,['Version','Before → after declarations'],rows,payload=report)
