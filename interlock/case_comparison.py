"""Compare recorded caller-case classifications; never replay or certify inputs."""
import re
from .model_cases import EXPECTED


def _index(report):
    if not isinstance(report,dict) or report.get('format') != 'interlock-model-cases-report-v1':
        raise ValueError('expected complete model-cases report format')
    cases = report.get('cases')
    if not isinstance(cases,list) or not 1 <= len(cases) <= 8:
        raise ValueError('report must contain1..8 recorded cases')
    indexed = {}
    for row in cases:
        if (not isinstance(row,dict) or not isinstance(row.get('id'),str)
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}',row['id'])
                or row['id'] in indexed or not isinstance(row.get('scenario_sha256'),str)
                or not re.fullmatch(r'[0-9a-f]{64}',row['scenario_sha256'])
                or not isinstance(row.get('expected_status'),str) or row['expected_status'] not in EXPECTED
                or not isinstance(row.get('report'),dict)):
            raise ValueError('invalid recorded model case identity or expectation')
        observed = row['report'].get('status')
        if not isinstance(observed,str) or observed not in EXPECTED | {'incomplete'}:
            raise ValueError('unsupported recorded model classification')
        verdict = 'incomplete' if observed == 'incomplete' else 'passed' if observed == row['expected_status'] else 'unexpected'
        if row.get('verdict') != verdict:
            raise ValueError('recorded model verdict contradicts its expected/observed statuses')
        indexed[row['id']] = {'scenario_sha256':row['scenario_sha256'],'expected_status':row['expected_status'],
                              'observed_status':observed,'verdict':verdict}
    return indexed


def compare_case_results(before, after):
    left,right = _index(before),_index(after)
    rows = []
    for key in sorted(set(left)|set(right)):
        a,b = left.get(key),right.get(key)
        changes = ['added'] if a is None else ['removed'] if b is None else [field for field in ('scenario_sha256','expected_status','observed_status','verdict') if a[field] != b[field]]
        rows.append({'id':key,'before':a,'after':b,'changes':changes,'changed':bool(changes)})
    return {'format':'interlock-case-result-comparison-v1','cases':rows,
            'changed_cases':sum(row['changed'] for row in rows),'unchanged_cases':sum(not row['changed'] for row in rows),
            'execution_scope':'none','source_verification':'not_checked',
            'scope':'Recorded classification metadata comparison only, not fresh search/replay, authenticated reports or safety verification. Scenario hashes and case IDs are caller claims. Changed scenario identities or expectations must be reviewed separately from changed observations. Search bounds/coverage and detailed evidence are not compared; unchanged classifications do not imply equivalent behavior or equal coverage.'}
