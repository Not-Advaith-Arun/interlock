"""Actual CLI schedule comparison before any replay execution is selected."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from interlock.scenario import fingerprint

ROOT = Path(__file__).resolve().parents[1]


class StructureComparisonAcceptance(unittest.TestCase):
    def test_static_differences_are_directional_and_do_not_claim_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); left = root/'left.json'; right = root/'right.json'
            scenario = json.loads((ROOT/'examples/multi_job_retry_conflict.json').read_text())
            scenario['name'] = 'Private scenario title'
            base = {'format':'interlock-witness-v1','scenario':scenario,'scenario_sha256':fingerprint(scenario),
                    'events':['private-illegal-event','other-private-event']}
            left.write_text(json.dumps(base)); saved = left.read_bytes()
            code = ("import sys; from unittest.mock import patch; from interlock.cli import main\n"
                    "with patch('interlock.engine._initial',side_effect=RuntimeError('model forbidden')), "
                    "patch('interlock.fixture.replay_fixture',side_effect=RuntimeError('handlers forbidden')), "
                    "patch('interlock.fixture.validate_witness_fixture',side_effect=RuntimeError('source reads forbidden')):\n"
                    " raise SystemExit(main(sys.argv[1:]))\n")
            def compare(a, b, *extra, expected=0):
                r = subprocess.run([sys.executable,'-c',code,'compare-witnesses',str(a),str(b),'--structure-only',*extra],
                                   cwd=ROOT,capture_output=True,text=True,timeout=5)
                self.assertEqual(r.returncode,expected,r.stdout+r.stderr)
                return json.loads(r.stdout) if expected == 0 else r
            same = compare(left,left)
            self.assertTrue(same['identical_events']); self.assertIsNone(same['first_event_difference'])
            for events, difference in ((['private-illegal-event'], {'event_number':2,'left_ended':False,'right_ended':True}),
                                       (['changed'], {'event_number':1,'left_ended':False,'right_ended':False}),
                                       ([], {'event_number':1,'left_ended':False,'right_ended':True})):
                right.write_text(json.dumps({**base,'events':events})); before = right.read_bytes()
                result = compare(left,right)
                self.assertEqual(result['first_event_difference'],difference)
                self.assertEqual(result['common_event_prefix_length'],difference['event_number']-1)
                self.assertEqual(result['execution_scope'],'none')
                self.assertEqual(result['event_legality'],'not_checked')
                self.assertEqual(result['source_verification'],'not_checked')
                for secret in ('Private scenario','private-illegal','other-private','changed'):
                    self.assertNotIn(secret,json.dumps(result))
                reverse = compare(right,left)['first_event_difference']
                self.assertEqual(reverse['left_ended'],difference['right_ended'])
                self.assertEqual(reverse['right_ended'],difference['left_ended'])
                self.assertEqual(right.read_bytes(),before)
            compare(left,left,'--require-pin',expected=2)
            compare(left,left,'--model-only',expected=2)
            right.write_text(json.dumps({**base,'scenario_sha256':'0'*64})); compare(left,right,expected=2)
            self.assertEqual(left.read_bytes(),saved)
