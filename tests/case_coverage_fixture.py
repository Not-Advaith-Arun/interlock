"""Equal classifications can conceal different requested bounds and explored coverage."""
from pathlib import Path
import sys,json,subprocess,re
from interlock.case_template import case_template
root=Path(sys.argv[1]);manifest=root/'cases.json';manifest.write_text(json.dumps(case_template(['retry-fixed'])));files=[]
for depth in [1,2]:
 file=root/('depth'+str(depth)+'.json');r=subprocess.run([sys.executable,'-m','interlock','check-cases',str(manifest),'--max-depth',str(depth),'--max-states','10','--report',str(file)],capture_output=True,text=True);assert r.returncode==0,r.stderr;files.append(file)
base=[sys.executable,'-m','interlock','compare-case-results',*map(str,files),'--include-coverage'];before=[p.read_bytes()for p in files];r=subprocess.run(base,capture_output=True,text=True);assert r.returncode==0,r.stderr;result=json.loads(r.stdout);row=result['cases'][0];assert row['changes']==['bounds','coverage'],row;assert row['before']['observed_status']==row['after']['observed_status'];assert row['before']['bounds']['max_depth']==1 and row['after']['bounds']['max_depth']==2;h=subprocess.run(base+['--html'],capture_output=True,text=True);assert h.returncode==0,h.stderr;assert json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',h.stdout,re.S).group(1))==result;(root/'coverage.html').write_text(h.stdout);(root/'expected.json').write_text(json.dumps(result));assert[p.read_bytes()for p in files]==before
code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.model_batch.run_check',side_effect=RuntimeError('search forbidden')):raise SystemExit(main("+repr(base[3:])+"))";r=subprocess.run([sys.executable,'-c',code],capture_output=True);assert r.returncode==0
bad=json.loads(before[1]);bad['cases'][0]['report']['coverage']['states_explored']=True;files[1].write_text(json.dumps(bad));r=subprocess.run(base+['--html'],capture_output=True);assert r.returncode==2 and not r.stdout
