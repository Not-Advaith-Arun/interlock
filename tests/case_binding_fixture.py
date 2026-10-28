"""Real bounded report to declaration binding, with no search during inspection."""
from pathlib import Path
import sys,json,subprocess
from interlock.case_template import case_template
root=Path(sys.argv[1]);manifest=root/'cases.json';report=root/'run.json';value=case_template(['retry-fixed','retry-conflict']);manifest.write_text(json.dumps(value))
def cli(*args):return subprocess.run([sys.executable,'-m','interlock',*map(str,args)],text=True,capture_output=True)
r=cli('check-cases',manifest,'--max-depth','1','--max-states','10','--report',report);assert r.returncode in [0,1,2],r.stderr;assert report.exists()
before=[manifest.read_bytes(),report.read_bytes()];base=['inspect-case-binding',str(manifest),str(report)];r=cli(*base);assert r.returncode==0,r.stderr;assert json.loads(r.stdout)['matches_declarations'];(root/'expected.json').write_text(r.stdout);(root/'binding.html').write_text(cli(*base,'--html').stdout)
code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.model_batch.run_check',side_effect=RuntimeError('forbidden')):raise SystemExit(main("+repr(base)+"))";assert subprocess.run([sys.executable,'-c',code],capture_output=True).returncode==0
bad=json.loads(before[1]);bad['cases'][0]['scenario_sha256']='0'*64;report.write_text(json.dumps(bad));r=cli(*base);assert r.returncode==1 and not json.loads(r.stdout)['matches_declarations'];report.write_bytes(before[1]);r=cli(*base,'--case',value['cases'][0]['id']);assert r.returncode==1;assert 'unexpected_record'in r.stdout
bad=json.loads(before[1]);bad['cases'][0]['report']['coverage']['states_explored']=True;report.write_text(json.dumps(bad));r=cli(*base);assert r.returncode==2 and not r.stdout;report.write_bytes(before[1]);assert[manifest.read_bytes(),report.read_bytes()]==before
