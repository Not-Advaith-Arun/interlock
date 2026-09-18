"""Shared model/handler checking without CLI or filesystem side effects."""

from .engine import search
from .fixture import MAX_FIXTURE_SCHEDULES, check_fixture, replay_fixture, validate_fixture


def run_check(scenario, *, fixture=None, max_depth=8, max_states=50_000, max_schedules=None):
    if max_schedules is not None:
        if not fixture:
            raise ValueError('--max-schedules requires --fixture')
        if type(max_schedules) is not int or not 1 <= max_schedules <= MAX_FIXTURE_SCHEDULES:
            raise ValueError(f'--max-schedules must be between 1 and {MAX_FIXTURE_SCHEDULES}')
    if fixture:
        validate_fixture(scenario, fixture)
    report = search(scenario, max_depth, max_states)
    if not fixture:
        return report
    report['model_status'] = report['status']
    if report['status'] == 'incomplete':
        report['fixture'] = {'fixture': fixture, 'status': 'not_run',
                             'reason': 'Model search exceeded its state budget.'}
        return report
    checked = report['fixture'] = check_fixture(scenario, fixture, max_depth=max_depth,
                                                max_schedules=max_schedules or MAX_FIXTURE_SCHEDULES)
    if checked['status'] != 'agreement':
        report['status'] = checked['status']
    elif report['candidate']:
        actual = checked['candidate_replay'] = replay_fixture(scenario, report['candidate']['events'], fixture)
        if not actual['agreement']:
            report['status'] = checked['status'] = 'fixture_mismatch'
            checked['first_mismatch'] = actual
            checked['coverage'].update(complete_up_to_depth=False, termination_reason='fixture_mismatch')
    return report
