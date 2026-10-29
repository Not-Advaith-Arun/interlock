from pathlib import Path
import json,subprocess,sys,copy
from interlock.case_template import case_template
root=Path(sys.argv[1]);manifest=root/'cases.json';report=root/'grid.json'
def cli(*args):return subprocess.run([sys.executable,'-m','interlock',*map(str,args)],capture_output=True,text=True)
if len(sys.argv)==2:
 manifest.write_text(json.dumps(case_template(['retry-fixed','retry-conflict'])));r=cli('check-case-depths',manifest,'--depth','1','--depth','4','--max-states','2');assert r.returncode==2,r.stderr;report.write_text(r.stdout);original=report.read_bytes();value=json.loads(original)
 r=cli('select-case-depths',report,'--case','retry-fixed');assert r.returncode==0,r.stderr;selected=json.loads(r.stdout);assert selected['selected_cases']==1 and selected['omitted_cases']==1 and selected['manifest_cases']==2;assert selected['depths']==[1,4];assert selected['results']==[r for r in value['results'] if r['id']=='retry-fixed'];assert selected['status']=='incomplete';(root/'selected.json').write_text(r.stdout);(root/'expected.json').write_text(r.stdout)
 assert cli('case-depth-summary',root/'selected.json').returncode==0;assert cli('compare-case-depths',root/'selected.json',root/'selected.json').returncode==0
 h=cli('select-case-depths',report,'--case','retry-fixed','--html');assert h.returncode==0,h.stderr;(root/'selected.html').write_text(h.stdout)
 code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.engine._initial',side_effect=RuntimeError('search forbidden')),patch('interlock.fixture.check_fixture',side_effect=RuntimeError('handler forbidden')):raise SystemExit(main("+repr(['select-case-depths',str(report),'--case','retry-fixed'])+"))";assert subprocess.run([sys.executable,'-c',code],capture_output=True).returncode==0
 for args in [['--case','unknown'],['--case','retry-fixed','--case','retry-fixed']]:
  r=cli('select-case-depths',report,*args);assert r.returncode==2 and not r.stdout
 bad=copy.deepcopy(value);bad['results'][-1]['scenario_sha256']='bad';report.write_text(json.dumps(bad));r=cli('select-case-depths',report,'--case','retry-fixed');assert r.returncode==2 and not r.stdout;report.write_bytes(original);assert report.read_bytes()==original
else:assert json.loads((root/'download.json').read_text())==json.loads((root/'expected.json').read_text())
