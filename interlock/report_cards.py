"""Small offline cards for explicit, read-only report metadata."""
from html import escape
import json
from pathlib import Path


def render_report(title, scope, columns, rows, *, payload, summary=None, extra_script=""):
    def text(value):
        return escape(str(value), quote=True)
    groups=sorted({row['group'] for row in rows})
    cards=[]
    for row in rows:
        cells=''.join('<div class="report-cell"><dt>'+text(label)+'</dt><dd>'+text(value)+'</dd></div>' for label,value in zip(columns,row['cells']))
        cards.append('<article class="report-card" data-group="'+text(row['group'])+'"><dl>'+cells+'</dl></article>')
    options=''.join('<option value="'+text(group)+'">'+text(group.replace('_',' '))+'</option>' for group in groups)
    data=json.dumps(payload,ensure_ascii=True).replace('<','\\u003c').replace('&','\\u0026')
    scope_html=('<p class="scope">'+text(scope)+'</p>' if summary is None else
        '<p class="critical-summary">'+text(summary)+'</p><details class="report-scope"><summary>Scope and limitations</summary><p class="scope">'+text(scope)+'</p></details>')
    assets=Path(__file__).with_name('ui')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; script-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
        '<title>'+text(title)+'</title><style>'+assets.joinpath('report.css').read_text(encoding='utf-8')+'</style></head><body><main>'
        '<div class="topline"><span>Local workspace / Read-only report</span><button id="theme" type="button" aria-pressed="false">Dark theme</button></div>'
        '<h1>'+text(title)+'</h1>'+scope_html+'<div class="filters"><label>Search report<input id="find" aria-label="Search report" type="search" autocomplete="off"></label>'
        '<label>Show group<select id="group" aria-label="Show group"><option value="">All groups</option>'+options+'</select></label><button id="download" type="button">Download report JSON</button><button id="download-view" type="button">Download visible rows</button><p class="view-export-note">Visible-row download is a static printable display with full scope warnings. It excludes native JSON and draft inputs; inspect downloaded copies before sharing.</p><output id="matches" aria-live="polite"></output></div>'
        '<section aria-label="Report results">'+''.join(cards)+'</section><p id="empty" hidden>No rows match this view.</p><footer>Captured report only. Filtering changes the display, never the underlying inputs. This page cannot apply changes, perform verification or refresh external state.</footer></main>'
        '<script id="report-data" type="application/json">'+data+'</script><script>'+assets.joinpath('report.js').read_text(encoding='utf-8')+'\n'+extra_script+'\n'+assets.joinpath('review_views.js').read_text(encoding='utf-8')+'</script></body></html>')
