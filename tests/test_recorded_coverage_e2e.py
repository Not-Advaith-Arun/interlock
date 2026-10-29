"""Retained native report contradictions must never become completed coverage claims."""
import copy,json,subprocess,sys,tempfile,unittest
from pathlib import Path
from interlock.case_template import case_template

class RecordedCoverageWorkflow(unittest.TestCase):
    def test_native_incomplete_grid_cannot_claim_completed_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);manifest=root/'cases.json';report=root/'grid.json';manifest.write_text(json.dumps(case_template(['retry-fixed','retry-conflict'])))
            def cli(*args):return subprocess.run([sys.executable,'-m','interlock',*map(str,args)],capture_output=True,text=True)
            result=cli('check-case-depths',manifest,'--depth','1','--depth','4','--max-states','2');self.assertEqual(result.returncode,2,result.stderr);good=json.loads(result.stdout);report.write_text(result.stdout)
            consumers=[['case-depth-summary',report],['compare-case-depths',report,report],['select-case-depths',report,'--case','retry-fixed']]
            for args in consumers:self.assertEqual(cli(*args).returncode,0)
            # Mutate an omitted case's late incomplete row; the entire matrix must validate.
            changes=[{'complete_up_to_depth':True},{'termination_reason':'state_space_exhausted'},{'states_explored':999},{'states_discovered':999},{'depth_reached':999},{'depth_limited_states':999}]
            for change in changes:
                bad=copy.deepcopy(good);self.assertEqual(bad['results'][-1]['verdict'],'incomplete');bad['results'][-1]['coverage'].update(change);report.write_text(json.dumps(bad));original=report.read_bytes()
                for args in consumers:
                    with self.subTest(change=change,consumer=args[0]):
                        result=cli(*args);self.assertEqual(result.returncode,2);self.assertEqual(result.stdout,'');self.assertEqual(report.read_bytes(),original)
            report.write_text(json.dumps(good));summary=json.loads(cli('case-depth-summary',report).stdout);self.assertEqual(summary['cases'][0]['highest_recorded_complete_depth'],1)
