"""Static intake validates omitted declarations without executing bounded searches."""
from pathlib import Path
import sys,json,subprocess,re
from interlock.case_template import case_template
root=Path(sys.argv[1]);manifest=case_template(['retry-conflict','retry-fixed']);manifest['cases'][0]['scenario']['name']='PRIVATE_SCENARIO_TITLE';source=root/'manifest.json';source.write_text(json.dumps(manifest));before=source.read_bytes()
for name,extra in [('all',[]),('selected',['--case','retry-fixed'])]:
 base=[sys.executable,'-m','interlock','inspect-cases',str(source),*extra];r=subprocess.run(base,capture_output=True,text=True);assert r.returncode==0,r.stderr;value=json.loads(r.stdout);assert len(value['cases'])==(2 if name=='all'else 1);assert value['omitted_cases']==(0 if name=='all'else 1);h=subprocess.run(base+['--html'],capture_output=True,text=True);assert h.returncode==0,h.stderr;assert 'PRIVATE_SCENARIO_TITLE'not in h.stdout;assert json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',h.stdout,re.S).group(1))==value;(root/(name+'.html')).write_text(h.stdout);(root/(name+'.json')).write_text(json.dumps(value));assert source.read_bytes()==before
code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.model_cases.check_many',side_effect=RuntimeError('search forbidden')),patch('interlock.fixture.check_fixture',side_effect=RuntimeError('handlers forbidden')):raise SystemExit(main(['inspect-cases',"+repr(str(source))+"]))"
r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True);assert r.returncode==0,r.stderr
manifest['cases'][0]['scenario']['model']='invalid';source.write_text(json.dumps(manifest));r=subprocess.run([sys.executable,'-m','interlock','inspect-cases',str(source),'--case','retry-fixed','--html'],capture_output=True);assert r.returncode==2 and not r.stdout
