"""Actual bounded CLI batch/sweep output with complete and incomplete metadata."""
from pathlib import Path
import sys,json,subprocess,re
from interlock.fixture import fixture_scenario
root=Path(sys.argv[1]);files=[]
for index,name in enumerate(('retry-conflict','retry-fixed')):
 scenario=fixture_scenario(name);scenario['name']='PRIVATE_SCENARIO_TITLE '+str(index);path=root/f'scenario-{index}.json';path.write_text(json.dumps(scenario));files.append(path)
before={p:p.read_bytes() for p in files}
commands=[('batch',['check-many',*map(str,files)]),('limited',['check-many',*map(str,files),'--max-states','1']),('sweep',['sweep-depths',str(files[0]),'--model-only','--depth','0','--depth','8']),('sweep-limited',['sweep-depths',str(files[0]),'--model-only','--depth','0','--depth','8','--max-states','1'])]
for name,args in commands:
 native=subprocess.run([sys.executable,'-m','interlock',*args],capture_output=True,text=True);report=json.loads(native.stdout);html=subprocess.run([sys.executable,'-m','interlock',*args,'--html'],capture_output=True,text=True);assert html.returncode==native.returncode;data=json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',html.stdout,re.S).group(1));assert data['any_incomplete']==report['any_incomplete'] and data['any_failure']==report['any_failure'];assert len(data['results'])==2;assert data['requested_state_budget']==sum(row['bounds']['max_states'] for row in data['results']);assert data['execution_scope']=='model_only' and data['source_verification']=='not_checked';assert 'PRIVATE_SCENARIO_TITLE' not in html.stdout
 source=report['cases'] if name.startswith('batch') or name=='limited' else report['results']
 for got,entry in zip(data['results'],source):
    expected=entry.get('report',entry);assert got['status']==expected['status'] and got['bounds']==expected['bounds'] and got['coverage']==expected['coverage'];assert 'candidate_events' not in got and 'versions' not in got
 (root/(name+'.html')).write_text(html.stdout);(root/(name+'.json')).write_text(json.dumps(data))
bad=subprocess.run([sys.executable,'-m','interlock','sweep-depths',str(files[0]),'--depth','1','--fixture','retry-conflict','--html'],text=True,capture_output=True);assert bad.returncode==2 and not bad.stdout
assert all(path.read_bytes()==data for path,data in before.items())
