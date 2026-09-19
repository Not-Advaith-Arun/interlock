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
            safe_sweep = self.cli("sweep-depths", ROOT / "examples/retry_safe.json", "--depth", "0", "--depth", "12", "--model-only")
            self.assertFalse(safe_sweep["any_failure"])
            scenario_bytes = scenario.read_bytes()
            sweep = self.cli("sweep-depths", scenario, "--depth", "0", "--depth", "12", "--model-only", expected=1)
            self.assertEqual([r["depth"] for r in sweep["results"]], [0,12])
            self.assertIsNone(sweep["results"][0]["candidate_events"])
            self.assertTrue(sweep["results"][1]["candidate_events"])
            self.assertEqual(sweep["execution_scope"], "model_only")
            self.assertTrue(all("measurements" not in row for row in sweep["results"]))
            if sys.platform.startswith("linux"):
                measured = self.cli("sweep-depths", scenario, "--depth", "0", "--depth", "12",
                                    "--model-only", "--profile", expected=1)
                for actual, baseline in zip(measured["results"], sweep["results"]):
                    metrics = actual.pop("measurements")
                    self.assertEqual(actual, baseline)
                    self.assertGreaterEqual(metrics["wall_seconds"], 0)
                    self.assertGreaterEqual(metrics["process_cpu_seconds"], 0)
                    self.assertGreater(metrics["process_peak_rss_bytes"], 0)
                    self.assertIn("process-lifetime", metrics["scope"])
            self.cli("sweep-depths", scenario, "--depth", "1", "--depth", "1", "--model-only", expected=2)
            self.cli("sweep-depths", scenario, "--depth", "1", "--max-states", "200001", "--model-only", expected=2)
            self.assertEqual(scenario.read_bytes(), scenario_bytes)
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
            explained = self.cli("minimize", padded, "--model-only", "--max-diagnostics", "2", "--json")
            self.assertEqual(explained["reduced_events"], reduced["reduced_events"])
            self.assertEqual(explained["attempts"], reduced["attempts"])
            self.assertEqual(len(explained["decisions"]), 2)
            self.assertEqual(explained["omitted_decisions"], explained["attempts"] - 2)
            self.assertEqual(explained["decisions"][0]["attempt"], 1)
            self.assertIn(explained["decisions"][0]["outcome"], ("illegal-schedule", "interaction-lost", "removed"))
            self.cli("minimize", padded, "--model-only", "--max-diagnostics", "1001", "--json", expected=2)
            capped = self.cli("minimize", padded, "--model-only", "--max-attempts", "1", "--json", expected=3)
            self.assertFalse(capped["one_event_deletion_minimal"])
            self.assertEqual(capped["status"], "budget_exhausted")
            self.assertEqual(padded.read_bytes(), padded_bytes)
            diagnostic = Path(directory) / "reduced-report.json"
            self.cli("minimize", padded, "--model-only", "--report", diagnostic, "--json")
            self.assertEqual(json.loads(diagnostic.read_text())["format"], "interlock-trace-reduction-v1")
            diagnostic_bytes = diagnostic.read_bytes()
            self.cli("replay", diagnostic, "--json", expected=2)
            self.cli("view-witness", diagnostic, "--model-only", expected=2)
            preserved_report = Path(directory) / "previous-diagnostic.json"
            preserved_report.write_text("preserve prior diagnostic")
            self.cli("minimize", diagnostic, "--model-only", "--report", preserved_report,
                     "--force", "--json", expected=2)
            self.assertEqual(preserved_report.read_text(), "preserve prior diagnostic")
            self.assertEqual(diagnostic.read_bytes(), diagnostic_bytes)
            exhausted_report = Path(directory) / "budget-diagnostic.json"
            exhausted = self.cli("minimize", padded, "--model-only", "--max-attempts", "1",
                                 "--max-diagnostics", "1", "--report", exhausted_report, "--json", expected=3)
            self.assertEqual(json.loads(exhausted_report.read_text()), exhausted)
            self.assertEqual(exhausted["status"], "budget_exhausted")
            self.assertFalse(exhausted["one_event_deletion_minimal"])
            self.assertTrue(exhausted["replay"]["interaction_reproduced"])
            self.cli("replay", exhausted_report, "--json", expected=2)
            self.assertEqual(padded.read_bytes(), padded_bytes)
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
            checked_reduction = self.cli("minimize", pinned_file, "--fixture", "multi-job-retry-conflict", "--max-diagnostics", "1000", "--json")
            self.assertGreater(checked_reduction["removed_events"], 0)
            self.assertEqual(checked_reduction["source_verification"], "verified")
            self.assertTrue(checked_reduction["handler_replay"]["interaction_reproduced"])
            self.assertIsNone(checked_reduction["first_mismatch"])
            self.assertEqual(checked_reduction["omitted_decisions"], 0)
            self.assertTrue(any(row["outcome"] == "removed" for row in checked_reduction["decisions"]))
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

    def test_schedule_comparison_locates_event_divergence_and_ended_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = json.loads((ROOT / "examples/multi_job_retry_conflict.json").read_text())
            base = {"format": "interlock-witness-v1", "scenario": scenario,
                    "scenario_sha256": fingerprint(scenario)}
            left, right, prefix = [root / name for name in ("left.json", "right.json", "prefix.json")]
            common = ["submit:a", "deliver:a:0"]
            for path, events in ((left, common + ["acknowledge:a:0"]),
                                 (right, common + ["drop_ack:a:0"]), (prefix, common)):
                path.write_text(json.dumps({**base, "events": events}))
            originals = {p: p.read_bytes() for p in (left, right, prefix)}
            compared = self.cli("compare-witnesses", left, right, "--model-only")
            first = compared["first_event_difference"]
            self.assertEqual(first["event_number"], 3)
            self.assertEqual(first["left"]["event"], "acknowledge:a:0")
            self.assertEqual(first["right"]["event"], "drop_ack:a:0")
            self.assertFalse(first["left"]["ended"] or first["right"]["ended"])
            for side, path in (("left", left), ("right", right)):
                replayed = self.cli("replay", path, "--json")
                self.assertEqual(first[side]["outcomes"], replayed["trace"][-1]["outcomes"])
            ended = self.cli("compare-witnesses", prefix, left, "--model-only")["first_event_difference"]
            self.assertTrue(ended["left"]["ended"])
            self.assertIsNone(ended["left"]["event"])
            self.assertEqual(ended["left"]["outcomes"], self.cli("replay", prefix, "--json")["trace"][-1]["outcomes"])
            swapped = self.cli("compare-witnesses", left, prefix, "--model-only")["first_event_difference"]
            self.assertEqual(swapped["left"], ended["right"])
            self.assertEqual(swapped["right"], ended["left"])
            self.assertIsNone(self.cli("compare-witnesses", left, left, "--model-only")["first_event_difference"])
            self.assertEqual({p: p.read_bytes() for p in originals}, originals)

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


    def test_depth_budget_exhaustion_cannot_be_reported_as_a_safe_sweep(self):
        scenario = ROOT / "examples/multi_job_retry_conflict.json"
        before = scenario.read_bytes()
        incomplete = self.cli("sweep-depths", scenario, "--depth", "0", "--depth", "12", "--max-states", "1", "--model-only", expected=3)
        self.assertTrue(incomplete["any_incomplete"])
        self.assertEqual(incomplete["results"][1]["status"], "incomplete")
        self.assertFalse(incomplete["results"][1]["coverage"]["complete_up_to_depth"])
        self.assertIsNone(incomplete["results"][1]["candidate_events"])
        shallow = self.cli("sweep-depths", scenario, "--depth", "0", "--max-states", "1", "--model-only")
        self.assertFalse(shallow["any_incomplete"])
        self.assertFalse(shallow["any_failure"])
        self.assertEqual(shallow["results"][0]["bounds"]["max_depth"], 0)
        self.cli("sweep-depths", scenario, "--depth", "0", expected=2)
        self.assertEqual(scenario.read_bytes(), before)
