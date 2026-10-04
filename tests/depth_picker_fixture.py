from pathlib import Path
import json,subprocess,sys
from interlock.case_template import case_template
root=Path(sys.argv[1]);manifest=root/'cases.json';report=root/'grid.json'
def cli(*args):return subprocess.run([sys.executable,'-m','interlock',*map(str,args)],capture_output=True,text=True)
if len(sys.argv)==2:
 manifest.write_text(json.dumps(case_template(['retry-fixed','retry-conflict'])));r=cli('check-case-depths',manifest,'--depth','1','--depth','4','--max-states','2');assert r.returncode==2,r.stderr;report.write_text(r.stdout);before=report.read_bytes();h=cli('case-depth-picker',report);assert h.returncode==0,h.stderr;(root/'picker.html').write_text(h.stdout);(root/'before').write_bytes(before)
 code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.engine._initial',side_effect=RuntimeError('search forbidden')),patch('interlock.fixture.check_fixture',side_effect=RuntimeError('handler forbidden')):raise SystemExit(main("+repr(['case-depth-picker',str(report),'--json'])+"))";assert subprocess.run([sys.executable,'-c',code],capture_output=True).returncode==0
 bad=json.loads(before);bad['results'][-1]['coverage']['complete_up_to_depth']=True;report.write_text(json.dumps(bad));r=cli('case-depth-picker',report);assert r.returncode==2 and not r.stdout;report.write_bytes(before)
else:
 selected=root/'selected.json';value=json.loads(selected.read_text());original=json.loads((root/'before').read_text());assert value['format']=='interlock-case-depths-v1' and value['selected_cases']==1 and value['omitted_cases']==1 and value['status']=='incomplete';assert value['results']==[r for r in original['results']if r['id']=='retry-fixed'];assert cli('case-depth-summary',selected).returncode==0 and cli('compare-case-depths',selected,selected).returncode==0;assert report.read_bytes()==(root/'before').read_bytes()
