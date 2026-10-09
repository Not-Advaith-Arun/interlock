"""Executable expectations for the finite bundled cases, not an empirical study."""

from collections import Counter
from time import perf_counter

from .fixture import MAX_FIXTURE_SCHEDULES, fixture_scenario
from .runner import run_check

# Expectations are specified separately from model search and handler execution.
EXPECTED_WITNESSES = {
    'retry-conflict': ['submit', 'deliver', 'timeout', 'deliver'],
    'retry-fixed': None,
    'cancellation-conflict': ['start', 'cancel', 'fire_callback'],
    'cancellation-fixed': None,
    'multi-job-conflict': ['submit:a', 'submit:b', 'deliver:b', 'acknowledge:b'],
    'multi-job-fixed': None,
    'multi-job-retry-conflict': ['submit:a', 'deliver:a:0', 'drop_ack:a:0', 'submit:b',
                               'deliver:b:0', 'timeout:a:0', 'deliver:a:1'],
    'multi-job-retry-fixed': None,
}
EXIT_CODES = {'passed': 0, 'failed': 1, 'incomplete': 3, 'fixture_mismatch': 4}


def _verdict(report, expected_status, expected_events):
    if report['status'] == 'fixture_mismatch':
        return 'fixture_mismatch', 'Model and handlers disagree.'
    if report['status'] == 'incomplete':
        return 'incomplete', 'Exploration budget exhausted.'
    if report['status'] in ('baseline_failure', 'branch_failure'):
        return 'failed', 'An independently safe baseline or branch regressed.'
    if expected_events is None and report['candidate'] is not None:
        return 'failed', 'A passing control produced an interaction candidate.'
    if (report['coverage']['termination_reason'] != 'state_space_exhausted'
            or report['fixture']['coverage']['termination_reason'] != 'schedule_space_exhausted'):
        return 'incomplete', 'The depth bound does not exhaust this finite fixture.'
    if report['status'] != expected_status:
        return 'failed', 'Observed classification differs from the specified expectation.'
    observed_events = report['candidate']['events'] if report['candidate'] else None
    if observed_events != expected_events:
        return 'failed', 'The shortest witness differs from the specified event sequence.'
    if expected_events is not None and not report['fixture']['candidate_replay']['interaction_reproduced']:
        return 'failed', 'The specified interaction did not reproduce in actual handlers.'
    return 'passed', 'Expected behavior reproduced with complete finite fixture coverage.'


def run_suite(fixtures=None, *, max_depth=12, max_states=50_000, max_schedules=MAX_FIXTURE_SCHEDULES):
    if fixtures is None:
        fixtures = sorted(EXPECTED_WITNESSES)
    if (not isinstance(fixtures, (list, tuple)) or not fixtures
            or any(not isinstance(name, str) or name not in EXPECTED_WITNESSES for name in fixtures)):
        raise ValueError('suite fixtures must be a nonempty list of bundled fixture names')
    if len(set(fixtures)) != len(fixtures):
        raise ValueError('suite fixture names must be unique')
    if type(max_depth) is not int or not 0 <= max_depth <= 64:
        raise ValueError('max_depth must be an integer between 0 and 64')
    if type(max_states) is not int or not 1 <= max_states <= 1_000_000:
        raise ValueError('max_states must be an integer between 1 and 1000000')
    if type(max_schedules) is not int or not 1 <= max_schedules <= MAX_FIXTURE_SCHEDULES:
        raise ValueError(f'max_schedules must be between 1 and {MAX_FIXTURE_SCHEDULES}')
    started = perf_counter()
    cases = []
    for name in fixtures:
        case_started = perf_counter()
        expected_events = EXPECTED_WITNESSES[name]
        expected_events = list(expected_events) if expected_events is not None else None
        expected_status = 'no_interaction_within_bound' if expected_events is None else 'merge_interaction_found'
        report = run_check(fixture_scenario(name), fixture=name, max_depth=max_depth,
                           max_states=max_states, max_schedules=max_schedules)
        verdict, reason = _verdict(report, expected_status, expected_events)
        cases.append({'fixture': name, 'verdict': verdict, 'reason': reason,
                      'expected_status': expected_status, 'expected_events': expected_events,
                      'elapsed_seconds': round(perf_counter() - case_started, 6), 'report': report})
    counts = Counter(case['verdict'] for case in cases)
    status = next((status for status in ('fixture_mismatch', 'failed', 'incomplete') if counts[status]), 'passed')
    return {'format': 'interlock-suite-v1', 'status': status,
            'bounds': {'max_depth': max_depth, 'max_states': max_states, 'max_schedules': max_schedules},
            'summary': {'cases': len(cases), **{status: counts[status] for status in EXIT_CODES},
                        'schedules_checked': sum(case['report']['fixture'].get('coverage', {}).get('schedules_checked', 0) for case in cases),
                        'event_steps_executed': sum(case['report']['fixture'].get('coverage', {}).get('event_steps_executed', 0) for case in cases)},
            'elapsed_seconds': round(perf_counter() - started, 6), 'cases': cases,
            'scope': 'Regression checks for bundled synthetic/reconstructed protocols only. '
                     'Pass requires expected failures/controls and full finite schedule coverage; not historical-case evaluation or arbitrary-source analysis.'}
