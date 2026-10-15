"""Comparison of actual stored regressions separates expectation and observation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class CaseComparisonAcceptance(unittest.TestCase):
    def test_real_reports_compare_without_search_and_reject_contradictory_verdicts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);manifest=root/'cases.json';before=root/'before.json';after=root/'after.json'
            case={'id':'baseline','expected_status':'baseline_failure','scenario':json.loads((ROOT/'examples/baseline_failure.json').read_text())}
            def cli(*args,expected=0,trapped=False):
                code="from unittest.mock import patch;from interlock.cli import main\nwith patch('interlock.model_batch.run_check',side_effect=RuntimeError('search forbidden')): raise SystemExit(main())\n"
                cmd=[sys.executable,'-c',code] if trapped else [sys.executable,'-m','interlock']
                r=subprocess.run([*cmd,*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=10)
                self.assertEqual(r.returncode,expected,r.stdout+r.stderr);return json.loads(r.stdout) if r.stdout else None
            manifest.write_text(json.dumps({'format':'interlock-model-cases-v1','cases':[case]}));cli('check-cases',manifest,'--report',before)
            same=cli('compare-case-results',before,before,trapped=True);self.assertEqual(same['unchanged_cases'],1)
            case['expected_status']='no_interaction_within_bound';manifest.write_text(json.dumps({'format':'interlock-model-cases-v1','cases':[case]}));cli('check-cases',manifest,'--report',after,expected=1)
            originals=[p.read_bytes() for p in (before,after)];changed=cli('compare-case-results',before,after,trapped=True)
            self.assertEqual(changed['cases'][0]['changes'],['expected_status','verdict']);self.assertEqual(changed['cases'][0]['before']['observed_status'],changed['cases'][0]['after']['observed_status'])
            self.assertEqual([p.read_bytes() for p in (before,after)],originals)
            altered=json.loads(originals[1]);altered['cases'][0]['id']='renamed';after.write_text(json.dumps(altered));self.assertEqual({c for r in cli('compare-case-results',before,after,trapped=True)['cases'] for c in r['changes']},{'added','removed'})
            altered['cases'][0]['verdict']='passed';after.write_text(json.dumps(altered));cli('compare-case-results',before,after,expected=2,trapped=True)
