"""Explicit regression selection never turns omitted declarations into coverage."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class SelectedCaseAcceptance(unittest.TestCase):
    def test_selection_reports_omissions_and_validates_unselected_declarations(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'cases.json'
            cases=[{'id':key,'expected_status':status,'scenario':json.loads((ROOT/'examples'/name).read_text())} for key,status,name in [('bad','merge_interaction_found','multi_job_retry_conflict.json'),('control','no_interaction_within_bound','multi_job_retry_safe.json')]]
            manifest={'format':'interlock-model-cases-v1','cases':cases};path.write_text(json.dumps(manifest))
            def cli(*args,expected=0,trapped=False):
                code="from unittest.mock import patch; from interlock.cli import main\nwith patch('interlock.model_batch.run_check',side_effect=RuntimeError('search forbidden')): raise SystemExit(main())\n"
                cmd=[sys.executable,'-c',code] if trapped else [sys.executable,'-m','interlock']
                r=subprocess.run([*cmd,'check-cases',str(path),*args],cwd=ROOT,capture_output=True,text=True,timeout=10)
                self.assertEqual(r.returncode,expected,r.stdout+r.stderr);return json.loads(r.stdout) if r.stdout else None
            chosen=cli('--case','control');self.assertEqual(chosen['status'],'passed');self.assertEqual(chosen['selected_case_ids'],['control']);self.assertEqual(chosen['omitted_cases'],1)
            cli('--case','missing',expected=2,trapped=True);cli('--case','control','--case','control',expected=2,trapped=True)
            cases[0]['scenario']={};path.write_text(json.dumps(manifest));cli('--case','control',expected=2,trapped=True)
