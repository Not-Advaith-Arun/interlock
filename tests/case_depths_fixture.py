"""Actual selected model checks keep depth coverage and frozen expectations independent."""
from pathlib import Path
import sys,json,subprocess
from interlock.case_template import case_template
root=Path(sys.argv[1]);file=root/'cases.json';manifest=case_template(['retry-fixed','retry-conflict']);file.write_text(json.dumps(manifest));before=file.read_bytes();base=[sys.executable,'-m','interlock','check-case-depths',str(file),'--depth','2','--depth','1','--max-states','10','--case','retry-fixed'];r=subprocess.run(base,capture_output=True,text=True);assert r.returncode==0,r.stderr;data=json.loads(r.stdout);assert data['depths']==[1,2]and data['selected_cases']==1 and data['omitted_cases']==1;assert len(data['results'])==2 and all(row['id']=='retry-fixed'for row in data['results']);assert data['results'][0]['coverage']!=data['results'][1]['coverage'];h=subprocess.run(base+['--html'],capture_output=True,text=True);assert h.returncode==0,h.stderr;(root/'depths.html').write_text(h.stdout);(root/'expected.json').write_text(json.dumps(data));assert file.read_bytes()==before
for extra in [['--depth','2'],['--max-states','200001']]:
 r=subprocess.run(base+extra,capture_output=True);assert r.returncode==2 and not r.stdout
bad=json.loads(before);bad['cases'][1]['scenario']={};file.write_text(json.dumps(bad));r=subprocess.run(base,capture_output=True);assert r.returncode==2 and not r.stdout;file.write_bytes(before)
r=subprocess.run([sys.executable,'-m','interlock','check-case-depths',str(file),'--depth','2','--max-states','1'],capture_output=True,text=True);assert r.returncode==2,r.stdout+r.stderr;assert json.loads(r.stdout)['any_incomplete']
code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.fixture.check_fixture',side_effect=RuntimeError('handlers forbidden')):raise SystemExit(main("+repr(base[3:])+"))";assert subprocess.run([sys.executable,'-c',code],capture_output=True).returncode==0
