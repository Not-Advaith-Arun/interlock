"""Inspect bounded trace pages without truncating replay or final verdicts."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class ReplayTracePageAcceptance(unittest.TestCase):
    def test_model_and_handler_pages_preserve_full_sequence_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            witness=Path(directory)/'witness.json'
            def cli(*args,expected=0):
                r=subprocess.run([sys.executable,'-m','interlock',*map(str,args)],cwd=ROOT,
                                 capture_output=True,text=True,timeout=15)
                self.assertEqual(r.returncode,expected,r.stdout+r.stderr)
                return json.loads(r.stdout) if r.stdout else r
            cli('check',ROOT/'examples/multi_job_retry_conflict.json','--fixture','multi-job-retry-conflict','--witness',witness,'--json',expected=1)
            original=witness.read_bytes()
            for mode,field in ((['--model-only'],'outcomes'),(['--fixture','multi-job-retry-conflict','--require-pin'],'observed_outcomes')):
                args=['replay',witness,*mode,'--json'];full=cli(*args,expected=1);frames=[];cursor=0;identity=None
                while True:
                    page=cli(*args,'--trace-limit','2','--from-step',cursor,expected=1)
                    self.assertEqual(page[field],full[field]);self.assertEqual(page['interaction_reproduced'],full['interaction_reproduced'])
                    if 'agreement' in full:self.assertEqual(page['agreement'],full['agreement'])
                    meta=page['trace_page'];self.assertEqual(meta['total_frames'],len(full['trace']))
                    identity=identity or meta['witness_sha256'];self.assertEqual(meta['witness_sha256'],identity)
                    frames.extend(page['trace'])
                    if not meta['has_more']:break
                    cursor=meta['next_from_step']
                self.assertEqual(frames,full['trace'])
                empty=cli(*args,'--trace-limit','2','--from-step',len(full['trace']),expected=1)
                self.assertEqual(empty['trace'],[]);self.assertEqual(empty[field],full[field]);self.assertFalse(empty['trace_page']['has_more'])
            for extra in (['--trace-limit','0','--json'],['--trace-limit','2'],['--trace-limit','2','--summary','--json'],['--from-step','1','--json']):
                cli('replay',witness,'--model-only',*extra,expected=2)
            self.assertEqual(witness.read_bytes(),original)
