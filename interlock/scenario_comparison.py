"""Directional comparison of validated declarations, without execution."""

from .scenario import VERSIONS, fingerprint, validate_scenario


def compare_scenarios(left, right):
    validate_scenario(left)
    validate_scenario(right)
    if left["model"] != right["model"]:
        raise ValueError("scenario comparison requires the same model")
    versions = {}
    for version in VERSIONS:
        before, after = left["versions"][version], right["versions"][version]
        changes = [{"field": key, "before": before.get(key), "after": after.get(key),
                    "before_present": key in before, "after_present": key in after}
                   for key in sorted(set(before) | set(after))
                   if key not in before or key not in after or before[key] != after[key]]
        versions[version] = {"changed": bool(changes), "changes": changes}
    return {"format": "interlock-scenario-comparison-v1", "model": left["model"],
            "left": {"name": left["name"], "sha256": fingerprint(left)},
            "right": {"name": right["name"], "sha256": fingerprint(right)},
            "declarations_identical": left == right, "versions": versions,
            "scope": "Directional declared configuration differences only. No model search, handler execution, behavioral equivalence or safety verdict. Name-only changes affect fingerprints but not version configurations."}
