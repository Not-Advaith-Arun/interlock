"""Expected model regressions never turn incomplete/unsafe scope into safety."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ModelCaseAcceptance(unittest.TestCase):
    def test_custom_expectations_preserve_full_reports_and_never_accept_incomplete(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);manifest=root/'cases.json';report=root/'report.json'
            def cli(*args,expected=0,trapped=False):
                code=("import sys; from unittest.mock import patch; from interlock.cli import main\n"
                      "with patch('interlock.model_batch.run_check',side_effect=RuntimeError('search must not start')):\n"
                      " raise SystemExit(main(sys.argv[1:]))\n")
                cmd=[sys.executable,'-c',code] if trapped else [sys.executable,'-m','interlock']
                r=subprocess.run([*cmd,*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=15)
                self.assertEqual(r.returncode,expected,r.stdout+r.stderr)
                return json.loads(r.stdout) if r.stdout else r
            cases=[{'id':label,'expected_status':status,'scenario':json.loads((ROOT/'examples'/name).read_text())}
                   for label,status,name in (('conflict','merge_interaction_found','multi_job_retry_conflict.json'),('control','no_interaction_within_bound','multi_job_retry_safe.json'),('baseline','baseline_failure','baseline_failure.json'))]
            payload={'format':'interlock-model-cases-v1','cases':cases};manifest.write_text(json.dumps(payload));original=manifest.read_bytes()
            args=('check-cases',manifest,'--report',report)
            passed=cli(*args);self.assertEqual(passed['status'],'passed');self.assertTrue(all(r['verdict']=='passed' for r in passed['cases']))
            self.assertEqual(passed['cases'][2]['report']['status'],'baseline_failure');self.assertEqual(json.loads(report.read_bytes()),passed)
            wrong=json.loads(original);wrong['cases'][0]['expected_status']='no_interaction_within_bound';manifest.write_text(json.dumps(wrong))
            unexpected=cli(*args,'--force',expected=1);self.assertEqual(unexpected['cases'][0]['verdict'],'unexpected')
            low=cli(*args,'--force','--max-states','1',expected=3);self.assertEqual(low['status'],'incomplete');self.assertTrue(any(r['verdict']=='incomplete' for r in low['cases']))
            saved=report.read_bytes();invalid=json.loads(original);invalid['cases'][-1]['expected_status']='incomplete';manifest.write_text(json.dumps(invalid))
            cli(*args,'--force',expected=2,trapped=True);self.assertEqual(report.read_bytes(),saved)
            manifest.write_bytes(original);cli('check-cases',manifest,'--report',manifest,'--force',expected=2,trapped=True);self.assertEqual(manifest.read_bytes(),original)
