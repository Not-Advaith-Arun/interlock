"""A later model-case runtime failure must not publish a misleading partial report."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class MidrunCaseFailureAcceptance(unittest.TestCase):
    def test_failure_after_completed_first_case_keeps_existing_report_and_retry_completes_all(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);manifest=root/'cases.json';report=root/'report.json';marker=root/'first-completed'
            cases=[{'id':label,'expected_status':status,'scenario':json.loads((ROOT/'examples'/name).read_text())} for label,status,name in [('baseline','baseline_failure','baseline_failure.json'),('control','no_interaction_within_bound','multi_job_retry_safe.json')]];manifest.write_text(json.dumps({'format':'interlock-model-cases-v1','cases':cases}));original=manifest.read_bytes();report.write_text('Existing independently reviewed evidence\n');saved=report.read_bytes()
            code=("import sys;from pathlib import Path;from unittest.mock import patch;from interlock.model_batch import run_check;from interlock.cli import main\n"
                  "marker=Path(sys.argv.pop(1));calls=0\n"
                  "def failing(*a,**k):\n"
                  " global calls\n"
                  " calls+=1\n"
                  " if calls==2:raise OSError('controlled second-case runtime interruption')\n"
                  " result=run_check(*a,**k);marker.touch();return result\n"
                  "with patch('interlock.model_batch.run_check',failing):raise SystemExit(main())\n")
            failed=subprocess.run([sys.executable,'-c',code,str(marker),'check-cases',str(manifest),'--report',str(report),'--force','--summary'],cwd=ROOT,capture_output=True,text=True,timeout=8)
            self.assertEqual(failed.returncode,2,failed.stdout+failed.stderr);self.assertTrue(marker.exists());self.assertEqual(failed.stdout,'');self.assertIn('second-case runtime interruption',failed.stderr);self.assertEqual(report.read_bytes(),saved);self.assertEqual(manifest.read_bytes(),original)
            retry=subprocess.run([sys.executable,'-m','interlock','check-cases',str(manifest),'--report',str(report),'--force','--summary'],cwd=ROOT,capture_output=True,text=True,timeout=8)
            self.assertEqual(retry.returncode,0,retry.stdout+retry.stderr);complete=json.loads(report.read_bytes());self.assertEqual([row['id'] for row in complete['cases']],['baseline','control']);self.assertEqual(complete['status'],'passed');self.assertEqual(manifest.read_bytes(),original);self.assertEqual(list(root.glob('*.tmp')),[])
