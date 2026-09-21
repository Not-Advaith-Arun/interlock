"""Actual static intake before opting into schedule/handler execution."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from interlock.scenario import fingerprint

ROOT=Path(__file__).resolve().parents[1]


class WitnessInspectionAcceptance(unittest.TestCase):
    def test_inspection_never_runs_models_or_handlers_and_does_not_claim_legality(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pinned=root/"pinned.json";imported=root/"imported.json"
            result=subprocess.run([sys.executable,"-m","interlock","check",str(ROOT/"examples/multi_job_retry_conflict.json"),
                "--fixture","multi-job-retry-conflict","--witness",str(pinned),"--json"],cwd=ROOT,capture_output=True,text=True,timeout=15)
            self.assertEqual(result.returncode,1,result.stdout+result.stderr)
            original=pinned.read_bytes();value=json.loads(original)
            code=("import sys; from unittest.mock import patch; from interlock.cli import main\n"
                  "with patch('interlock.engine._initial',side_effect=RuntimeError('model execution forbidden')), "
                  "patch('interlock.cli.replay_fixture',side_effect=RuntimeError('handlers forbidden')), "
                  "patch('interlock.cli.validate_witness_fixture',side_effect=RuntimeError('installed source reads forbidden')):\n"
                  " raise SystemExit(main(sys.argv[1:]))\n")
            def inspect(path, expected=0):
                result=subprocess.run([sys.executable,"-c",code,"inspect-witness",str(path)],cwd=ROOT,
                                      capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,expected,result.stdout+result.stderr)
                return json.loads(result.stdout) if expected==0 else result
            checked=inspect(pinned)
            self.assertTrue(checked["source_binding_recorded"])
            self.assertEqual(checked["execution_scope"],"none")
            self.assertEqual(checked["source_verification"],"not_checked")
            self.assertEqual(checked["event_count"],len(value["events"]))
            self.assertEqual(checked["witness_canonical_sha256"],fingerprint(value))
            legacy={key:value[key] for key in ("scenario","scenario_sha256","events")}
            legacy["format"]="interlock-witness-v1";legacy["events"]=["not-a-legal-event"]
            imported.write_text(json.dumps(legacy));saved=imported.read_bytes()
            static=inspect(imported)
            self.assertFalse(static["source_binding_recorded"])
            self.assertEqual(static["event_legality"],"not_checked")
            replay=subprocess.run([sys.executable,"-m","interlock","replay",str(imported),"--model-only","--json"],
                                  cwd=ROOT,capture_output=True,text=True,timeout=5)
            self.assertEqual(replay.returncode,2)
            self.assertIn("disabled",replay.stderr)
            self.assertEqual(imported.read_bytes(),saved)
            for events in ([None],["event"]*1001):
                imported.write_text(json.dumps({**legacy,"events":events}));inspect(imported,expected=2)
            damaged=json.loads(original);damaged["events"].append("changed")
            imported.write_text(json.dumps(damaged));inspect(imported,expected=2)
            self.assertEqual(pinned.read_bytes(),original)
