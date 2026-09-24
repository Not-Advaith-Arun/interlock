"""Concise regression output must preserve unsafe/incomplete exit semantics."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class CaseSummaryAcceptance(unittest.TestCase):
    def test_summary_omits_search_payload_but_keeps_complete_file_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);manifest=root/'cases.json';report=root/'full.json'
            scenario=json.loads((ROOT/'examples/baseline_failure.json').read_text());case={'id':'baseline','expected_status':'baseline_failure','scenario':scenario}
            def cli(expected=0,*extra):
                manifest.write_text(json.dumps({'format':'interlock-model-cases-v1','cases':[case]}))
                r=subprocess.run([sys.executable,'-m','interlock','check-cases',str(manifest),'--summary','--report',str(report),'--force',*extra],cwd=ROOT,capture_output=True,text=True,timeout=8)
                self.assertEqual(r.returncode,expected,r.stdout+r.stderr);return json.loads(r.stdout),json.loads(report.read_bytes())
            summary,full=cli();self.assertEqual(summary['status'],'passed');self.assertEqual(summary['cases'][0]['observed_status'],'baseline_failure')
            self.assertNotIn('report',summary['cases'][0]);self.assertIn('report',full['cases'][0]);self.assertEqual(full['cases'][0]['scenario_sha256'],summary['cases'][0]['scenario_sha256'])
            case['expected_status']='no_interaction_within_bound';summary,full=cli(1);self.assertEqual(summary['status'],'unexpected')
            case['scenario']=json.loads((ROOT/'examples/multi_job_retry_conflict.json').read_text());case['expected_status']='merge_interaction_found'
            summary,full=cli(3,'--max-states','1');self.assertEqual(summary['status'],'incomplete');self.assertEqual(summary['cases'][0]['verdict'],'incomplete')
