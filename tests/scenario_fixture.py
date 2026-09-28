"""Actual declared-change review must not turn into a model execution."""
from pathlib import Path
import sys,json,subprocess,re
from interlock.fixture import fixture_scenario
root=Path(sys.argv[1]);a=root/'scenario-a.json';b=root/'scenario-b.json'
one=fixture_scenario('retry-conflict');two=fixture_scenario('retry-fixed');two['name']='<script>window.scenarioInjected=true</script>'
a.write_text(json.dumps(one));b.write_text(json.dumps(two));saved=[a.read_bytes(),b.read_bytes()]
code="import sys;from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.engine._initial',side_effect=RuntimeError('execution forbidden')):\n raise SystemExit(main(sys.argv[1:]))\n"
base=[sys.executable,'-c',code,'compare-scenarios',str(a),str(b)]
expected=json.loads(subprocess.check_output(base));r=subprocess.run(base+['--html'],text=True,capture_output=True);assert r.returncode==0,r.stderr
assert json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',r.stdout,re.S).group(1))==expected
assert any(row['changed'] for row in expected['versions'].values());assert [a.read_bytes(),b.read_bytes()]==saved
(root/'scenarios.html').write_text(r.stdout);(root/'scenarios-expected.json').write_text(json.dumps(expected))
b.write_text(json.dumps({**two,'versions':{}}));r=subprocess.run(base+['--html'],capture_output=True,text=True);assert r.returncode==2 and not r.stdout
