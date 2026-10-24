"""Static four-version replay review; HTML never executes witness data."""

from html import escape
import json
from pathlib import Path


def render_witness(name, result, *, max_frames=100):
    if type(max_frames) is not int or not 1 <= max_frames <= 1000:
        raise ValueError("max frames must be an integer between 1 and 1000")
    trace = result["trace"]
    selected = trace if len(trace) <= max_frames else ([trace[0]] + trace[-(max_frames - 1):] if max_frames > 1 else trace[-1:])
    frames = []
    for frame in selected:
        outcomes = frame.get("outcomes") or frame["observed"]
        versions = []
        for version in ("base", "left", "right", "merged"):
            outcome = outcomes[version]
            payload = json.dumps(outcome, indent=2, ensure_ascii=True)
            truncated = len(payload) > 6000
            state = "PASS" if outcome["passed"] else "FAIL"
            versions.append(f'<section><h3 class="{state.lower()}">{version}: {state}</h3><pre>{escape(payload[:6000])}</pre>'
                            + ('<p>JSON display truncated.</p>' if truncated else '') + '</section>')
        label = f"{frame['step']}: {frame['event'] or 'Initial state'}"
        frames.append('<details open class="frame"><summary>' + escape(label) + '</summary><div class="versions">' + ''.join(versions) + '</div></details>')
    scope = result.get("execution_scope", "bundled_handlers")
    source = result.get("source_verification", "not_checked")
    interaction = "reproduced" if result["interaction_reproduced"] else "not reproduced"
    document = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Interlock witness review</title><style>
''' + Path(__file__).with_name('ui').joinpath('witness.css').read_text(encoding='utf-8') + '''
</style></head><body><main><div class="topline"><span>Interlock / Witness</span><button id="theme" type="button" aria-pressed="false">Dark theme</button></div><h1>Interlock witness review</h1><h2>''' + escape(name) + '</h2><p>Interaction on this sequence: <strong>' + interaction + '</strong>.</p><p>Execution: ' + escape(scope) + '; source identity: ' + escape(source) + '.</p><p class="limits">This review covers one event sequence, not complete branch safety or globally shortest failure. ' + escape(result["scope"]) + '</p><p>Showing ' + str(len(selected)) + ' of ' + str(len(trace)) + ' recorded states. Initial and recent states are kept when possible; omitted states are not shown.</p>' + '<div class="playback" hidden><button id="previous" type="button">Previous state</button><output id="position" aria-live="polite"></output><button id="next" type="button">Next state</button><button id="all" type="button" aria-pressed="false">Show all states</button></div>' + ''.join(frames) + '<script>' + Path(__file__).with_name('ui').joinpath('witness.js').read_text(encoding='utf-8') + '</script></main></body></html>'
    if len(document.encode("utf-8")) > 32 * 1024 * 1024:
        raise ValueError("rendered witness view exceeds 32 MiB; lower --max-frames")
    return document
