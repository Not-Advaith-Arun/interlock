"""Bind every recorded depth to supplied case declarations without execution."""
from .depth_comparison import _grid
from .model_cases import validated_cases
from .scenario import fingerprint
from .report_cards import render_report


def inspect_depth_binding(manifest, report, selected_ids=None):
    declared = validated_cases(manifest, selected_ids)
    grid = _grid(report)
    expected = {r['id']: {'scenario_sha256': fingerprint(r['scenario']), 'expected_status': r['expected_status']} for r in declared}
    rows = []
    for depth in sorted(report['depths']):
        recorded = {key: value for (key, d), value in grid.items() if d == depth}
        for key in sorted(set(expected) | set(recorded)):
            a, b = expected.get(key), recorded.get(key)
            differences = ['unexpected_record'] if a is None else ['missing_record'] if b is None else [field for field in a if a[field] != b[field]]
            rows.append({'id': key, 'depth': depth, 'differences': differences, 'matches_declaration': not differences,
                         'declared': a, 'recorded': b})
    total_matches = len(manifest['cases']) == report['manifest_cases']
    return {'format': 'interlock-depth-binding/v1', 'matches_declarations': total_matches and all(r['matches_declaration'] for r in rows),
            'original_case_total_matches': total_matches, 'manifest_cases': len(manifest['cases']), 'recorded_manifest_cases': report['manifest_cases'],
            'selected_declarations': len(declared), 'recorded_selected_cases': report['selected_cases'], 'recorded_omitted_cases': report['omitted_cases'],
            'recorded_status': report['status'], 'recorded_any_incomplete': report['any_incomplete'], 'cells': rows,
            'execution_scope': 'none', 'source_verification': 'not_checked',
            'scope': 'Every declaration and complete retained depth matrix validates before checking original case totals and each selected case identity/expectation at every recorded depth. Missing and extra cases remain explicit at each depth; --case selects declarations, not observations. Matching hashes/expectations and original totals do not authenticate a shared origin, execution, freshness or source pins. Original recorded coverage/bounds/classifications remain unauthenticated claims; incomplete never becomes pass, and expected unsafe observations are not safety. Exit0 means declaration binding matches only. No search, replay, handlers, source verification or declaration edits.'}


def render_depth_binding(report):
    rows = [{'group': 'Declaration matches' if r['matches_declaration'] else 'Declaration mismatch', 'cells': [r['id'], r['depth'], ', '.join(r['differences']) or 'Identity and expectation match', r['recorded']['observed_status'] if r['recorded'] else 'Missing observation']} for r in report['cells']]
    return render_report('Interlock retained depth declaration binding', report['scope'], ['Case ID', 'Recorded depth', 'Binding check', 'Recorded classification'], rows, payload=report,
                         summary=f"Declaration binding matches: {report['matches_declarations']}. Recorded grid status remains {report['recorded_status']}; original declared totals match: {report['original_case_total_matches']}. No fresh execution or safety assessment.")
