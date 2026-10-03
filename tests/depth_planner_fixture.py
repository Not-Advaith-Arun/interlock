from pathlib import Path
import sys,json,subprocess,copy
from interlock.case_template import case_template
root=Path(sys.argv[1]);manifest=root/'cases.json'
def cli(*args):return subprocess.run([sys.executable,'-m','interlock',*map(str,args)],capture_output=True,text=True)
if len(sys.argv)==2:
 manifest.write_text(json.dumps(case_template(['retry-fixed','retry-conflict'])));h=cli('case-depth-template',manifest);assert h.returncode==0,h.stderr;(root/'planner.html').write_text(h.stdout);(root/'before').write_bytes(manifest.read_bytes());code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.engine._initial',side_effect=RuntimeError('search forbidden')),patch('interlock.fixture.check_fixture',side_effect=RuntimeError('handlers forbidden')):raise SystemExit(main("+repr(['case-depth-template',str(manifest)])+"))";assert subprocess.run([sys.executable,'-c',code],capture_output=True).returncode==0
else:
 file=root/'out.json';good=file.read_bytes();plan=json.loads(good);assert plan['case_ids']==['retry-fixed']and plan['depths']==[1,2]and plan['max_states']==10;before=(root/'before').read_bytes();base=['check-case-depths',manifest,'--plan',file];r=cli(*base);assert r.returncode==0,r.stderr;result=json.loads(r.stdout);assert result['selected_cases']==1 and result['omitted_cases']==1 and result['depths']==[1,2];assert manifest.read_bytes()==before
 for bad in[{**plan,'manifest_sha256':'0'*64},{**plan,'case_ids':None},{**plan,'case_ids':['unknown']},{**plan,'depths':[1,1]},{**plan,'depths':[True]},{**plan,'max_states':200001}]:
  file.write_text(json.dumps(bad));r=cli(*base);assert r.returncode==2 and not r.stdout
 file.write_bytes(good)
 for extra in[['--depth','1'],['--case','retry-fixed'],['--max-states','10']]:assert cli(*base,*extra).returncode==2
 changed=json.loads(before);changed['cases'][1]['expected_status']='baseline_failure';manifest.write_text(json.dumps(changed));r=cli(*base);assert r.returncode==2 and not r.stdout;changed['cases'][1]['scenario']={};manifest.write_text(json.dumps(changed));assert cli('case-depth-template',manifest).returncode==2;manifest.write_bytes(before)
