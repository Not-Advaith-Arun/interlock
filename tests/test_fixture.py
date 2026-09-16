from collections import deque
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import replace
import difflib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from interlock.cli import main
from interlock.engine import make_witness, search
from interlock.fixture import (CONFLICT, FIXED, FIXTURES, FixtureRuntime, JOB,
                              check_fixture, replay_fixture, source_identity)
from interlock.models import RetryModel
from interlock.scenario import read_json

ROOT = Path(__file__).resolve().parents[1]


def scenario(name="retry_conflict"):
    return read_json(ROOT / "examples" / (name + ".json"))


class ExtraEffectWorker(CONFLICT.revisions["merged"].worker):
    """Deliberately divergent trusted test code, unavailable through JSON or CLI."""
    def receive(self, job):
        super().receive(job)
        self.effects.perform(job)


def divergent():
    revisions = dict(CONFLICT.revisions)
    revisions["merged"] = replace(revisions["merged"], worker=ExtraEffectWorker)
    return replace(CONFLICT, revisions=revisions)


class FixtureTests(unittest.TestCase):
    def test_discovered_witness_executes_actual_business_effects(self):
        data = scenario()
        witness = make_witness(data, search(data))
        result = replay_fixture(data, witness["events"], "retry-conflict")
        self.assertTrue(result["agreement"])
        self.assertTrue(result["interaction_reproduced"])
        self.assertEqual(result["executed_steps"], 4)
        self.assertEqual({v: len(outcome["effect_records"]) for v, outcome in result["observed_outcomes"].items()},
                         {"base": 1, "left": 1, "right": 1, "merged": 2})
        self.assertEqual(result["trace"][3]["stuttered"], ["base", "right"])
        self.assertEqual(result["observed_outcomes"]["left"]["clock"], 10)
        self.assertEqual(result["observed_outcomes"]["base"]["clock"], 0)
        self.assertEqual(result["observed_outcomes"]["merged"]["effect_records"][0],
                         result["observed_outcomes"]["merged"]["effect_records"][1])

    def test_handlers_work_when_model_step_is_forbidden(self):
        runtime = FixtureRuntime(CONFLICT.revisions["merged"])
        with patch.object(RetryModel, "step", side_effect=AssertionError("implementation called model.step")):
            for event in ("submit", "deliver", "timeout", "deliver"):
                self.assertTrue(runtime.dispatch(event))
            observed = runtime.snapshot()
        self.assertEqual(len(observed["effect_records"]), 2)
        self.assertEqual(observed["violations"], ["at_most_one_effect_per_job"])

    def test_every_handler_generated_schedule_agrees_with_model(self):
        # Enumerate from actual runtime enabled actions, independently of model
        # search/replay. No state deduplication hides history-dependent behavior.
        for name, data in (("retry-conflict", scenario()), ("retry-fixed", scenario("retry_safe"))):
            with self.subTest(fixture=name):
                queue, checked = deque([()]), 0
                while queue:
                    events = queue.popleft()
                    runtimes = [FixtureRuntime(revision) for revision in FIXTURES[name].revisions.values()]
                    for event in events:
                        for runtime in runtimes:
                            runtime.dispatch(event)
                    result = replay_fixture(data, events, name)
                    self.assertTrue(result["agreement"], (events, result["first_mismatch"]))
                    checked += 1
                    if len(events) < 8:
                        enabled = sorted({event for runtime in runtimes for event in runtime.enabled()})
                        queue.extend(events + (event,) for event in enabled)
                self.assertEqual(checked, 42)

    def test_full_bounded_fixture_check_and_budget(self):
        result = check_fixture(scenario(), "retry-conflict")
        self.assertEqual(result["status"], "agreement")
        self.assertEqual(result["coverage"]["schedules_checked"], 42)
        self.assertTrue(result["coverage"]["complete_up_to_depth"])
        incomplete = check_fixture(scenario(), "retry-conflict", max_schedules=1)
        self.assertEqual(incomplete["status"], "incomplete")
        self.assertFalse(incomplete["coverage"]["complete_up_to_depth"])
        initial = check_fixture(scenario(), "retry-conflict", max_depth=0)
        self.assertEqual(initial["status"], "agreement")
        self.assertEqual(initial["coverage"]["schedules_checked"], 1)

    def test_deliberately_divergent_handler_fails_at_first_effect(self):
        with patch.dict(FIXTURES, {"retry-conflict": divergent()}):
            result = check_fixture(scenario(), "retry-conflict")
        self.assertEqual(result["status"], "fixture_mismatch")
        failure = result["first_mismatch"]
        self.assertEqual(failure["events"], ["submit", "deliver"])
        self.assertEqual(failure["first_mismatch"]["step"], 2)
        self.assertFalse(failure["interaction_reproduced"])
        self.assertTrue(any(item["field"] == "effect_records" for item in failure["first_mismatch"]["differences"]))

    def test_broken_model_cannot_make_fixture_agreement_pass(self):
        original = RetryModel.step
        def broken(model, state, event, config):
            updated = original(model, state, event, config)
            if event == "deliver":
                updated["effects"] = 0
            return updated
        with patch.object(RetryModel, "step", broken):
            result = replay_fixture(scenario(), ["submit", "deliver"], "retry-conflict")
        self.assertFalse(result["agreement"])
        self.assertEqual(result["first_mismatch"]["step"], 2)

    def test_handler_exception_becomes_a_trace_mismatch(self):
        class RaisingWorker(CONFLICT.revisions["merged"].worker):
            def receive(self, job):
                raise RuntimeError("deliberate handler failure")
        revisions = dict(CONFLICT.revisions)
        revisions["merged"] = replace(revisions["merged"], worker=RaisingWorker)
        with patch.dict(FIXTURES, {"retry-conflict": replace(CONFLICT, revisions=revisions)}):
            result = replay_fixture(scenario(), ["submit", "deliver"], "retry-conflict")
        self.assertFalse(result["agreement"])
        errors = [item for item in result["first_mismatch"]["differences"] if item["field"] == "handler_exception"]
        self.assertEqual(errors[0]["observed"], "RuntimeError: deliberate handler failure")

    def test_same_witness_is_safe_in_compatible_fixed_code(self):
        events = search(scenario())["candidate"]["events"]
        result = replay_fixture(scenario("retry_safe"), events, "retry-fixed")
        self.assertTrue(result["agreement"])
        self.assertFalse(result["interaction_reproduced"])
        self.assertTrue(all(len(value["effect_records"]) == 1 for value in result["observed_outcomes"].values()))
        runtime = FixtureRuntime(FIXED.revisions["merged"])
        for event in events:
            runtime.dispatch(event)
        self.assertEqual(runtime.worker.duplicate_diagnostics, [JOB.job_id])

    def test_ack_and_timer_delivery_obey_real_handler_lifecycle(self):
        runtime = FixtureRuntime(CONFLICT.revisions["merged"])
        runtime.dispatch("submit")
        runtime.clock.advance_to(9)
        self.assertFalse(runtime.producer.on_timeout())
        self.assertEqual(len(runtime.transport.requests), 1)
        runtime.dispatch("deliver")
        runtime.dispatch("timeout")
        runtime.dispatch("acknowledge")
        self.assertNotIn("timeout", runtime.enabled())
        self.assertFalse(runtime.dispatch("timeout"))
        runtime.dispatch("deliver")
        self.assertEqual(len(runtime.effects.records), 2)

    def test_lost_acknowledgement_executes_independent_handler_path(self):
        result = replay_fixture(scenario(), ["submit", "deliver", "drop_ack", "timeout", "deliver"], "retry-conflict")
        self.assertTrue(result["agreement"])
        self.assertTrue(result["interaction_reproduced"])

    def test_fixture_does_not_accept_arbitrary_configuration_or_code(self):
        for name in ("os:system", "../worker.py", "retry-fixed"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                replay_fixture(scenario(), [], name)
        changed = scenario()
        changed["versions"]["left"]["retry_limit"] = 2
        with self.assertRaisesRegex(ValueError, "exact bundled"):
            replay_fixture(changed, [], "retry-conflict")
        with self.assertRaises(ValueError):
            replay_fixture(scenario("callback_conflict"), [], "retry-conflict")

    def test_replay_and_schedule_bounds_remain_enforced(self):
        with self.assertRaises(ValueError):
            replay_fixture(scenario(), ["submit"] * 1001, "retry-conflict")
        with self.assertRaisesRegex(ValueError, "disabled"):
            replay_fixture(scenario(), ["deliver"], "retry-conflict")
        for value in (-1, 65, True):
            with self.assertRaises(ValueError):
                check_fixture(scenario(), "retry-conflict", max_depth=value)
        for value in (0, 10001, True):
            with self.assertRaises(ValueError):
                check_fixture(scenario(), "retry-conflict", max_schedules=value)

    def test_sources_and_patches_show_nonoverlapping_merge(self):
        root = ROOT / "interlock/fixtures/retry"
        for name in ("producer.py", "worker.py"):
            base = (root / "base" / name).read_text()
            left = (root / "left" / name).read_text()
            right = (root / "right" / name).read_text()
            merged = (root / "merged" / name).read_text()
            self.assertEqual(merged, left if name == "producer.py" else right)
            self.assertEqual(base, right if name == "producer.py" else left)
            changed = left if name == "producer.py" else right
            self.assertNotEqual(base, changed)
            expected = "".join(difflib.unified_diff(base.splitlines(True), changed.splitlines(True),
                                                  fromfile="a/" + name, tofile="b/" + name))
            fixture = "left-add-retry.patch" if name == "producer.py" else "right-remove-guard.patch"
            self.assertEqual((ROOT / "examples/source-patches" / fixture).read_text(), expected)
        identity = source_identity("retry-conflict")
        self.assertEqual(len(identity["sha256"]), 64)
        self.assertEqual(identity, source_identity("retry-conflict"))
        self.assertNotEqual(identity["sha256"], source_identity("retry-fixed")["sha256"])


class FixtureCliTests(unittest.TestCase):
    def invoke(self, *args):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(list(args))
        return code, output.getvalue(), error.getvalue()

    def test_opt_in_check_witness_and_replay_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            witness = str(Path(directory) / "witness.json")
            report = str(Path(directory) / "report.json")
            code, output, error = self.invoke("check", str(ROOT / "examples/retry_conflict.json"),
                "--fixture", "retry-conflict", "--witness", witness, "--report", report, "--json")
            self.assertEqual(code, 1, error)
            checked = json.loads(output)
            self.assertEqual(checked["fixture"]["status"], "agreement")
            self.assertEqual(json.loads(Path(report).read_text()), checked)
            code, output, error = self.invoke("replay", witness, "--fixture", "retry-conflict", "--json")
            self.assertEqual(code, 1, error)
            self.assertTrue(json.loads(output)["interaction_reproduced"])

    def test_fixture_mismatch_has_exit_four_and_never_emits_witness(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(FIXTURES, {"retry-conflict": divergent()}):
            witness = Path(directory) / "witness.json"
            code, output, error = self.invoke("check", str(ROOT / "examples/retry_conflict.json"),
                "--fixture", "retry-conflict", "--witness", str(witness), "--json")
            self.assertEqual(code, 4, error)
            result = json.loads(output)
            self.assertEqual(result["status"], "fixture_mismatch")
            self.assertEqual(result["model_status"], "merge_interaction_found")
            self.assertFalse(witness.exists())

    def test_fixed_control_has_exit_zero(self):
        code, output, error = self.invoke("check", str(ROOT / "examples/retry_safe.json"),
                                         "--fixture", "retry-fixed", "--json")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["fixture"]["status"], "agreement")

    def test_replay_mismatch_reports_step_and_exit_four(self):
        with tempfile.TemporaryDirectory() as directory:
            witness = Path(directory) / "witness.json"
            data = scenario()
            witness.write_text(json.dumps(make_witness(data, search(data))))
            with patch.dict(FIXTURES, {"retry-conflict": divergent()}):
                code, output, error = self.invoke("replay", str(witness), "--fixture", "retry-conflict")
            self.assertEqual(code, 4, error)
            self.assertIn("MISMATCH merged.effect_records", output)
            self.assertIn("Observed interaction reproduced: false", output)

    def test_model_budget_stop_skips_real_code_schedule_enumeration(self):
        with patch("interlock.cli.check_fixture", side_effect=AssertionError("budget bypass")):
            code, output, error = self.invoke("check", str(ROOT / "examples/retry_conflict.json"),
                "--fixture", "retry-conflict", "--max-states", "1", "--json")
        self.assertEqual(code, 3, error)
        self.assertEqual(json.loads(output)["fixture"]["status"], "not_run")

    def test_default_model_check_never_constructs_real_handlers(self):
        with patch("interlock.fixture.FixtureRuntime", side_effect=AssertionError("fixture needs opt-in")):
            code, _, error = self.invoke("check", str(ROOT / "examples/retry_conflict.json"), "--json")
        self.assertEqual(code, 1, error)


if __name__ == "__main__":
    unittest.main()
