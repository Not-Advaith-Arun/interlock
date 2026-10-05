from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,subprocess,sys
from interlock.case_template import case_template
from interlock.depth_template import depth_template
from interlock.plan_binding import inspect_plan_binding
root=Path(sys.argv[1]);manifest=root/'cases.json';planfile=root/'plan.json';report=root/'grid.json'
def cli(*args):return subprocess.run([sys.executable,'-m','interlock',*map(str,args)],capture_output=True,text=True)
if len(sys.argv)==2:
 value=case_template(['retry-fixed','retry-conflict']);manifest.write_text(json.dumps(value));plan=depth_template(value)['plan'];plan.update(case_ids=['retry-fixed','retry-conflict'],depths=[1,4],max_states=2);planfile.write_text(json.dumps(plan));r=cli('check-case-depths',manifest,'--plan',planfile);assert r.returncode==2,r.stderr;report.write_text(r.stdout);grid=json.loads(r.stdout);r=cli('inspect-plan-binding',manifest,planfile,report);assert r.returncode==0,r.stderr;result=json.loads(r.stdout);assert result['matches_plan']and result['recorded_any_incomplete'];(root/'expected.json').write_text(r.stdout);h=cli('inspect-plan-binding',manifest,planfile,report,'--html');assert h.returncode==0,h.stderr;(root/'handoff.html').write_text(h.stdout)
 with patch('interlock.engine._initial',side_effect=AssertionError('search forbidden')),patch('interlock.fixture.check_fixture',side_effect=AssertionError('handlers forbidden')):assert inspect_plan_binding(value,plan,grid)==result
 for bad in [{**plan,'depths':[0,1]},{**plan,'max_states':3},{**plan,'case_ids':['retry-fixed']}]:
  planfile.write_text(json.dumps(bad));r=cli('inspect-plan-binding',manifest,planfile,report);assert r.returncode==1 and not json.loads(r.stdout)['matches_plan'];assert json.loads(r.stdout)['recorded_any_incomplete']
 planfile.write_text(json.dumps({**plan,'manifest_sha256':'stale'}));r=cli('inspect-plan-binding',manifest,planfile,report);assert r.returncode==2 and not r.stdout;planfile.write_text(json.dumps(plan));bad=deepcopy(grid);bad['results'][-1]['coverage']['complete_up_to_depth']=True;report.write_text(json.dumps(bad));r=cli('inspect-plan-binding',manifest,planfile,report);assert r.returncode==2 and not r.stdout;report.write_text(json.dumps(grid))
else:assert json.loads((root/'download.json').read_text())==json.loads((root/'expected.json').read_text())
