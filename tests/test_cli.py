import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from interlock.cli import _write
from interlock.scenario import MAX_INPUT_BYTES, MAX_WITNESS_BYTES

ROOT = Path(__file__).resolve().parents[1]


def run(*args):
    return subprocess.run([sys.executable, "-m", "interlock", *args], cwd=ROOT,
                          text=True, capture_output=True, check=False)


class CliTests(unittest.TestCase):
    def test_conflict_json_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            witness = str(Path(directory) / "witness.json")
            report = str(Path(directory) / "report.json")
            result = run("check", "examples/retry_conflict.json", "--json",
                         "--witness", witness, "--report", report)
            self.assertEqual(result.returncode, 1, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["status"], "merge_interaction_found")
            self.assertEqual(json.loads(Path(report).read_text()), data)
            result = run("replay", witness, "--json")
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertTrue(json.loads(result.stdout)["interaction_reproduced"])

    def test_safe_exit_zero(self):
        self.assertEqual(run("check", "examples/retry_safe.json").returncode, 0)

    def test_budget_exit_three(self):
        result = run("check", "examples/retry_conflict.json", "--max-states", "1", "--json")
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "incomplete")

    def test_missing_input_exit_two(self):
        result = run("check", "missing.json")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_malformed_witness_exit_two(self):
        result = run("replay", "examples/retry_conflict.json")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)

    def test_output_cannot_overwrite_input_even_with_force(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "scenario.json"
            original = (ROOT / "examples/retry_conflict.json").read_bytes()
            source.write_bytes(original)
            result = run("check", str(source), "--report", str(source), "--force")
            self.assertEqual(result.returncode, 2)
            self.assertEqual(source.read_bytes(), original)

    def test_existing_outputs_and_aliases_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            report, witness = Path(directory) / "report.json", Path(directory) / "witness.json"
            witness.write_text("preserve me")
            result = run("check", "examples/retry_conflict.json", "--report", str(report), "--witness", str(witness))
            self.assertEqual(result.returncode, 2)
            self.assertFalse(report.exists())
            self.assertEqual(witness.read_text(), "preserve me")
            result = run("check", "examples/retry_conflict.json", "--report", str(report), "--witness", str(report))
            self.assertEqual(result.returncode, 2)
            self.assertFalse(report.exists())

    def test_force_refreshes_witness_but_rejects_stale_witness_on_safe_run(self):
        with tempfile.TemporaryDirectory() as directory:
            witness = Path(directory) / "witness.json"
            witness.write_text("old")
            result = run("check", "examples/retry_conflict.json", "--witness", str(witness), "--force")
            self.assertEqual(result.returncode, 1, result.stderr)
            current = witness.read_bytes()
            result = run("check", "examples/retry_safe.json", "--witness", str(witness), "--force")
            self.assertEqual(result.returncode, 2)
            self.assertIn("older run", result.stderr)
            self.assertEqual(witness.read_bytes(), current)

    def test_large_scenarios_emit_replayable_witnesses(self):
        # Both fit the scenario limit; indentation or ASCII escaping previously
        # produced a witness that the same CLI refused to read.
        for prefix in ("event_", "é" * 4):
            with self.subTest(prefix=prefix), tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / "scenario.json"
                witness = Path(directory) / "witness.json"
                versions = {}
                for version in ("base", "left", "right", "merged"):
                    states = {f"s{i}": {
                        "on": {f"{prefix}{j:03}": "s0" for j in range(64)},
                        "violations": []} for i in range(256)}
                    if version == "merged":
                        states["s0"]["violations"] = ["merged_initial_failure"]
                    versions[version] = {"initial": "s0", "states": states}
                data = {"format": "interlock-scenario-v1", "name": "large valid input",
                        "model": "fsm-v1", "versions": versions}
                source.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
                self.assertLess(source.stat().st_size, MAX_INPUT_BYTES)
                checked = run("check", str(source), "--max-depth", "0", "--witness", str(witness), "--json")
                self.assertEqual(checked.returncode, 1, checked.stderr)
                self.assertLessEqual(witness.stat().st_size, MAX_WITNESS_BYTES)
                if prefix != "event_":
                    self.assertGreater(witness.stat().st_size, MAX_INPUT_BYTES)
                replayed = run("replay", str(witness), "--json")
                self.assertEqual(replayed.returncode, 1, replayed.stderr)
                self.assertTrue(json.loads(replayed.stdout)["interaction_reproduced"])
                # Older pretty-printed witnesses are still supported under the
                # distinct cap, rather than relying only on compact new output.
                pretty = json.dumps(json.loads(witness.read_text()), indent=2, sort_keys=True) + "\n"
                self.assertGreater(len(pretty.encode()), MAX_INPUT_BYTES)
                witness.write_text(pretty, encoding="utf-8")
                replayed = run("replay", str(witness), "--json")
                self.assertEqual(replayed.returncode, 1, replayed.stderr)

    def test_witness_limit_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            witness = Path(directory) / "oversized.json"
            witness.write_bytes(b" " * (MAX_WITNESS_BYTES + 1))
            result = run("replay", str(witness), "--json")
            self.assertEqual(result.returncode, 2)
            self.assertIn("16 MB limit", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_output_size_refusal_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "witness.json"
            output.write_text("preserve me")
            with self.assertRaisesRegex(ValueError, "output exceeds"):
                _write(str(output), {"large": "contents"}, force=True, compact=True, max_bytes=1)
            self.assertEqual(output.read_text(), "preserve me")


if __name__ == "__main__":
    unittest.main()
