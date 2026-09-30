"""Actual trusted bundled suite preserves verdict/coverage and incomplete exits in HTML."""
from pathlib import Path
import sys,subprocess,json,re
root=Path(sys.argv[1]);base=[sys.executable,'-m','interlock','suite','--fixture','retry-conflict','--fixture','retry-fixed']
for name,extra in [('complete',[]),('depth',['--max-depth','1']),('budget',['--max-schedules','1'])]:
 native=subprocess.run(base+extra+['--summary'],capture_output=True,text=True);expected=json.loads(native.stdout);html=subprocess.run(base+extra+['--html'],capture_output=True,text=True);assert html.returncode==native.returncode==(0 if name=='complete'else 3);data=json.loads(re.search(r'<script id="report-data" type="application/json">(.*?)</script>',html.stdout,re.S).group(1));assert data==expected;assert not any('trace'in r or'candidate'in r for r in data['cases']);(root/(name+'.html')).write_text(html.stdout);(root/(name+'.json')).write_text(json.dumps(data))
for extra in [['--json'],['--summary'],['--fixture','untrusted']]:
 refused=subprocess.run(base+extra+['--html'],capture_output=True,text=True);assert refused.returncode==2 and not refused.stdout
