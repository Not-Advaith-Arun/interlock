import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from interlock.fixture import FIXTURES, fixture_scenario
from interlock.runner import run_check
from interlock.suite import EXPECTED_WITNESSES, run_suite
from tests import test_workflow


class SuiteTests(unittest.TestCase):
    invoke = test_workflow.WorkflowTests.invoke

    def test_all_bundled_expectations_and_complete_coverage(self):
        self.assertEqual(set(EXPECTED_WITNESSES), set(FIXTURES))
        result = run_suite()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['summary'], {'cases': 6, 'passed': 6, 'failed': 0, 'incomplete': 0,
                                             'fixture_mismatch': 0, 'schedules_checked': 290,
                                             'event_steps_executed': 1676})
        for case in result['cases']:
            report = case['report']
            self.assertEqual(report['status'], case['expected_status'])
            self.assertEqual(report['fixture']['coverage']['termination_reason'], 'schedule_space_exhausted')
            if case['expected_events']:
                self.assertEqual(report['candidate']['events'], case['expected_events'])
                self.assertTrue(report['fixture']['candidate_replay']['interaction_reproduced'])
            self.assertGreaterEqual(case['elapsed_seconds'], 0)

    def test_depth_state_and_schedule_bounds_are_incomplete_not_regressions(self):
        for limits in ({'max_depth': 8}, {'max_states': 1}, {'max_schedules': 2}):
            result = run_suite(['multi-job-conflict'], **limits)
            self.assertEqual(result['status'], 'incomplete', limits)
            self.assertEqual(result['summary']['passed'], 0)
            self.assertEqual(result['summary']['failed'], 0)
            self.assertTrue(result['cases'][0]['reason'])

    def test_passing_control_regression_and_missing_known_failure_fail_suite(self):
        for name, observed in [('retry-fixed', 'retry-conflict'), ('retry-conflict', 'retry-fixed')]:
            report = run_check(fixture_scenario(observed), fixture=observed, max_depth=12)
            with patch('interlock.suite.run_check', return_value=report):
                result = run_suite([name])
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['summary']['failed'], 1)

    def test_unexpected_witness_or_independent_branch_failure_fails(self):
        report = run_check(fixture_scenario('retry-conflict'), fixture='retry-conflict', max_depth=12)
        different = copy.deepcopy(report)
        different['candidate']['events'] = ['submit', 'timeout', 'deliver', 'deliver']
        with patch('interlock.suite.run_check', return_value=different):
            self.assertEqual(run_suite(['retry-conflict'])['status'], 'failed')
        report['status'] = 'branch_failure'
        with patch('interlock.suite.run_check', return_value=report):
            result = run_suite(['retry-conflict'])
        self.assertEqual(result['status'], 'failed')
        self.assertIn('branch', result['cases'][0]['reason'])

    def test_mismatch_retains_diagnostics_and_has_priority_over_incomplete(self):
        original = run_check
        def checker(scenario, **kwargs):
            report = original(scenario, **kwargs)
            if kwargs['fixture'] == 'cancellation-conflict':
                report['status'] = 'fixture_mismatch'
                report['fixture']['status'] = 'fixture_mismatch'
                report['fixture']['first_mismatch'] = {'difference': 'injected'}
            return report
        with patch('interlock.suite.run_check', side_effect=checker):
            result = run_suite(['cancellation-conflict', 'multi-job-conflict'], max_depth=8)
        self.assertEqual(result['status'], 'fixture_mismatch')
        self.assertEqual(result['summary']['incomplete'], 1)
        self.assertEqual(result['cases'][0]['report']['fixture']['first_mismatch'], {'difference': 'injected'})

    def test_invalid_inputs_are_rejected_before_any_handler_work(self):
        selections = [[], 'retry-conflict', ['unknown'], ['retry-fixed', 'retry-fixed'], [None], [[]]]
        with patch('interlock.suite.run_check', side_effect=AssertionError('unexpected execution')):
            for names in selections:
                with self.assertRaises(ValueError):
                    run_suite(names)
            for limits in ({'max_depth': True}, {'max_depth': 65}, {'max_states': 0},
                           {'max_states': True}, {'max_schedules': 10001}, {'max_schedules': False}):
                with self.assertRaises(ValueError):
                    run_suite(**limits)

    def test_returned_expectations_cannot_mutate_suite_oracle(self):
        result = run_suite(['cancellation-conflict'])
        result['cases'][0]['expected_events'].append('wrong')
        self.assertEqual(EXPECTED_WITNESSES['cancellation-conflict'], ['start', 'cancel', 'fire_callback'])

    def test_cli_success_reports_expected_failures_as_success_and_preserves_files(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'suite.json'
            code, output, error = self.invoke('suite', '--fixture', 'multi-job-conflict', '--fixture', 'multi-job-fixed',
                                             '--report', str(path), '--json')
            self.assertEqual(code, 0, error)
            result = json.loads(output)
            self.assertEqual(result['summary']['passed'], 2)
            self.assertEqual(json.loads(path.read_text()), result)
            before = path.read_bytes()
            with patch('interlock.cli.run_suite', side_effect=AssertionError('preflight required')):
                code, _, error = self.invoke('suite', '--report', str(path))
            self.assertEqual(code, 2)
            self.assertEqual(path.read_bytes(), before)
            code, _, error = self.invoke('suite', '--fixture', 'cancellation-fixed', '--report', str(path), '--force')
            self.assertEqual(code, 0, error)

    def test_cli_exit_codes_distinguish_budget_mismatch_and_expectation_failure(self):
        code, output, error = self.invoke('suite', '--fixture', 'multi-job-conflict', '--max-depth', '8', '--json')
        self.assertEqual(code, 3, error)
        self.assertEqual(json.loads(output)['status'], 'incomplete')
        for status, expected_code in [('failed', 1), ('fixture_mismatch', 4)]:
            with patch('interlock.cli.run_suite', return_value={'status': status}):
                code, _, error = self.invoke('suite', '--json')
            self.assertEqual(code, expected_code, error)
        code, _, error = self.invoke('suite', '--fixture', 'retry-fixed', '--fixture', 'retry-fixed')
        self.assertEqual(code, 2)
        self.assertIn('unique', error)


if __name__ == '__main__':
    unittest.main()
