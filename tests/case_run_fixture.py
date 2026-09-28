"""Real bounded model checks keep incomplete/unsafe expectation scope in HTML."""
from pathlib import Path
import sys,json,subprocess,re
from interlock.fixture import fixture_scenario
root=Path(sys.argv[1]);manifest=root/'case-run.json';manifest.write_text(json.dumps({'format':'interlock-model-cases-v1','cases':[{'id':'conflict','expected_status':'merge_interaction_found','scenario':fixture_scenario('retry-conflict')},{'id':'control','expected_status':'no_interaction_within_bound','scenario':fixture_scenario('retry-fixed')}]}));before=manifest.read_bytes()
base=[sys.executable,'-m','interlock','check-cases',str(manifest)]
for i,extra in enumerate([[],['--max-states','1']]):
    r=subprocess.run(base+extra+['--html'],capture_output=True,text=True);assert r.returncode==(0 if i==0 else 3),r.stderr
    payload=json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',r.stdout,re.S).group(1));assert payload['status']==('passed' if i==0 else 'incomplete');assert payload['execution_scope']=='model_only';assert len(payload['cases'])==2;assert 'report' not in payload['cases'][0];assert payload['requested_bounds']['max_states_per_case']==(25000 if i==0 else 1)
    (root/f'case-run-{i}.html').write_text(r.stdout)
assert manifest.read_bytes()==before
r=subprocess.run(base+['--html','--summary'],capture_output=True,text=True);assert r.returncode==2 and not r.stdout
