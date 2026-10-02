"""Match witness scenario identity to declarations without executing schedules."""
from .witness_inspection import inspect_witness
from .model_cases import validated_cases
from .scenario import fingerprint
from .report_cards import render_report


def match_witness_cases(witness,manifest):
    inspected=inspect_witness(witness);cases=validated_cases(manifest)
    matches=[{'id':row['id'],'expected_status':row['expected_status'],'scenario_sha256':fingerprint(row['scenario'])}for row in cases if fingerprint(row['scenario'])==inspected['scenario_sha256']]
    return {'format':'interlock-witness-case-match-v1','witness_canonical_sha256':inspected['witness_canonical_sha256'],'scenario_sha256':inspected['scenario_sha256'],'event_count':inspected['event_count'],'source_binding_recorded':inspected['source_binding_recorded'],'manifest_cases':len(cases),'matched':bool(matches),'matches':matches,'execution_scope':'none','source_verification':'not_checked','event_legality':'not_checked',
        'scope':'Complete witness envelope and all manifest declarations structurally validated; matching uses exact canonical scenario identity only. Expected classifications remain caller declarations, not witness outcomes or passing-run evidence. Event legality, states, model behavior, recorded source bindings and installed sources are not checked. No model transitions, replay, handlers, source reads or imported application code. Private scenario wording/configuration, event names and source paths omitted; IDs/hashes may be sensitive. A match is not authenticity, approved expectations, independent reproducibility or safety.'}


def render_witness_case_match(report):
    rows=[{'group':'Matching declared case','cells':[row['id'],row['expected_status'],row['scenario_sha256']]}for row in report['matches']]
    return render_report('Interlock witness declaration match',report['scope'],['Explicit case ID','Caller expectation','Canonical scenario identity'],rows,payload=report,summary=f"{len(rows)} matching declaration(s) among {report['manifest_cases']}; {report['event_count']} recorded events. Schedule legality/outcomes and source bindings remain unchecked; no replay occurred.")
