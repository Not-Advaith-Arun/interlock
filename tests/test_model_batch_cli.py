"""Check an explicit scenario collection while retaining independent coverage."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ModelBatchAcceptance(unittest.TestCase):
    def test_batch_preserves_individual_verdicts_and_validates_every_input_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); files=[root/'conflict.json',root/'control.json']; report=root/'report.json'
            for target,name in zip(files,('multi_job_retry_conflict.json','multi_job_retry_safe.json')):
                target.write_bytes((ROOT/'examples'/name).read_bytes())
            originals={p:p.read_bytes() for p in files}
            def cli(*args,expected=0,trapped=False):
                code=("import sys; from unittest.mock import patch; from interlock.cli import main\n"
                      "with patch('interlock.model_batch.run_check',side_effect=RuntimeError('search must not start')):\n"
                      " raise SystemExit(main(sys.argv[1:]))\n")
                command=[sys.executable,'-c',code] if trapped else [sys.executable,'-m','interlock']
                r=subprocess.run([*command,*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=15)
                self.assertEqual(r.returncode,expected,r.stdout+r.stderr)
                return json.loads(r.stdout) if r.stdout else r
            batch=cli('check-many',*files,'--max-depth','8','--max-states','10000','--report',report,expected=1)
            self.assertEqual(json.loads(report.read_bytes()),batch)
            self.assertTrue(batch['any_failure']);self.assertFalse(batch['any_incomplete'])
            self.assertEqual(batch['requested_state_budget'],20000)
            for row,file in zip(batch['cases'],files):
                individual=cli('check',file,'--max-depth','8','--max-states','10000','--json',expected=1 if file==files[0] else 0)
                self.assertEqual(row['report'],individual)
            incomplete=cli('check-many',*files,'--max-states','1',expected=3)
            self.assertTrue(incomplete['any_incomplete']);self.assertEqual(len(incomplete['cases']),2)
            cli('check-many',files[0],files[0],expected=2,trapped=True)
            cli('check-many',*files,'--max-states','100001',expected=2,trapped=True)
            cli('check-many',*files,'--report',files[0],'--force',expected=2,trapped=True)
            files[1].write_text('{}');cli('check-many',*files,expected=2,trapped=True)
            self.assertEqual(files[0].read_bytes(),originals[files[0]])
            self.assertEqual(files[1].read_text(),'{}')
            self.assertEqual(json.loads(report.read_bytes()),batch)
