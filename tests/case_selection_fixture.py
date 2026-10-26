"""Real selected manifest roundtrip preserves declarations and honest bounded runs."""
from pathlib import Path
import json,subprocess,sys,re
from interlock.case_template import case_template
root=Path(sys.argv[1]);manifest=case_template(['retry-conflict','retry-fixed','cancellation-fixed']);manifest['cases'][0]['scenario']['name']='PRIVATE_OMITTED_SCENARIO';source=root/'manifest.json';source.write_text(json.dumps(manifest));before=source.read_bytes();base=[sys.executable,'-m','interlock','select-cases',str(source),'--case','cancellation-fixed','--case','retry-fixed'];expected={'format':manifest['format'],'cases':[manifest['cases'][1],manifest['cases'][2]]}
r=subprocess.run(base,capture_output=True,text=True);assert r.returncode==0,r.stderr;assert json.loads(r.stdout)==expected;h=subprocess.run(base+['--html'],capture_output=True,text=True);assert h.returncode==0,h.stderr;assert json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',h.stdout,re.S).group(1))==expected;assert 'PRIVATE_OMITTED_SCENARIO'not in h.stdout;assert source.read_bytes()==before;(root/'selected.html').write_text(h.stdout);(root/'expected.json').write_text(json.dumps(expected))
code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.model_cases.check_many',side_effect=RuntimeError('search forbidden')),patch('interlock.fixture.check_fixture',side_effect=RuntimeError('handlers forbidden')):raise SystemExit(main("+repr(base[3:])+"))"
r=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True);assert r.returncode==0,r.stderr
for extra in [['--case','missing'],['--case','retry-fixed','--case','retry-fixed']]:
 r=subprocess.run(base[:5]+extra,capture_output=True);assert r.returncode==2 and not r.stdout
manifest['cases'][0]['scenario']['model']='invalid';source.write_text(json.dumps(manifest));r=subprocess.run(base+['--html'],capture_output=True);assert r.returncode==2 and not r.stdout
