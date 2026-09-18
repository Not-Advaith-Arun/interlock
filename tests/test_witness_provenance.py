import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from interlock.engine import make_witness, replay_witness, search
from interlock.fixture import check_fixture, replay_fixture, source_identity
from tests import test_fixture
from tests.test_fixture import ROOT, scenario


class WitnessProvenanceTests(unittest.TestCase):
    invoke = test_fixture.FixtureCliTests.invoke

    def setUp(self):
        self.data = scenario()
        report = search(self.data)
        report['fixture'] = check_fixture(self.data, 'retry-conflict')
        report['fixture']['candidate_replay'] = replay_fixture(
            self.data, report['candidate']['events'], 'retry-conflict')
        self.report = report
        self.witness = make_witness(self.data, report)

    def write(self, directory, witness=None):
        path = Path(directory) / 'witness.json'
        path.write_text(json.dumps(self.witness if witness is None else witness))
        return str(path)

    def test_new_fixture_witness_pins_source_and_roundtrips(self):
        self.assertEqual(self.witness['format'], 'interlock-witness-v2')
        self.assertEqual(self.witness['fixture']['source_identity'], source_identity('retry-conflict'))
        self.assertTrue(replay_witness(self.witness)['interaction_reproduced'])
        with tempfile.TemporaryDirectory() as directory:
            code, output, error = self.invoke('replay', self.write(directory), '--fixture', 'retry-conflict', '--json')
        self.assertEqual(code, 1, error)
        self.assertEqual(json.loads(output)['source_verification'], 'verified')

    def test_check_command_emits_pinned_witness(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'witness.json')
            code, _, error = self.invoke('check', str(ROOT / 'examples/retry_conflict.json'),
                                         '--fixture', 'retry-conflict', '--witness', path)
            self.assertEqual(code, 1, error)
            self.assertEqual(json.loads(Path(path).read_text()), self.witness)

    def test_changed_installed_source_rejected_before_handler_construction(self):
        changed = copy.deepcopy(source_identity('retry-conflict'))
        changed['files']['fixtures/retry/merged/worker.py'] = '0' * 64
        with tempfile.TemporaryDirectory() as directory, \
                patch('interlock.fixture.source_identity', return_value=changed), \
                patch('interlock.fixture.FixtureRuntime', side_effect=AssertionError('must not execute')):
            code, _, error = self.invoke('replay', self.write(directory), '--fixture', 'retry-conflict')
        self.assertEqual(code, 2)
        self.assertIn('source identity does not match', error)

    def test_tampering_with_events_sources_or_fixture_name_rejected(self):
        changes = [lambda w: w['events'].pop(),
                   lambda w: w['fixture'].update(name='retry-fixed'),
                   lambda w: w['fixture']['source_identity']['files'].update({'engine.py': '0' * 64})]
        for change in changes:
            witness = copy.deepcopy(self.witness)
            change(witness)
            with self.assertRaisesRegex(ValueError, 'witness fingerprint'):
                replay_witness(witness)

    def test_requires_explicit_execution_choice_for_pinned_witness(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory)
            code, _, error = self.invoke('replay', path)
            self.assertEqual(code, 2)
            self.assertIn('--model-only', error)
            with patch('interlock.fixture.source_identity', side_effect=AssertionError('model only')):
                code, output, error = self.invoke('replay', path, '--model-only', '--json')
            self.assertEqual(code, 1, error)
            result = json.loads(output)
            self.assertEqual(result['source_verification'], 'not_checked')
            self.assertEqual(result['execution_scope'], 'model_only')

    def test_legacy_model_witness_still_replays_and_reports_unpinned_fixture(self):
        legacy = make_witness(self.data, search(self.data))
        self.assertEqual(legacy['format'], 'interlock-witness-v1')
        with tempfile.TemporaryDirectory() as directory:
            path = self.write(directory, legacy)
            self.assertEqual(self.invoke('replay', path)[0], 1)
            code, output, error = self.invoke('replay', path, '--fixture', 'retry-conflict', '--json')
            self.assertEqual(code, 1, error)
            self.assertEqual(json.loads(output)['source_verification'], 'unpinned')

    def test_incomplete_or_mismatching_fixture_cannot_make_pinned_witness(self):
        for status in ('incomplete', 'fixture_mismatch', 'not_run'):
            report = copy.deepcopy(self.report)
            report['fixture']['status'] = status
            with self.assertRaisesRegex(ValueError, 'complete check'):
                make_witness(self.data, report)
        report = copy.deepcopy(self.report)
        report['fixture']['candidate_replay']['source_identity'] = {}
        with self.assertRaisesRegex(ValueError, 'complete check'):
            make_witness(self.data, report)

    def test_malformed_v2_has_controlled_input_error(self):
        for field in (None, [], {}, {'name': [], 'source_identity': {}}):
            witness = dict(self.witness, fixture=field)
            with tempfile.TemporaryDirectory() as directory:
                code, _, error = self.invoke('replay', self.write(directory, witness), '--model-only')
            self.assertEqual(code, 2)
            self.assertNotIn('Traceback', error)


if __name__ == '__main__':
    unittest.main()
