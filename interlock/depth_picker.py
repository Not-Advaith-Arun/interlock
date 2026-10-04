"""Explicit complete recorded case slices; no model or handler activity."""
from pathlib import Path
from .depth_comparison import _grid
from .depth_selection import select_depth_cases
from .report_cards import render_report


def depth_choices(report):
    grid = _grid(report)
    ids = sorted({key for key, depth in grid})
    captured = select_depth_cases(report, ids)
    return {'format': 'interlock-recorded-depth-picker/v1', 'report': captured, 'case_ids': ids,
            'scope': 'Complete retained matrix validated before any choices, including every later omitted case/depth cell. Choose cases explicitly; each export retains every recorded depth, exact scenario/expectation/bounds/coverage and original declaration omissions. Display filters never choose cases. Canonical case-ID order within each depth, not original execution timing. A subset summary concerns selected cells only; omitted results remain unknown to its reader. No search, replay, handlers, source verification, witness publication or safety approval. Inputs and exported cells remain unauthenticated caller claims; metadata consistency is not a fresh result.'}


def render_depth_choices(report):
    rows = [{'group': row['verdict'], 'cells': [row['id'], row['depth'], row['observed_status'], row['verdict'], row['coverage']['complete_up_to_depth']]}
            for row in report['report']['results']]
    return render_report('Interlock choose retained depth cases', report['scope'],
                         ['Recorded case ID', 'Depth', 'Recorded classification', 'Declared verdict', 'Recorded completion'], rows, payload=report,
                         summary=f"{len(report['case_ids'])} complete recorded case slices available. No automatic choices or execution; incomplete rows stay incomplete.",
                         extra_script=Path(__file__).with_name('ui').joinpath('depth_picker.js').read_text())
