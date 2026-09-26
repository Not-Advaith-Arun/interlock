"""Bound replay trace output while preserving whole-sequence final evidence."""
from .scenario import fingerprint


def trace_page(witness, result, *, start=0, limit=100):
    trace = result["trace"]
    if type(start) is not int or not 0 <= start <= len(trace):
        raise ValueError("trace cursor must identify an original step or the end of this trace")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("trace limit must be1..1000")
    selected = trace[start:start+limit]
    more = start+len(selected) < len(trace)
    return {**result, "trace": selected, "trace_page": {
        "witness_sha256": fingerprint(witness), "from_step": start,
        "total_frames": len(trace), "returned_frames": len(selected), "has_more": more,
        "next_from_step": start+len(selected) if more else None,
        "scope": "Full requested replay completed before output selection. Final outcomes/agreement refer to the entire event sequence, not just these frames. Step0 is initial state. Compare witness identities, execution modes and installed-source identity across separate requests. Paging does not bound replay time/memory or recheck full search safety."}}
