"""Shared model/handler checking without CLI or filesystem side effects."""

from .engine import search
from .fixture import MAX_FIXTURE_SCHEDULES, check_fixture, replay_fixture, validate_fixture
from .retry_envelope_fixture import BRANCH_FAILURE_PROBE


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
    # An exhaustive prefix check can exceed its budget after a concrete branch
    # failure was found. Preserve separately labelled, directly executed evidence
    # for base/branch failures without turning that evidence into completeness.
    failure_replays = {}
    for version in ('base', 'left', 'right'):
        failure = report['versions'][version]['first_failure']
        if failure is not None:
            failure_replays[version] = replay_fixture(scenario, failure['events'], fixture)
    diagnostics = {'failure_replays': failure_replays,
                   'failure_replay_scope': 'Diagnostic schedules only; excluded from exhaustive prefix coverage counts.'}
    direct_results = list(failure_replays.values())
    if scenario['model'] == 'multi-job-retry-envelope-v2':
        result = replay_fixture(scenario, BRANCH_FAILURE_PROBE, fixture)
        direct_results.append(result)
        diagnostics['envelope_probe'] = {
            'name': 'serialized_early_retry', 'result': result,
            'within_search_depth': len(BRANCH_FAILURE_PROBE) <= max_depth,
            'scope': 'Frozen direct replay, independent of model/prefix exploration budgets. '
                     'May exceed requested search depth; never counted as exhaustive coverage.'}
        diagnostics['known_unsafe_versions'] = [
            version for version, outcome in result['observed_outcomes'].items()
            if result['agreement'] and not outcome['passed']]
        diagnostics['branch_safety_caveat'] = (
            'A frozen direct replay demonstrates independent right-branch failure. '
            'A shallow model candidate does not establish merge-only failure for this envelope.'
            if any(v in diagnostics['known_unsafe_versions'] for v in ('base', 'left', 'right')) else
            'The frozen direct replay is safe; only the reported model/prefix bounds were explored.')
    mismatch = next((result for result in direct_results if not result['agreement']), None)
    if mismatch is not None:
        report['status'] = 'fixture_mismatch'
        report['fixture'] = {'fixture': fixture, 'status': 'fixture_mismatch',
                             'first_mismatch': mismatch, **diagnostics,
                             'reason': 'Direct base/branch failure replay disagrees with the model; prefix search not run.'}
        return report
    if report['status'] == 'incomplete':
        report['fixture'] = {'fixture': fixture, 'status': 'not_run',
                             'reason': 'Exhaustive prefix search not run: model search exceeded its state budget; diagnostic replays are separate.',
                             **diagnostics}
        return report
    checked = report['fixture'] = check_fixture(scenario, fixture, max_depth=max_depth,
                                                max_schedules=max_schedules or MAX_FIXTURE_SCHEDULES)
    checked.update(diagnostics)
    if checked['status'] != 'agreement':
        report['status'] = checked['status']
    elif report['candidate']:
        actual = checked['candidate_replay'] = replay_fixture(scenario, report['candidate']['events'], fixture)
        if not actual['agreement']:
            report['status'] = checked['status'] = 'fixture_mismatch'
            checked['first_mismatch'] = actual
            checked['coverage'].update(complete_up_to_depth=False, termination_reason='fixture_mismatch')
    if report['status'] not in ('incomplete', 'fixture_mismatch'):
        unsafe = diagnostics.get('known_unsafe_versions', [])
        if 'base' in unsafe:
            report['status'] = 'baseline_failure'
        elif any(version in unsafe for version in ('left', 'right')):
            report['status'] = 'branch_failure'
        if any(version in unsafe for version in ('base', 'left', 'right')):
            report['classification_scope'] = 'Bounded model/prefix checks plus the separately labelled frozen direct replay.'
    return report
