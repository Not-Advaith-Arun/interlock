from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import json,subprocess,sys
from interlock.case_template import case_template
from interlock.depth_binding import inspect_depth_binding
from interlock.depth_selection import select_depth_cases
root=Path(sys.argv[1]);manifest=root/'cases.json';report=root/'grid.json'
def cli(*args):return subprocess.run([sys.executable,'-m','interlock',*map(str,args)],capture_output=True,text=True)
if len(sys.argv)==2:
 manifest.write_text(json.dumps(case_template(['retry-fixed','retry-conflict'])));r=cli('check-case-depths',manifest,'--depth','1','--depth','4','--max-states','2');assert r.returncode==2,r.stderr;report.write_text(r.stdout);grid=json.loads(r.stdout);decl=json.loads(manifest.read_text());before=report.read_bytes();r=cli('inspect-depth-binding',manifest,report);assert r.returncode==0,r.stderr;result=json.loads(r.stdout);assert result['matches_declarations']and result['recorded_any_incomplete']and result['recorded_status']=='incomplete';h=cli('inspect-depth-binding',manifest,report,'--html');assert h.returncode==0,h.stderr;(root/'binding.html').write_text(h.stdout);(root/'expected.json').write_text(json.dumps(result))
 with patch('interlock.engine._initial',side_effect=AssertionError('search forbidden')),patch('interlock.fixture.check_fixture',side_effect=AssertionError('handler forbidden')):assert inspect_depth_binding(decl,grid)==result
 # Changed expected status is visible at all recorded depths, not interpreted as fresh observations.
 bad=deepcopy(decl);bad['cases'][0]['expected_status']='baseline_failure';manifest.write_text(json.dumps(bad));r=cli('inspect-depth-binding',manifest,report);assert r.returncode==1 and all(x['differences']==['expected_status']for x in json.loads(r.stdout)['cells']if x['id']=='retry-fixed')
 manifest.write_text(json.dumps(decl));subset=select_depth_cases(grid,['retry-fixed']);report.write_text(json.dumps(subset));r=cli('inspect-depth-binding',manifest,report);assert r.returncode==1 and sum('missing_record'in x['differences']for x in json.loads(r.stdout)['cells'])==2;assert cli('inspect-depth-binding',manifest,report,'--case','retry-fixed').returncode==0
 bad=deepcopy(decl);bad['cases'][1]['scenario']['unknown']='invalid';manifest.write_text(json.dumps(bad));r=cli('inspect-depth-binding',manifest,report,'--case','retry-fixed');assert r.returncode==2 and not r.stdout;manifest.write_text(json.dumps(decl));bad=deepcopy(grid);bad['results'][-1]['coverage']['complete_up_to_depth']=True;report.write_text(json.dumps(bad));r=cli('inspect-depth-binding',manifest,report);assert r.returncode==2 and not r.stdout;report.write_bytes(before)
else:assert json.loads((root/'download.json').read_text())==json.loads((root/'expected.json').read_text())
