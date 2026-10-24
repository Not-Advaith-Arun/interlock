"""Actual model case results compared without triggering new replay/search."""
from pathlib import Path
import sys,json,subprocess
from interlock.model_cases import check_cases
from interlock.fixture import fixture_scenario
root=Path(sys.argv[1]);manifest={'format':'interlock-model-cases-v1','cases':[{'id':'retry','expected_status':'merge_interaction_found','scenario':fixture_scenario('retry-conflict')},{'id':'control','expected_status':'no_interaction_within_bound','scenario':fixture_scenario('retry-fixed')}]};before=check_cases(manifest);manifest['cases'][0]['scenario']=fixture_scenario('retry-fixed');manifest['cases'][0]['scenario']['name']='Repaired retry candidate';after=check_cases(manifest)
paths=[root/'before.json',root/'after.json']
for p,v in zip(paths,[before,after]):p.write_text(json.dumps(v))
saved=[p.read_bytes() for p in paths];base=[sys.executable,'-m','interlock','compare-case-results',*map(str,paths)];expected=json.loads(subprocess.check_output(base));html=subprocess.check_output(base+['--html'],text=True);assert [p.read_bytes() for p in paths]==saved;assert expected['changed_cases']==1 and expected['unchanged_cases']==1
(root/'report.html').write_text(html);(root/'expected.json').write_text(json.dumps({'title':'Interlock recorded comparison','rows':2,'group':'changed','groupRows':1,'payload':expected}))
after['cases'][0]['verdict']='passed';paths[1].write_text(json.dumps(after));r=subprocess.run(base+['--html'],capture_output=True,text=True);assert r.returncode==2 and not r.stdout
