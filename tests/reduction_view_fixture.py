"""Actual complete/budget-limited model reduction retains scope and omits replay evidence."""
from pathlib import Path
import sys,subprocess,json,re
from interlock.fixture import fixture_scenario
from interlock.reduction_view import reduction_metadata
root=Path(sys.argv[1]);scenario=root/'scenario.json';scenario.write_text(json.dumps(fixture_scenario('multi-job-retry-conflict')));witness=root/'witness.json';made=subprocess.run([sys.executable,'-m','interlock','check',str(scenario),'--witness',str(witness),'--json'],capture_output=True,text=True);assert made.returncode==1,made.stderr;before=witness.read_bytes();base=[sys.executable,'-m','interlock','minimize',str(witness),'--model-only']
for name,flags in [('complete',['--max-diagnostics','100']),('budget',['--max-attempts','1','--max-diagnostics','1']),('omitted',['--max-diagnostics','1'])]:
 native=subprocess.run(base+flags+['--json'],capture_output=True,text=True);result=json.loads(native.stdout);html=subprocess.run(base+flags+['--html'],capture_output=True,text=True);assert html.returncode==native.returncode==(3 if name=='budget'else 0),html.stderr;data=json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',html.stdout,re.S).group(1));assert data==reduction_metadata(result);assert not any(key in data for key in ['scenario','replay','original_events','reduced_events','handler_replay']);assert data['one_event_deletion_minimal']==(name!='budget');assert name!='omitted' or data['omitted_decisions']>0;(root/(name+'.html')).write_text(html.stdout);(root/(name+'.json')).write_text(json.dumps(data))
for flags in [['--json'],['--report',str(root/'must-not-exist.json')],['--model-witness',str(root/'must-not-exist.json')],['--max-attempts','0']]:
 bad=subprocess.run(base+flags+['--html'],capture_output=True,text=True);assert bad.returncode==2 and not bad.stdout
bad=subprocess.run([sys.executable,'-m','interlock','minimize',str(witness),'--fixture','multi-job-retry-conflict','--html'],capture_output=True,text=True);assert bad.returncode==2 and not bad.stdout;assert not(root/'must-not-exist.json').exists();assert witness.read_bytes()==before
