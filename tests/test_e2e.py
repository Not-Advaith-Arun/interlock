"""CLI journeys through exploration, real handlers, exported witnesses and replay."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EndToEndTests(unittest.TestCase):
    def cli(self, *args, expected=0):
        result = subprocess.run([sys.executable, "-m", "interlock", *map(str, args)],
                                cwd=ROOT, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return json.loads(result.stdout) if result.stdout.lstrip().startswith("{") else result.stdout

    def test_bundled_handler_corpus_and_historical_calibration(self):
        report = self.cli("suite", "--json")
        self.assertEqual(report["status"], "passed")
        historical = self.cli("historical-waitfor", "--json")
        self.assertEqual(historical["status"], "calibrated")

    def test_generate_check_replay_and_refuse_stale_witness(self):
        with tempfile.TemporaryDirectory() as directory:
            scenario, witness = Path(directory) / "scenario.json", Path(directory) / "witness.json"
            self.cli("example", "multi-job-retry-conflict", "--output", scenario)
            checked = self.cli("check", scenario, "--fixture", "multi-job-retry-conflict",
                               "--witness", witness, "--json", expected=1)
            self.assertEqual(checked["status"], "merge_interaction_found")
            replayed = self.cli("replay", witness, "--fixture", "multi-job-retry-conflict", "--json", expected=1)
            self.assertTrue(replayed["interaction_reproduced"])
            original = witness.read_bytes()
            report = Path(directory) / "report.json"
            report.write_text("preserve prior report")
            for invalid in (Path(directory), witness / "child.json"):
                self.cli("check", scenario, "--fixture", "multi-job-retry-conflict", "--report", report,
                         "--witness", invalid, "--force", "--json", expected=2)
                self.assertEqual(report.read_text(), "preserve prior report")
                self.assertEqual(witness.read_bytes(), original)
            self.cli("check", ROOT / "examples/retry_safe.json", "--witness", witness,
                     "--force", "--json", expected=2)
            self.assertEqual(witness.read_bytes(), original)

    def test_incomplete_or_individually_unsafe_search_cannot_publish_witness(self):
        with tempfile.TemporaryDirectory() as directory:
            witness = Path(directory) / "witness.json"
            self.cli("check", ROOT / "examples/multi_job_retry_conflict.json", "--fixture",
                     "multi-job-retry-conflict", "--max-schedules", "1", "--witness", witness,
                     "--json", expected=3)
            self.assertFalse(witness.exists())
            result = self.cli("check", ROOT / "examples/retry_envelope_branch_failure.json",
                              "--witness", witness, "--json", expected=1)
            self.assertNotEqual(result["status"], "merge_interaction_found")
            self.assertFalse(witness.exists())
