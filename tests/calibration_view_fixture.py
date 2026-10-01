"""Actual pinned calibration, explicit model-only and source-integrity refusal in HTML."""
from pathlib import Path
import sys,json,subprocess,re,shutil
from interlock.calibration_view import calibration_metadata
from interlock.historical_waitfor import FIXTURE
root=Path(sys.argv[1]);base=[sys.executable,'-m','interlock','historical-waitfor']
for name,flags,status in [('source',[],'calibrated'),('model',['--model-only'],'model_only')]:
 native=subprocess.run(base+flags+['--json'],capture_output=True,text=True);report=json.loads(native.stdout);assert report['status']==status,native.stderr;html=subprocess.run(base+flags+['--html'],capture_output=True,text=True);assert html.returncode==native.returncode==0;data=json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',html.stdout,re.S).group(1));assert data==calibration_metadata(report);assert len(data['models'])==10 and len(data['observations'])==(12 if name=='source'else 0);assert all(c['complete']for c in data['models']);assert data['observations_complete']==(name=='source');assert name!='source'or all(row['matches']for row in data['observations']);assert not any(k in data for k in ['substitutions','reason','limits','source_identity']);(root/(name+'.html')).write_text(html.stdout);(root/(name+'.json')).write_text(json.dumps(data))
# Use actual altered source bytes to trigger pin failure before source execution.
changed=root/'PRIVATE_SOURCE_FIXTURE';shutil.copytree(FIXTURE,changed);(changed/'before.py').write_text('PRIVATE_DRIFT_CONTENT')
code="import sys;from pathlib import Path;from unittest.mock import patch;import interlock.historical_waitfor as h;from interlock.cli import main\noriginal=h.verified_payloads\nwith patch.object(h,'verified_payloads',lambda:original(Path(sys.argv[1]))):raise SystemExit(main(sys.argv[2:]))\n"
for fmt in ['--json','--html']:
 r=subprocess.run([sys.executable,'-c',code,str(changed),'historical-waitfor',fmt],capture_output=True,text=True);assert r.returncode==2,r.stderr
 if fmt=='--json':expected=calibration_metadata(json.loads(r.stdout));assert expected['status']=='source_drift'and not expected['observations']
 else:
  data=json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',r.stdout,re.S).group(1));assert data==expected;assert 'PRIVATE_DRIFT_CONTENT'not in r.stdout and 'PRIVATE_SOURCE_FIXTURE'not in r.stdout;(root/'drift.html').write_text(r.stdout);(root/'drift.json').write_text(json.dumps(data))
for flags in [['--json'],['--report',str(root/'must-not-write.json')]]:
 refused=subprocess.run(base+flags+['--html'],capture_output=True,text=True);assert refused.returncode==2 and not refused.stdout
assert not(root/'must-not-write.json').exists()
