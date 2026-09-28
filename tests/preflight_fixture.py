"""Offline intake rejects damaged inputs and never enters a replay backend."""
from pathlib import Path
import sys,json,subprocess,re
from interlock.scenario import fingerprint
root=Path(sys.argv[1]);project=Path(__file__).resolve().parents[1]
scenario=json.loads((project/'examples/multi_job_retry_conflict.json').read_text());scenario['name']='Private imported scenario'
witness={'format':'interlock-witness-v1','scenario':scenario,'scenario_sha256':fingerprint(scenario),'events':['private-illegal-event']}
a=root/'intake-a.json';b=root/'intake-b.json';a.write_text(json.dumps(witness));b.write_text(json.dumps({**witness,'events':[]}));saved=[a.read_bytes(),b.read_bytes()]
code="import sys;from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.engine._initial',side_effect=RuntimeError('execution forbidden')),patch('interlock.fixture.validate_witness_fixture',side_effect=RuntimeError('source verification forbidden')):\n raise SystemExit(main(sys.argv[1:]))\n"
for i,args in enumerate([['inspect-witness',str(a)],['compare-witnesses',str(a),str(b),'--structure-only']]):
    def cli(*extra):return subprocess.run([sys.executable,'-c',code,*args,*extra],text=True,capture_output=True)
    result=cli();assert result.returncode==0,result.stderr;expected=json.loads(result.stdout);r=cli('--html');assert r.returncode==0,r.stderr;html=r.stdout
    assert json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',html,re.S).group(1))==expected
    assert 'private-illegal-event' not in html and 'Private imported scenario' not in html
    assert expected['execution_scope']=='none' and expected['event_legality']=='not_checked';(root/f'preflight-{i}.html').write_text(html)
assert [a.read_bytes(),b.read_bytes()]==saved
r=subprocess.run([sys.executable,'-m','interlock','compare-witnesses',str(a),str(b),'--model-only','--html'],capture_output=True,text=True);assert r.returncode==2 and not r.stdout
b.write_text(json.dumps({**witness,'scenario_sha256':'0'*64}));r=subprocess.run([sys.executable,'-m','interlock','inspect-witness',str(b),'--html'],capture_output=True,text=True);assert r.returncode==2 and not r.stdout
