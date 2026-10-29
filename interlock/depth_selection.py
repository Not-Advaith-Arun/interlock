"""Extract complete per-case retained depth slices; never run or repair cells."""
from .depth_comparison import _grid


def select_depth_cases(report, selected_ids):
    grid = _grid(report)  # Validate even omitted cases and summary before extracting.
    known = {key for key, depth in grid}
    if (not isinstance(selected_ids, list) or not 1 <= len(selected_ids) <= 8
            or any(not isinstance(key, str) or key not in known for key in selected_ids)
            or len(set(selected_ids)) != len(selected_ids)):
        raise ValueError('select distinct existing recorded case IDs')
    rows = [{'depth': depth, 'id': key, **grid[(key, depth)]}
            for depth in sorted(report['depths']) for key in selected_ids]
    incomplete = any(row['verdict'] == 'incomplete' for row in rows)
    unexpected = any(row['verdict'] == 'unexpected' for row in rows)
    result = {'format': 'interlock-case-depths-v1', 'status': 'incomplete' if incomplete else 'unexpected' if unexpected else 'passed',
              'any_incomplete': incomplete, 'any_unexpected': unexpected, 'manifest_cases': report['manifest_cases'],
              'selected_cases': len(selected_ids), 'omitted_cases': report['manifest_cases'] - len(selected_ids),
              'depths': sorted(report['depths']), 'results': rows, 'execution_scope': 'model_only', 'source_verification': 'not_checked',
              'scope': 'Explicit retained case subset from a completely structurally validated recorded matrix. Every requested recorded depth, original scenario identity, expectation, coverage and bound is kept; omitted cases count against the original declaration total. A subset summary can differ from its input; it says nothing about omitted results. No new model search, handlers, replay, source verification or safety approval. Caller-recorded claims are unauthenticated; model_only labels the retained observations, not execution by this extraction. Expected unsafe outcomes are not safety, and every selected incomplete row remains incomplete.'}
    _grid(result)
    return result
