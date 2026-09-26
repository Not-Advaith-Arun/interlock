"""Execute an explicit schedule prefix without claiming suffix outcomes."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from interlock.scenario import fingerprint

ROOT=Path(__file__).resolve().parents[1]


class PrefixReplayAcceptance(unittest.TestCase):
    def test_prefix_outcomes_match_full_frames_but_unexecuted_suffix_remains_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);witness=root/'witness.json';imported=root/'imported.json'
            def cli(*args,expected=0,trapped=False):
                code=("import sys; from unittest.mock import patch; from interlock.cli import main\n"
                      "with patch('interlock.prefix_replay.replay_fixture',side_effect=RuntimeError('handlers must not start')):\n"
                      " raise SystemExit(main(sys.argv[1:]))\n")
                cmd=[sys.executable,'-c',code] if trapped else [sys.executable,'-m','interlock']
                r=subprocess.run([*cmd,*map(str,args)],cwd=ROOT,capture_output=True,text=True,timeout=15)
                self.assertEqual(r.returncode,expected,r.stdout+r.stderr)
                return json.loads(r.stdout) if r.stdout else r
            cli('check',ROOT/'examples/multi_job_retry_conflict.json','--fixture','multi-job-retry-conflict','--witness',witness,'--json',expected=1)
            original=witness.read_bytes();value=json.loads(original);count=len(value['events'])
            for mode,outcome_key,frame_key in ((['--model-only'],'outcomes','outcomes'),(['--fixture','multi-job-retry-conflict','--require-pin'],'observed_outcomes','observed')):
                full=cli('replay',witness,*mode,'--json',expected=1)
                for step in (0,count//2,count):
                    wanted=full['trace'][step][frame_key];status=int(any(not row['passed'] for row in wanted.values()))
                    prefix=cli('replay-prefix',witness,*mode,'--through-step',step,expected=status)
                    self.assertEqual(prefix['result'][outcome_key],wanted)
                    self.assertEqual(prefix['result']['trace'],full['trace'][:step+1])
                    self.assertEqual(prefix['executed_event_count'],step);self.assertEqual(prefix['remaining_event_count'],count-step)
                    self.assertEqual(prefix['complete_witness_executed'],step==count)
                    self.assertEqual(prefix['source_verification'],'verified' if outcome_key=='observed_outcomes' else 'not_checked')
            legacy={key:value[key] for key in ('scenario','scenario_sha256','events')};legacy['format']='interlock-witness-v1';legacy['events']=legacy['events']+['illegal-private-suffix']
            imported.write_text(json.dumps(legacy));saved=imported.read_bytes()
            partial=cli('replay-prefix',imported,'--model-only','--through-step',count,expected=1)
            self.assertEqual(partial['remaining_event_count'],1);self.assertNotIn('illegal-private-suffix',json.dumps(partial))
            cli('replay',imported,'--model-only','--json',expected=2);self.assertEqual(imported.read_bytes(),saved)
            forged=json.loads(original);forged['fixture']['source_identity']['false']='binding';forged['witness_sha256']=fingerprint({k:v for k,v in forged.items() if k!='witness_sha256'})
            imported.write_text(json.dumps(forged));cli('replay-prefix',imported,'--fixture','multi-job-retry-conflict','--require-pin','--through-step','0',expected=2,trapped=True)
            for step in (-1,count+1):cli('replay-prefix',witness,'--model-only','--through-step',step,expected=2)
            self.assertEqual(witness.read_bytes(),original)
