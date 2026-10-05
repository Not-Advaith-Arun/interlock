from pathlib import Path
from unittest.mock import patch
import json,subprocess,sys
from interlock.case_template import case_template
from interlock.depth_template import depth_template,combine_depth_plans
root=Path(sys.argv[1]);manifest=root/'cases.json';a=root/'left.json';b=root/'right.json'
def cli(*args):return subprocess.run([sys.executable,'-m','interlock',*map(str,args)],capture_output=True,text=True)
if len(sys.argv)==2:
 value=case_template(['retry-fixed','retry-conflict']);manifest.write_text(json.dumps(value));base=depth_template(value)['plan'];left={**base,'case_ids':['retry-fixed'],'depths':[1,4],'max_states':2};right={**left,'case_ids':['retry-conflict']};a.write_text(json.dumps(left));b.write_text(json.dumps(right));beforea=a.read_bytes();beforeb=b.read_bytes();r=cli('combine-depth-plans',manifest,a,b);assert r.returncode==0,r.stderr;combined=json.loads(r.stdout);assert combined['case_ids']==['retry-conflict','retry-fixed']and combined['depths']==[1,4];(root/'expected.json').write_text(r.stdout);h=cli('combine-depth-plans',manifest,a,b,'--html');assert h.returncode==0,h.stderr;(root/'combined.html').write_text(h.stdout)
 with patch('interlock.engine._initial',side_effect=AssertionError('search forbidden')),patch('interlock.fixture.check_fixture',side_effect=AssertionError('handler forbidden')):assert combine_depth_plans(value,left,right)['plan']==combined
 for x,y in [({**left,'depths':[1]},{**right,'depths':[4]}),(left,{**right,'max_states':3}),(left,{**right,'manifest_sha256':'stale'}),({**left,'max_states':60000},{**right,'max_states':60000})]:
  a.write_text(json.dumps(x));b.write_text(json.dumps(y));r=cli('combine-depth-plans',manifest,a,b);assert r.returncode==2 and not r.stdout
 a.write_bytes(beforea);b.write_bytes(beforeb);assert combine_depth_plans(value,left,left)['plan']['case_ids']==left['case_ids']
else:
 assert json.loads((root/'download.json').read_text())==json.loads((root/'expected.json').read_text());r=cli('check-case-depths',manifest,'--plan',root/'download.json');assert r.returncode==2,r.stderr;grid=json.loads(r.stdout);assert grid['any_incomplete']and grid['selected_cases']==2 and grid['depths']==[1,4]
