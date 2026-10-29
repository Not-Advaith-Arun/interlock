from pathlib import Path
import json,subprocess,sys,copy
from interlock.case_template import case_template
root=Path(sys.argv[1]);manifest=root/'cases.json'
def cli(*args):return subprocess.run([sys.executable,'-m','interlock',*map(str,args)],capture_output=True,text=True)
if len(sys.argv)==2:
 manifest.write_text(json.dumps(case_template(['retry-fixed','retry-conflict'])))
 for key,name in [('retry-fixed','left.json'),('retry-conflict','right.json')]:
  r=cli('check-case-depths',manifest,'--case',key,'--depth','1','--depth','4','--max-states','2');assert r.returncode==2,r.stderr;(root/name).write_text(r.stdout)
 left=root/'left.json';right=root/'right.json';original=right.read_bytes();before=left.read_bytes();r=cli('combine-case-depths',left,right);assert r.returncode==0,r.stderr;combined=json.loads(r.stdout);assert combined['selected_cases']==2 and combined['omitted_cases']==0 and combined['status']=='incomplete';allrun=cli('check-case-depths',manifest,'--depth','1','--depth','4','--max-states','2');assert sorted(combined['results'],key=lambda r:(r['depth'],r['id']))==sorted(json.loads(allrun.stdout)['results'],key=lambda r:(r['depth'],r['id']));(root/'expected.json').write_text(r.stdout);(root/'combined.json').write_text(r.stdout);assert cli('case-depth-summary',root/'combined.json').returncode==0;assert cli('compare-case-depths',root/'combined.json',root/'combined.json').returncode==0
 h=cli('combine-case-depths',left,right,'--html');assert h.returncode==0,h.stderr;(root/'combined.html').write_text(h.stdout)
 r=cli('combine-case-depths',left,left);assert r.returncode==0 and json.loads(r.stdout)['selected_cases']==1
 # Same case identity with incompatible recorded scenario declaration must never overwrite.
 bad=json.loads(before)
 for row in bad['results']:row['scenario_sha256']='0'*64
 right.write_text(json.dumps(bad));r=cli('combine-case-depths',left,right);assert r.returncode==2 and not r.stdout
 right.write_bytes(original);bad=json.loads(original);bad['results'][-1]['coverage']['complete_up_to_depth']=True;right.write_text(json.dumps(bad));r=cli('combine-case-depths',left,right);assert r.returncode==2 and not r.stdout;right.write_bytes(original)
 code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.engine._initial',side_effect=RuntimeError('search forbidden')),patch('interlock.fixture.check_fixture',side_effect=RuntimeError('handler forbidden')):raise SystemExit(main("+repr(['combine-case-depths',str(left),str(right)])+"))";assert subprocess.run([sys.executable,'-c',code],capture_output=True).returncode==0;assert left.read_bytes()==before and right.read_bytes()==original
else:assert json.loads((root/'download.json').read_text())==json.loads((root/'expected.json').read_text())
