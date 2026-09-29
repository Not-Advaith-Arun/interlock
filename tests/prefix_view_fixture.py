"""Actual partial model execution retains outcomes but omits private full replay evidence."""
from pathlib import Path
import sys,subprocess,json,re
root=Path(sys.argv[1]);witness=root/'witness.json';scenario=Path(__file__).resolve().parents[1]/'examples/multi_job_retry_conflict.json';made=subprocess.run([sys.executable,'-m','interlock','check',str(scenario),'--witness',str(witness),'--json'],capture_output=True,text=True);assert made.returncode==1,made.stderr
before=witness.read_bytes();count=len(json.loads(before)['events'])
for step in [0,count//2,count]:
 base=[sys.executable,'-m','interlock','replay-prefix',str(witness),'--model-only','--through-step',str(step)];raw=subprocess.run(base,capture_output=True,text=True);native=json.loads(raw.stdout);html=subprocess.run(base+['--html'],capture_output=True,text=True);assert html.returncode==raw.returncode;data=json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',html.stdout,re.S).group(1));assert data['executed_event_count']==step and data['remaining_event_count']==count-step;assert {r['version']:(r['passed'],r['violation_count'])for r in data['versions']}=={key:(value['passed'],len(value['violations']))for key,value in native['result']['outcomes'].items()};assert not any(k in data for k in ['result','trace','events','scenario']);(root/(str(step)+'.html')).write_text(html.stdout);(root/(str(step)+'.json')).write_text(json.dumps(data))
for args in [['--model-only','--through-step',str(count+1)],['--fixture','multi-job-retry-conflict','--through-step','0']]:
 bad=subprocess.run([sys.executable,'-m','interlock','replay-prefix',str(witness),*args,'--html'],capture_output=True,text=True);assert bad.returncode==2 and not bad.stdout
assert witness.read_bytes()==before
