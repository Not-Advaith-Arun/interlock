"""Static four-version replay review; HTML never executes witness data."""

from html import escape
import json


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
        frames.append('<details open><summary>' + escape(label) + '</summary><div class="versions">' + ''.join(versions) + '</div></details>')
    scope = result.get("execution_scope", "bundled_handlers")
    source = result.get("source_verification", "not_checked")
    interaction = "reproduced" if result["interaction_reproduced"] else "not reproduced"
    document = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Interlock witness review</title><style>
body{font:16px/1.55 system-ui,sans-serif;background:#f1f4f8;color:#142d4e;margin:0}main{max-width:1280px;margin:auto;padding:2rem}h1{font-size:2.2rem;line-height:1.2}h2{font-size:1.2rem}p{max-width:80ch}details{background:white;margin:1.4rem 0;border:1px solid #b5c3d4}summary{padding:1rem;font-weight:650;cursor:pointer;overflow-wrap:anywhere}summary:focus-visible{outline:3px solid #006357}.versions{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:#b5c3d4}.versions section{background:white;padding:.9rem;min-width:0}h3{font-size:1rem;margin:0 0 .8rem}.pass{color:#006357}.fail{color:#983d27}pre{font:12px/1.5 monospace;white-space:pre-wrap;overflow-wrap:anywhere;margin:0}.limits{border-left:4px solid #142d4e;padding:.5rem 1rem;background:white}@media(max-width:950px){.versions{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:550px){main{padding:1rem}.versions{grid-template-columns:1fr}}
</style></head><body><main><h1>Interlock witness review</h1><h2>''' + escape(name) + '</h2><p>Interaction on this sequence: <strong>' + interaction + '</strong>.</p><p>Execution: ' + escape(scope) + '; source identity: ' + escape(source) + '.</p><p class="limits">This review covers one event sequence, not complete branch safety or globally shortest failure. ' + escape(result["scope"]) + '</p><p>Showing ' + str(len(selected)) + ' of ' + str(len(trace)) + ' recorded states. Initial and recent states are kept when possible; omitted states are not shown.</p>' + ''.join(frames) + '</main></body></html>'
    if len(document.encode("utf-8")) > 32 * 1024 * 1024:
        raise ValueError("rendered witness view exceeds 32 MiB; lower --max-frames")
    return document
