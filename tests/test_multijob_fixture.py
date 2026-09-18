from collections import deque
from dataclasses import replace
import difflib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from interlock.engine import search
from interlock.fixture import FIXTURES, check_fixture, fixture_scenario, replay_fixture, source_identity
from interlock.multijob import MultiJobModel
from interlock.multijob_fixture import MultiJobRuntime
from tests import test_workflow

ROOT = Path(__file__).resolve().parents[1]
FAILURE = ['submit:a', 'submit:b', 'deliver:b', 'acknowledge:b']


class MultiJobFixtureTests(unittest.TestCase):
    invoke = test_workflow.WorkflowTests.invoke

    def test_real_effects_and_completion_causality_reproduce_the_failure(self):
        data = fixture_scenario('multi-job-conflict')
        result = replay_fixture(data, search(data)['candidate']['events'], 'multi-job-conflict')
        self.assertTrue(result['agreement'])
        self.assertTrue(result['interaction_reproduced'])
        merged = result['observed_outcomes']['merged']
        self.assertEqual(merged['state']['completed'], ['a'])
        self.assertEqual(merged['effect_records'], [{'job_id': 'b', 'payload': 'Notify account B', 'request_id': 'request:b'}])
        self.assertEqual(merged['state']['completion_causes'], [{'job_id': 'a', 'acknowledgement_id': 'ack:b'}])
        ack = next(m for m in merged['message_records'] if m['message_id'] == 'ack:b')
        self.assertEqual(ack, {'message_id': 'ack:b', 'parent_id': 'request:b', 'payload': {'job_id': None}})
        self.assertEqual(result['trace'][2]['stuttered'], ['base', 'right'])
        self.assertEqual(result['observed_outcomes']['left']['state']['completed'], ['b'])

    def test_independent_handlers_run_without_model_transitions(self):
        with patch.object(MultiJobModel, 'step', side_effect=AssertionError('model invoked')):
            runtime = MultiJobRuntime(FIXTURES['multi-job-conflict'].revisions['merged'])
            for event in FAILURE:
                self.assertTrue(runtime.dispatch(event))
            self.assertEqual(runtime.producer.completed, ['a'])
            self.assertEqual(runtime.snapshot()['violations'], ['acknowledgement_matches_completed_job',
                                                                'completion_requires_matching_effect'])
            runtime.dispatch('deliver:a')
            self.assertIn('completion_requires_matching_effect', runtime.snapshot()['violations'])

    def test_all_handler_generated_schedules_agree_without_state_merging(self):
        for name in ('multi-job-conflict', 'multi-job-fixed'):
            data = fixture_scenario(name)
            queue, checked, steps = deque([()]), 0, 0
            while queue:
                events = queue.popleft()
                runtimes = [MultiJobRuntime(revision) for revision in FIXTURES[name].revisions.values()]
                for event in events:
                    for runtime in runtimes:
                        runtime.dispatch(event)
                result = replay_fixture(data, events, name)
                self.assertTrue(result['agreement'], (events, result['first_mismatch']))
                checked += 1
                steps += len(events)
                enabled = sorted({event for runtime in runtimes for event in runtime.enabled()})
                queue.extend(events + (event,) for event in enabled)
            self.assertEqual((checked, steps), (98, 632))
            result = check_fixture(data, name, max_depth=12)
            self.assertEqual(result['status'], 'agreement')
            self.assertEqual(result['coverage']['termination_reason'], 'schedule_space_exhausted')
            self.assertEqual(result['coverage']['depth_reached'], 9)

    def test_guarded_control_preserves_reordered_ack_identity(self):
        data = fixture_scenario('multi-job-fixed')
        for events in (FAILURE, ['submit:a', 'submit:b', 'deliver:a', 'deliver:b', 'acknowledge:b']):
            result = replay_fixture(data, events, 'multi-job-fixed')
            self.assertTrue(result['agreement'])
            self.assertTrue(all(o['passed'] for o in result['observed_outcomes'].values()))
            self.assertEqual(result['observed_outcomes']['merged']['state']['completed'], ['b'])

    def test_wrong_parent_and_payload_are_detected_beyond_state_counts(self):
        fixture = FIXTURES['multi-job-conflict']
        for defect in ('parent', 'payload'):
            class BrokenWorker(fixture.revisions['merged'].worker):
                def receive(self, request):
                    super().receive(request)
                    if defect == 'parent':
                        self.transport.acknowledgements[-1] = replace(self.transport.acknowledgements[-1], parent_id='request:wrong')
                    else:
                        self.effects.records[-1] = replace(self.effects.records[-1], payload='wrong payload')
            revisions = dict(fixture.revisions)
            revisions['merged'] = replace(revisions['merged'], worker=BrokenWorker)
            with patch.dict(FIXTURES, {'multi-job-conflict': replace(fixture, revisions=revisions)}):
                result = check_fixture(fixture_scenario('multi-job-conflict'), 'multi-job-conflict')
            self.assertEqual(result['status'], 'fixture_mismatch')
            differences = result['first_mismatch']['first_mismatch']['differences']
            expected_field = 'ack_records' if defect == 'parent' else 'effect_records'
            self.assertTrue(any(d['field'] == expected_field for d in differences), differences)

    def test_broken_model_or_handler_exception_never_claims_agreement(self):
        with patch.object(MultiJobModel, 'violations', return_value=()):
            result = check_fixture(fixture_scenario('multi-job-conflict'), 'multi-job-conflict')
            self.assertEqual(result['status'], 'fixture_mismatch')
        fixture = FIXTURES['multi-job-conflict']
        with patch.object(fixture.revisions['merged'].worker, 'receive', side_effect=RuntimeError('broken handler')):
            result = check_fixture(fixture_scenario('multi-job-conflict'), 'multi-job-conflict')
        self.assertEqual(result['status'], 'fixture_mismatch')
        self.assertFalse(result['first_mismatch']['interaction_reproduced'])
        self.assertTrue(any(d['field'] == 'handler_exception' for d in result['first_mismatch']['first_mismatch']['differences']))

    def test_source_composition_and_fingerprints_include_new_dependencies(self):
        root = ROOT/'interlock/fixtures/multijob'
        for filename, branch, label in [('producer.py', 'left', 'left-pipeline-jobs'),
                                        ('worker.py', 'right', 'right-omit-ack-identity')]:
            base, changed = (root/'base'/filename).read_text(), (root/branch/filename).read_text()
            self.assertEqual((root/'merged'/filename).read_text(), changed)
            other = 'right' if branch == 'left' else 'left'
            self.assertEqual((root/other/filename).read_text(), base)
            self.assertNotEqual(base, changed)
            expected = ''.join(difflib.unified_diff(base.splitlines(True), changed.splitlines(True),
                                                   fromfile='a/'+filename, tofile='b/'+filename))
            self.assertEqual((ROOT/'examples/source-patches'/(label+'.patch')).read_text(), expected)
        identity = source_identity('multi-job-conflict')
        self.assertTrue({'multijob.py', 'multijob_fixture.py', 'fixtures/multijob/services.py'} <= identity['files'].keys())
        self.assertNotEqual(identity, source_identity('multi-job-fixed'))

    def test_cli_generation_pinned_roundtrip_and_control(self):
        with tempfile.TemporaryDirectory() as directory:
            source, witness = Path(directory)/'case.json', Path(directory)/'witness.json'
            self.assertEqual(self.invoke('example', 'multi-job-conflict', '--output', str(source))[0], 0)
            code, _, error = self.invoke('check', str(source), '--fixture', 'multi-job-conflict',
                                         '--max-depth', '12', '--witness', str(witness))
            self.assertEqual(code, 1, error)
            self.assertEqual(json.loads(witness.read_text())['fixture']['name'], 'multi-job-conflict')
            code, output, error = self.invoke('replay', str(witness), '--fixture', 'multi-job-conflict')
            self.assertEqual(code, 1, error)
            self.assertIn('ack:b → completed a', output)
            self.assertIn('source identity: verified', output)
            self.assertEqual(self.invoke('example', 'multi-job-fixed', '--output', str(source), '--force')[0], 0)
            code, _, error = self.invoke('check', str(source), '--fixture', 'multi-job-fixed', '--max-depth', '12')
            self.assertEqual(code, 0, error)

    def test_shallow_and_budgeted_fixture_results_remain_honest(self):
        data = fixture_scenario('multi-job-conflict')
        shallow = check_fixture(data, 'multi-job-conflict', max_depth=3)
        self.assertEqual(shallow['status'], 'agreement')
        self.assertEqual(shallow['coverage']['termination_reason'], 'depth_bound')
        capped = check_fixture(data, 'multi-job-conflict', max_depth=12, max_schedules=10)
        self.assertEqual(capped['status'], 'incomplete')
        self.assertFalse(capped['coverage']['complete_up_to_depth'])
        self.assertEqual(capped['coverage']['termination_reason'], 'schedule_budget')
        with self.assertRaises(ValueError):
            check_fixture(data, 'multi-job-fixed')


if __name__ == '__main__':
    unittest.main()
