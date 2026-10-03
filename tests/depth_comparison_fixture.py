from pathlib import Path
import sys,json,subprocess,copy
from interlock.case_template import case_template
root=Path(sys.argv[1]);manifest=root/'cases.json';manifest.write_text(json.dumps(case_template(['retry-fixed','retry-conflict'])));left=root/'left.json';right=root/'right.json'
def cli(*args):return subprocess.run([sys.executable,'-m','interlock',*map(str,args)],capture_output=True,text=True)
for target,depths,budget in [(left,[1,2],10),(right,[1,2,3],1)]:
 r=cli('check-case-depths',manifest,*[item for d in depths for item in('--depth',d)],'--max-states',budget,'--case','retry-fixed');assert r.returncode in(0,2),r.stderr;target.write_text(r.stdout)
originals=[p.read_bytes()for p in(left,right,manifest)];a,b=json.loads(originals[0]),json.loads(originals[1]);assert not a['any_incomplete']and b['any_incomplete'];base=['compare-case-depths',left,right];r=cli(*base);assert r.returncode==0,r.stderr;data=json.loads(r.stdout);assert len(data['cells'])==3 and data['changed_cells']==3;assert data['cells'][2]['changes']==['added'];assert any(row['after']['verdict']=='incomplete'for row in data['cells']);h=cli(*base,'--html');assert h.returncode==0;(root/'comparison.html').write_text(h.stdout);(root/'expected.json').write_text(json.dumps(data));assert[p.read_bytes()for p in(left,right,manifest)]==originals
code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.engine._initial',side_effect=RuntimeError('search forbidden')),patch('interlock.fixture.check_fixture',side_effect=RuntimeError('handler forbidden')):raise SystemExit(main("+repr(list(map(str,base)))+"))";assert subprocess.run([sys.executable,'-c',code],capture_output=True).returncode==0
bad=[];value=copy.deepcopy(b);value['results'].pop();bad.append(value);value=copy.deepcopy(b);value['results'][1]['scenario_sha256']='0'*64;bad.append(value);value=copy.deepcopy(b);value['status']='passed';bad.append(value);value=copy.deepcopy(b);value['results'][0]['bounds']['max_depth']=64;bad.append(value);value=copy.deepcopy(b);value['results'][1]['coverage']['states_explored']=True;bad.append(value);value=copy.deepcopy(b);value['results'][1]=copy.deepcopy(value['results'][0]);bad.append(value)
for value in bad:
 right.write_text(json.dumps(value));r=cli(*base);assert r.returncode==2 and not r.stdout;assert left.read_bytes()==originals[0]and manifest.read_bytes()==originals[2]
right.write_bytes(originals[1])
