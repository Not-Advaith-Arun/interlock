"""Piped custom regressions retain strict input and pre-publication boundaries."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class CaseStdinAcceptance(unittest.TestCase):
    def test_bounded_stdin_matches_file_workflow_and_invalid_input_preserves_report(self):
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/'report.json';case={'id':'baseline','expected_status':'baseline_failure','scenario':json.loads((ROOT/'examples/baseline_failure.json').read_text())};payload=json.dumps({'format':'interlock-model-cases-v1','cases':[case]})
            def cli(raw,expected=0,trapped=False):
                code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.model_batch.run_check',side_effect=RuntimeError('search forbidden')):raise SystemExit(main())\n"
                cmd=[sys.executable,'-c',code] if trapped else [sys.executable,'-m','interlock']
                r=subprocess.run([*cmd,'check-cases','-','--case','baseline','--summary','--report',str(report),'--force'],cwd=ROOT,input=raw,capture_output=True,text=True,timeout=8)
                self.assertEqual(r.returncode,expected,r.stdout+r.stderr);return json.loads(r.stdout) if r.stdout else r
            summary=cli(payload);self.assertEqual(summary['status'],'passed');self.assertEqual(json.loads(report.read_bytes())['cases'][0]['id'],'baseline');saved=report.read_bytes()
            for invalid in (payload.replace('"format":','"format":"shadow","format":',1),' '*2000001,payload.replace('"cases":','"cases":NaN,"unused":',1)):
                refused=cli(invalid,expected=2,trapped=True);self.assertEqual(refused.stdout,'');self.assertNotIn('search forbidden',refused.stderr);self.assertEqual(report.read_bytes(),saved)
            self.assertEqual(list(Path(directory).iterdir()),[report])
