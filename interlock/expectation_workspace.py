"""Human expectation declarations on a complete captured manifest, never learned outcomes."""
from copy import deepcopy
from pathlib import Path
from .model_cases import validated_cases, EXPECTED
from .scenario import fingerprint
from .report_cards import render_report


def expectation_template(manifest):
    cases = validated_cases(manifest)
    return {'draft': {'format': 'interlock-expectation-edit/v1', 'manifest_sha256': fingerprint(manifest), 'expectations': []},
            'allowed_classifications': sorted(EXPECTED),
            'cases': [{'id': r['id'], 'expected_status': r['expected_status'], 'scenario_sha256': fingerprint(r['scenario'])} for r in cases],
            'scope': 'Explicit caller-authored expectation edits only, never outcomes learned by search. Metadata IDs and scenario fingerprints only; complete original declarations must match the native guard, including omitted cases. Choose each included case and classification deliberately; incomplete is never a passing expectation. Download a guarded edit draft, then revise-case-expectations to export a new private full-scenario manifest without overwriting the original. Review it before separate bounded check-cases. No search, handlers, source verification, witness, safety approval or automatic expectation update.'}


def revise_expectations(manifest, draft):
    cases = validated_cases(manifest)
    if (not isinstance(draft, dict) or set(draft) != {'format', 'manifest_sha256', 'expectations'}
            or draft['format'] != 'interlock-expectation-edit/v1' or draft['manifest_sha256'] != fingerprint(manifest)):
        raise ValueError('expectation edit belongs to a different or changed complete manifest')
    rows = draft['expectations']; known = {r['id'] for r in cases}
    if not isinstance(rows, list) or not 1 <= len(rows) <= 8: raise ValueError('supply1..8 explicit expectation edits')
    edits = {}
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {'id', 'expected_status'}
                or not isinstance(row['id'], str) or row['id'] not in known or row['id'] in edits
                or not isinstance(row['expected_status'], str) or row['expected_status'] not in EXPECTED):
            raise ValueError('choose distinct existing cases and supported complete classifications')
        edits[row['id']] = row['expected_status']
    result = deepcopy(manifest)
    for row in result['cases']:
        if row['id'] in edits: row['expected_status'] = edits[row['id']]
    validated_cases(result)
    return result


def render_expectation_template(report):
    rows = [{'group': 'Current caller declaration', 'cells': [r['id'], r['expected_status'], r['scenario_sha256']]} for r in report['cases']]
    return render_report('Interlock explicit expectation workspace', report['scope'],
                         ['Case ID', 'Current declared classification', 'Scenario identity'], rows, payload=report,
                         summary='Declare expectations deliberately before execution. No observed outcomes, source verification or safety approval.',
                         extra_script=Path(__file__).with_name('ui').joinpath('expectation_drafts.js').read_text())
