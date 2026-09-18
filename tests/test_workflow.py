from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from interlock.cli import main
from interlock.engine import search
from interlock.fixture import FIXTURES, check_fixture, fixture_scenario, replay_fixture


class WorkflowTests(unittest.TestCase):
    def invoke(self, *args):
        output, error = StringIO(), StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(list(args))
        return code, output.getvalue(), error.getvalue()

    def test_fixture_discovery_and_examples_do_not_run_handlers(self):
        with patch('interlock.fixture.FixtureRuntime', side_effect=AssertionError('executed')), \
                patch('interlock.cancellation_fixture.CancellationRuntime', side_effect=AssertionError('executed')):
            code, output, error = self.invoke('fixtures', '--json')
            self.assertEqual(code, 0, error)
            self.assertEqual({f['name'] for f in json.loads(output)['fixtures']}, set(FIXTURES))
            for name in FIXTURES:
                code, output, error = self.invoke('example', name)
                self.assertEqual(code, 0, error)
                data = json.loads(output)
                self.assertEqual(data, fixture_scenario(name))
                expected = 'no_interaction_within_bound' if name.endswith('-fixed') else 'merge_interaction_found'
                self.assertEqual(search(data)['status'], expected)

    def test_generated_scenarios_are_independent_and_protected_from_overwrite(self):
        data = fixture_scenario('retry-conflict')
        data['versions']['merged']['retry_limit'] = 16
        self.assertEqual(fixture_scenario('retry-conflict')['versions']['merged']['retry_limit'], 1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'case.json'
            self.assertEqual(self.invoke('example', 'retry-conflict', '--output', str(path))[0], 0)
            before = path.read_bytes()
            self.assertEqual(self.invoke('example', 'retry-fixed', '--output', str(path))[0], 2)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(self.invoke('example', 'retry-fixed', '--output', str(path), '--force')[0], 0)
            link = Path(directory)/'link.json'
            link.symlink_to(path)
            self.assertEqual(self.invoke('example', 'retry-conflict', '--output', str(link), '--force')[0], 2)

    def test_reports_distinguish_depth_and_budget_from_exhaustion(self):
        data = fixture_scenario('cancellation-conflict')
        self.assertEqual(search(data)['coverage']['termination_reason'], 'state_space_exhausted')
        self.assertEqual(search(data, max_depth=2)['coverage']['termination_reason'], 'depth_bound')
        self.assertEqual(search(data, max_states=2)['coverage']['termination_reason'], 'state_budget')
        full = check_fixture(data, 'cancellation-conflict')
        self.assertEqual(full['coverage']['termination_reason'], 'schedule_space_exhausted')
        bounded = check_fixture(data, 'cancellation-conflict', max_depth=2)
        self.assertEqual(bounded['coverage']['termination_reason'], 'depth_bound')
        self.assertTrue(bounded['coverage']['complete_up_to_depth'])
        capped = check_fixture(data, 'cancellation-conflict', max_schedules=2)
        self.assertEqual(capped['coverage']['termination_reason'], 'schedule_budget')
        self.assertFalse(capped['coverage']['complete_up_to_depth'])
        self.assertEqual(capped['coverage']['schedules_pending'], 2)

    def test_schedule_budget_cli_refuses_witness_and_returns_three(self):
        with tempfile.TemporaryDirectory() as directory:
            source, witness, report = [Path(directory)/name for name in ('case.json', 'witness.json', 'report.json')]
            source.write_text(json.dumps(fixture_scenario('cancellation-conflict')))
            code, output, error = self.invoke('check', str(source), '--fixture', 'cancellation-conflict',
                                             '--max-schedules', '2', '--witness', str(witness), '--report', str(report), '--json')
            self.assertEqual(code, 3, error)
            result = json.loads(output)
            self.assertEqual(json.loads(report.read_text()), result)
            self.assertEqual(result['model_status'], 'merge_interaction_found')
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(result['fixture']['coverage']['termination_reason'], 'schedule_budget')
            self.assertFalse(witness.exists())
            witness.write_text('old witness')
            code, _, error = self.invoke('check', str(source), '--fixture', 'cancellation-conflict',
                                         '--max-schedules', '2', '--witness', str(witness), '--force')
            self.assertEqual(code, 2)
            self.assertIn('older run', error)
            self.assertEqual(witness.read_text(), 'old witness')

    def test_schedule_budget_validation_and_exact_completion_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'case.json'
            source.write_text(json.dumps(fixture_scenario('cancellation-fixed')))
            for cap in ('0', '-1', '10001'):
                code, _, error = self.invoke('check', str(source), '--fixture', 'cancellation-fixed', '--max-schedules', cap)
                self.assertEqual(code, 2, error)
            code, _, error = self.invoke('check', str(source), '--max-schedules', '5')
            self.assertEqual(code, 2)
            self.assertIn('requires --fixture', error)
            self.assertEqual(self.invoke('check', str(source), '--fixture', 'cancellation-fixed', '--max-schedules', '5')[0], 0)

    def test_candidate_replay_disagreement_cannot_export_witness(self):
        data = fixture_scenario('cancellation-conflict')
        real_replay = replay_fixture(data, ['start', 'cancel', 'fire_callback'], 'cancellation-conflict')
        real_replay['agreement'] = False
        real_replay['interaction_reproduced'] = False
        with tempfile.TemporaryDirectory() as directory, patch('interlock.cli.replay_fixture', return_value=real_replay):
            source = Path(directory)/'case.json'
            witness = Path(directory)/'witness.json'
            source.write_text(json.dumps(data))
            code, output, error = self.invoke('check', str(source), '--fixture', 'cancellation-conflict', '--witness', str(witness), '--json')
            self.assertEqual(code, 4, error)
            self.assertEqual(json.loads(output)['status'], 'fixture_mismatch')
            self.assertFalse(json.loads(output)['fixture']['coverage']['complete_up_to_depth'])
            self.assertFalse(witness.exists())


if __name__ == '__main__':
    unittest.main()
