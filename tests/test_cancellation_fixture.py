from collections import deque
from dataclasses import replace
import difflib
import itertools
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from interlock.cancellation_fixture import CancellationRuntime
from interlock.engine import replay, search
from interlock.fixture import FIXTURES, check_fixture, replay_fixture, source_identity
from interlock.models import CancellationModel
from interlock.scenario import read_json, validate_scenario
from tests import test_fixture

ROOT = Path(__file__).resolve().parents[1]


def scenario(safe=False):
    return read_json(ROOT / 'examples' / ('cancellation_safe.json' if safe else 'cancellation_conflict.json'))


class CancellationTests(unittest.TestCase):
    invoke = test_fixture.FixtureCliTests.invoke

    def test_shortest_witness_reproduces_real_future_error(self):
        data = scenario()
        report = search(data)
        self.assertEqual(report['status'], 'merge_interaction_found')
        events = report['candidate']['events']
        self.assertEqual(events, ['start', 'cancel', 'fire_callback'])
        actual = replay_fixture(data, events, 'cancellation-conflict')
        self.assertTrue(actual['agreement'])
        self.assertTrue(actual['interaction_reproduced'])
        self.assertEqual(actual['observed_outcomes']['merged']['error_records'], [{'type': 'InvalidStateError'}])
        for v in ('base', 'left', 'right'):
            self.assertTrue(actual['observed_outcomes'][v]['passed'])
        for n in range(3):
            for shorter in itertools.product(events, repeat=n):
                try:
                    result = replay(data, shorter)
                except ValueError:
                    continue
                self.assertFalse(result['interaction_reproduced'], shorter)

    def test_real_handlers_are_independent_of_model(self):
        with patch.object(CancellationModel, 'step', side_effect=AssertionError('model called')):
            runtime = CancellationRuntime(FIXTURES['cancellation-conflict'].revisions['merged'])
            for event in ('start', 'cancel', 'fire_callback'):
                self.assertTrue(runtime.dispatch(event))
            self.assertTrue(runtime.future.cancelled())
            self.assertEqual(runtime.snapshot()['violations'], ['no_completion_after_cancellation'])
            self.assertFalse(runtime.dispatch('fire_callback'))

    def test_guarded_control_preserves_cancellation_and_successful_completion(self):
        self.assertEqual(search(scenario(True))['status'], 'no_interaction_within_bound')
        cancelled = replay_fixture(scenario(True), ['start', 'cancel', 'fire_callback'], 'cancellation-fixed')
        self.assertTrue(cancelled['agreement'])
        self.assertFalse(cancelled['interaction_reproduced'])
        self.assertEqual(cancelled['observed_outcomes']['merged']['state']['future'], 'cancelled')
        for name, safe in (('cancellation-conflict', False), ('cancellation-fixed', True)):
            completed = replay_fixture(scenario(safe), ['start', 'fire_callback'], name)
            self.assertTrue(completed['agreement'])
            self.assertTrue(all(o['result'] == 'ready' for o in completed['observed_outcomes'].values()))

    def test_independently_enumerated_handler_schedules_all_agree(self):
        for name, safe in (('cancellation-conflict', False), ('cancellation-fixed', True)):
            queue, checked = deque([()]), 0
            while queue:
                events = queue.popleft()
                runtimes = [CancellationRuntime(r) for r in FIXTURES[name].revisions.values()]
                for event in events:
                    for runtime in runtimes:
                        runtime.dispatch(event)
                self.assertTrue(replay_fixture(scenario(safe), events, name)['agreement'], events)
                checked += 1
                enabled = sorted({event for runtime in runtimes for event in runtime.enabled()})
                queue.extend(events + (event,) for event in enabled)
            self.assertEqual(checked, 5)
            report = check_fixture(scenario(safe), name)
            self.assertEqual(report['status'], 'agreement')
            self.assertEqual(report['coverage']['event_steps_executed'], 8)
            self.assertEqual(report['case']['kind'], 'historical_failure_reconstruction_with_synthetic_branch_split')

    def test_buggy_model_and_buggy_handler_cannot_pass_agreement(self):
        with patch.object(CancellationModel, 'violations', return_value=()):
            result = check_fixture(scenario(), 'cancellation-conflict')
            self.assertEqual(result['status'], 'fixture_mismatch')
            self.assertEqual(result['first_mismatch']['first_mismatch']['step'], 3)
        fixture = FIXTURES['cancellation-conflict']

        class WrongPayload(fixture.revisions['merged'].completer):
            def complete(self, future):
                future.set_result('wrong')
                self.records.append({'result': 'wrong'})

        revisions = dict(fixture.revisions)
        revisions['merged'] = replace(revisions['merged'], completer=WrongPayload)
        with patch.dict(FIXTURES, {'cancellation-conflict': replace(fixture, revisions=revisions)}):
            result = check_fixture(scenario(), 'cancellation-conflict')
        self.assertEqual(result['status'], 'fixture_mismatch')
        differences = result['first_mismatch']['first_mismatch']['differences']
        self.assertTrue(any(d['field'] == 'result' for d in differences))

    def test_invalid_configs_and_fixture_pairings_rejected(self):
        data = scenario()
        data['versions']['base']['deferred'] = 1
        with self.assertRaises(ValueError):
            validate_scenario(data)
        with self.assertRaises(ValueError):
            check_fixture(scenario(), 'cancellation-fixed')
        with self.assertRaisesRegex(ValueError, 'disabled'):
            replay_fixture(scenario(), ['cancel'], 'cancellation-conflict')

    def test_patch_composition_and_source_identity(self):
        root = ROOT / 'interlock/fixtures/cancellation'
        for file, branch, label in [('scheduler.py', 'left', 'left-defer-completion'),
                                    ('completion.py', 'right', 'right-remove-cancel-guard')]:
            before = (root/'base'/file).read_text()
            after = (root/branch/file).read_text()
            self.assertNotEqual(before, after)
            self.assertEqual((root/'merged'/file).read_text(), after)
            other = 'right' if branch == 'left' else 'left'
            self.assertEqual((root/other/file).read_text(), before)
            diff = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                               fromfile='a/'+file, tofile='b/'+file))
            self.assertEqual((ROOT/'examples/source-patches'/f'{label}.patch').read_text(), diff)
        identity = source_identity('cancellation-conflict')
        self.assertIn('runtime', identity)
        self.assertNotEqual(identity, source_identity('cancellation-fixed'))
        self.assertIn('cancellation_fixture.py', identity['files'])

    def test_cli_roundtrip_control_shallow_bound_and_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            witness = str(Path(directory)/'witness.json')
            source = str(ROOT/'examples/cancellation_conflict.json')
            code, _, error = self.invoke('check', source, '--fixture', 'cancellation-conflict', '--witness', witness)
            self.assertEqual(code, 1, error)
            code, output, error = self.invoke('replay', witness, '--fixture', 'cancellation-conflict')
            self.assertEqual(code, 1, error)
            self.assertIn('Observed interaction reproduced: true', output)
            self.assertIn('source identity: verified', output)
            code, output, error = self.invoke('check', source, '--fixture', 'cancellation-conflict', '--max-depth', '2', '--json')
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(output)['status'], 'no_interaction_within_bound')
            code, output, error = self.invoke('check', source, '--fixture', 'cancellation-conflict', '--max-states', '2', '--json')
            self.assertEqual(code, 3, error)
            self.assertEqual(json.loads(output)['fixture']['status'], 'not_run')
            code, _, error = self.invoke('check', str(ROOT/'examples/cancellation_safe.json'), '--fixture', 'cancellation-fixed')
            self.assertEqual(code, 0, error)
            report = check_fixture(scenario(), 'cancellation-conflict', max_schedules=2)
            self.assertEqual(report['status'], 'incomplete')


if __name__ == '__main__':
    unittest.main()
