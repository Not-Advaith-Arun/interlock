"""CLI journeys through exploration, real handlers, exported witnesses and replay."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from interlock.scenario import fingerprint

ROOT = Path(__file__).resolve().parents[1]


class EndToEndTests(unittest.TestCase):
    def cli(self, *args, expected=0, timeout=60):
        result = subprocess.run([sys.executable, "-m", "interlock", *map(str, args)],
                                cwd=ROOT, capture_output=True, text=True, timeout=timeout)
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
            profiling = ("--profile",) if sys.platform.startswith("linux") else ()
            checked = self.cli("check", scenario, "--fixture", "multi-job-retry-conflict",
                               "--witness", witness, *profiling, "--json", expected=1)
            self.assertEqual(checked["status"], "merge_interaction_found")
            if profiling:
                self.assertGreaterEqual(checked["measurements"]["wall_seconds"], 0)
                self.assertGreaterEqual(checked["measurements"]["process_cpu_seconds"], 0)
                self.assertGreater(checked["measurements"]["process_peak_rss_bytes"], 0)
                self.assertEqual(checked["measurements"]["platform"], "linux")
            replayed = self.cli("replay", witness, "--fixture", "multi-job-retry-conflict", "--json", expected=1)
            self.assertTrue(replayed["interaction_reproduced"])
            original = witness.read_bytes()
            view = self.cli("view-witness", witness, "--fixture", "multi-job-retry-conflict", "--max-frames", "2")
            self.assertIn("Interlock witness review", view)
            self.assertIn("Showing 2 of 8 recorded states", view)
            self.assertIn("merged: FAIL", view)
            self.assertIn("source identity: verified", view)
            self.assertNotIn("<script", view)
            self.assertEqual(witness.read_bytes(), original)

            reduced = self.cli("minimize", witness, "--model-only", "--json")
            self.assertTrue(reduced["one_event_deletion_minimal"])
            self.assertEqual(reduced["reduced_events"], json.loads(original)["events"])
            self.assertEqual(reduced["source_verification"], "not_checked")
            self.cli("minimize", witness, "--json", expected=2)
            self.cli("minimize", witness, "--model-only", "--report", witness, "--force", expected=2)
            self.assertEqual(witness.read_bytes(), original)
            imported = {key: value for key, value in json.loads(original).items()
                        if key in ("format", "scenario", "scenario_sha256", "events")}
            imported["format"] = "interlock-witness-v1"
            imported["events"].append("acknowledge:a:1")
            padded = Path(directory) / "imported.json"
            padded.write_text(json.dumps(imported))
            untrusted = json.loads(json.dumps(imported))
            untrusted["scenario"]["name"] = "<script>untrusted label</script>"
            untrusted["scenario_sha256"] = fingerprint(untrusted["scenario"])
            view_input = Path(directory) / "view-input.json"
            view_input.write_text(json.dumps(untrusted))
            view = self.cli("view-witness", view_input, "--model-only")
            self.assertIn("&lt;script&gt;untrusted label&lt;/script&gt;", view)
            self.assertNotIn("<script", view)

            comparison = self.cli("compare-witnesses", witness, padded, "--model-only")
            self.assertEqual(comparison["common_event_prefix_length"], len(json.loads(original)["events"]))
            self.assertFalse(comparison["identical_events"])
            self.assertEqual(comparison["source_verification"], "not_checked")
            identical = self.cli("compare-witnesses", witness, witness, "--model-only")
            self.assertTrue(identical["identical_events"])
            self.assertEqual(identical["final_outcome_changes"], [])
            self.cli("compare-witnesses", witness, view_input, "--model-only", expected=2)
            self.assertEqual(witness.read_bytes(), original)
            padded_bytes = padded.read_bytes()
            reduced = self.cli("minimize", padded, "--model-only", "--json")
            self.assertGreater(reduced["removed_events"], 0)
            self.assertTrue(reduced["one_event_deletion_minimal"])
            self.assertTrue(reduced["replay"]["interaction_reproduced"])
            capped = self.cli("minimize", padded, "--model-only", "--max-attempts", "1", "--json", expected=3)
            self.assertFalse(capped["one_event_deletion_minimal"])
            self.assertEqual(capped["status"], "budget_exhausted")
            self.assertEqual(padded.read_bytes(), padded_bytes)
            diagnostic = Path(directory) / "reduced-report.json"
            self.cli("minimize", padded, "--model-only", "--report", diagnostic, "--json")
            self.assertEqual(json.loads(diagnostic.read_text())["format"], "interlock-trace-reduction-v1")
            tampered = json.loads(original)
            tampered["events"].append("acknowledge:a:1")
            invalid = Path(directory) / "invalid-witness.json"
            invalid.write_text(json.dumps(tampered))
            self.cli("minimize", invalid, "--model-only", "--json", expected=2)
            pinned = json.loads(original)
            pinned["events"].append("acknowledge:a:1")
            pinned["witness_sha256"] = fingerprint({k:v for k,v in pinned.items() if k != "witness_sha256"})
            pinned_file = Path(directory) / "padded-pinned.json"
            pinned_file.write_text(json.dumps(pinned))
            checked_reduction = self.cli("minimize", pinned_file, "--fixture", "multi-job-retry-conflict", "--json")
            self.assertGreater(checked_reduction["removed_events"], 0)
            self.assertEqual(checked_reduction["source_verification"], "verified")
            self.assertTrue(checked_reduction["handler_replay"]["interaction_reproduced"])
            self.assertIsNone(checked_reduction["first_mismatch"])
            self.cli("minimize", padded, "--fixture", "multi-job-retry-conflict", "--json", expected=2)
            pinned["fixture"]["source_identity"]["deliberately_invalid"] = True
            pinned["witness_sha256"] = fingerprint({k:v for k,v in pinned.items() if k != "witness_sha256"})
            pinned_file.write_text(json.dumps(pinned))
            self.cli("minimize", pinned_file, "--fixture", "multi-job-retry-conflict", "--json", expected=2)
            fifo = Path(directory) / "unavailable.json"
            os.mkfifo(fifo)
            self.cli("check", fifo, "--witness", witness, "--force", "--json", expected=2, timeout=3)
            self.cli("replay", fifo, "--json", expected=2, timeout=3)
            self.assertEqual(witness.read_bytes(), original)
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
