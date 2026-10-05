from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,subprocess,sys
from interlock.case_template import case_template
from interlock.depth_template import depth_template,resume_depth_plan
from interlock.scenario import fingerprint
root=Path(sys.argv[1]);manifest=root/'cases.json';file=root/'plan.json'
def cli(*args):return subprocess.run([sys.executable,'-m','interlock',*map(str,args)],capture_output=True,text=True)
if len(sys.argv)==2:
 value=case_template(['retry-fixed','retry-conflict']);manifest.write_text(json.dumps(value));plan=depth_template(value)['plan'];plan.update(case_ids=['retry-conflict','retry-fixed'],depths=[4,1],max_states=2);file.write_text(json.dumps(plan));before=manifest.read_bytes();r=cli('resume-depth-plan',manifest,file);assert r.returncode==0,r.stderr;(root/'resume.html').write_text(r.stdout);(root/'before').write_bytes(before)
 with patch('interlock.engine._initial',side_effect=AssertionError('search forbidden')),patch('interlock.fixture.check_fixture',side_effect=AssertionError('handler forbidden')):assert resume_depth_plan(value,plan)['plan']==plan
 for bad in [{**plan,'manifest_sha256':'stale'},{**plan,'case_ids':['unknown']},{**plan,'depths':[1,1]},{**plan,'max_states':200001}]:
  file.write_text(json.dumps(bad));r=cli('resume-depth-plan',manifest,file);assert r.returncode==2 and not r.stdout
 bad=deepcopy(value);bad['cases'][1]['scenario']['unknown']='invalid';badplan={**plan,'case_ids':['retry-fixed'],'manifest_sha256':fingerprint(bad)};manifest.write_text(json.dumps(bad));file.write_text(json.dumps(badplan));r=cli('resume-depth-plan',manifest,file);assert r.returncode==2 and not r.stdout;manifest.write_bytes(before);file.write_text(json.dumps(plan))
else:
 assert json.loads((root/'download.json').read_text())==json.loads(file.read_text());assert manifest.read_bytes()==(root/'before').read_bytes();r=cli('check-case-depths',manifest,'--plan',root/'download.json');assert r.returncode==2,r.stderr;grid=json.loads(r.stdout);assert grid['any_incomplete']and grid['depths']==[1,4]and grid['selected_cases']==2
