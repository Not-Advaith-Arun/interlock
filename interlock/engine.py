"""Breadth-first product-state exploration with persistent safety violations."""

from collections import deque
from dataclasses import dataclass
from typing import Any

from .models import MODELS, Model, State
from .scenario import VERSIONS, canonical, fingerprint, validate_scenario


@dataclass
class Node:
    states: dict[str, State]
    violations: dict[str, tuple[str, ...]]
    events: tuple[str, ...]


def _initial(model: Model, scenario: dict) -> Node:
    states = {v: model.initial(scenario["versions"][v]) for v in VERSIONS}
    violations = {v: tuple(sorted(set(model.violations(states[v], scenario["versions"][v]))))
                  for v in VERSIONS}
    return Node(states, violations, ())


def _enabled(model: Model, scenario: dict, node: Node) -> list[str]:
    return sorted({event for v in VERSIONS
                   for event in model.enabled(node.states[v], scenario["versions"][v])})


def _advance(model: Model, scenario: dict, node: Node, event: str) -> tuple[Node, list[str]]:
    states, violations, stuttered = {}, {}, []
    for version in VERSIONS:
        config = scenario["versions"][version]
        state = node.states[version]
        if event in model.enabled(state, config):
            states[version] = model.step(state, event, config)
        else:
            states[version] = state
            stuttered.append(version)
        violations[version] = tuple(sorted(set(node.violations[version])
                                           | set(model.violations(states[version], config))))
    return Node(states, violations, node.events + (event,)), stuttered


def _interaction(node: Node) -> bool:
    return bool(node.violations["merged"]) and all(not node.violations[v] for v in VERSIONS[:3])


def _outcomes(node: Node) -> dict:
    return {v: {"passed": not bool(node.violations[v]),
                "violations": list(node.violations[v]), "state": node.states[v]} for v in VERSIONS}


def _key(node: Node) -> str:
    # Safety failures are sticky: returning to a safe-looking state cannot erase a failure.
    return canonical([node.states, node.violations])


def replay(scenario: dict, events: list[str] | tuple[str, ...]) -> dict:
    validate_scenario(scenario)
    if not isinstance(events, (list, tuple)) or len(events) > 1000:
        raise ValueError("events must be a list containing at most 1000 event names")
    if any(not isinstance(event, str) for event in events):
        raise ValueError("event names must be strings")
    model = MODELS[scenario["model"]]
    node = _initial(model, scenario)
    trace = [{"step": 0, "event": None, "stuttered": [], "outcomes": _outcomes(node)}]
    for step, event in enumerate(events, 1):
        if event not in _enabled(model, scenario, node):
            raise ValueError(f"event {event!r} at step {step} is disabled in all versions")
        node, stuttered = _advance(model, scenario, node, event)
        trace.append({"step": step, "event": event, "stuttered": stuttered,
                      "outcomes": _outcomes(node)})
    return {"format": "interlock-replay-v1", "scenario_sha256": fingerprint(scenario),
            "interaction_reproduced": _interaction(node), "events": list(events),
            "outcomes": _outcomes(node), "trace": trace}


def search(scenario: dict, max_depth: int = 8, max_states: int = 50_000) -> dict[str, Any]:
    validate_scenario(scenario)
    if type(max_depth) is not int or not 0 <= max_depth <= 64:
        raise ValueError("max_depth must be an integer between 0 and 64")
    if type(max_states) is not int or not 1 <= max_states <= 1_000_000:
        raise ValueError("max_states must be an integer between 1 and 1000000")
    model = MODELS[scenario["model"]]
    first = _initial(model, scenario)
    queue = deque([first])
    seen = {_key(first)}
    first_failures: dict[str, Any] = {v: None for v in VERSIONS}
    candidate = None
    explored = transitions = depth_reached = 0
    incomplete = False
    while queue:
        node = queue.popleft()
        explored += 1
        depth_reached = max(depth_reached, len(node.events))
        for version in VERSIONS:
            if node.violations[version] and first_failures[version] is None:
                first_failures[version] = {"events": list(node.events),
                                           "violations": list(node.violations[version])}
        if candidate is None and _interaction(node):
            candidate = {"events": list(node.events), "outcomes": _outcomes(node),
                         "minimality": "shortest event count under this model and event ordering"}
        if len(node.events) == max_depth:
            continue
        for event in _enabled(model, scenario, node):
            transitions += 1
            following, _ = _advance(model, scenario, node, event)
            key = _key(following)
            if key in seen:
                continue
            if len(seen) >= max_states:
                incomplete = True
                break
            seen.add(key)
            queue.append(following)
        if incomplete:
            break
    if incomplete:
        status = "incomplete"
    elif first_failures["base"] is not None:
        status = "baseline_failure"
    elif any(first_failures[v] is not None for v in ("left", "right")):
        status = "branch_failure"
    elif candidate is not None:
        status = "merge_interaction_found"
    else:
        status = "no_interaction_within_bound"
    return {"format": "interlock-report-v1", "name": scenario["name"],
            "model": scenario["model"], "scenario_sha256": fingerprint(scenario),
            "status": status, "bounds": {"max_depth": max_depth, "max_states": max_states},
            "coverage": {"complete_up_to_depth": not incomplete,
                         "states_discovered": len(seen), "states_explored": explored,
                         "transitions_explored": transitions, "depth_reached": depth_reached},
            "versions": {v: {"passed_explored_states": first_failures[v] is None,
                             "first_failure": first_failures[v]} for v in VERSIONS},
            "candidate": candidate,
            "scope": "Explicit model only. No source-code analysis or unbounded correctness claim."}


def make_witness(scenario: dict, report: dict) -> dict:
    if report["scenario_sha256"] != fingerprint(scenario):
        raise ValueError("report belongs to a different scenario")
    if report["candidate"] is None:
        raise ValueError("report contains no interaction candidate")
    witness = {"format": "interlock-witness-v1", "scenario": scenario,
               "scenario_sha256": fingerprint(scenario), "events": report["candidate"]["events"]}
    if "fixture" in report:
        checked = report["fixture"]
        reproduced = checked.get("candidate_replay", {})
        if (checked.get("status") != "agreement"
                or not report["coverage"]["complete_up_to_depth"]
                or not reproduced.get("agreement")
                or not reproduced.get("interaction_reproduced")
                or reproduced.get("events") != witness["events"]
                or reproduced.get("source_identity") != checked.get("source_identity")):
            raise ValueError("fixture witness requires a complete check and an agreeing candidate replay")
        witness.update(format="interlock-witness-v2", fixture={
            "name": checked["fixture"], "source_identity": checked["source_identity"]})
        witness["witness_sha256"] = fingerprint(witness)
    return witness


def replay_witness(witness: Any) -> dict:
    if not isinstance(witness, dict):
        raise ValueError("unsupported witness format")
    fields = {"format", "scenario", "scenario_sha256", "events"}
    if witness.get("format") == "interlock-witness-v2":
        fields |= {"fixture", "witness_sha256"}
        if set(witness) != fields:
            raise ValueError("unsupported witness format")
        binding = witness["fixture"]
        if (not isinstance(binding, dict) or set(binding) != {"name", "source_identity"}
                or not isinstance(binding["name"], str) or not binding["name"]
                or not isinstance(binding["source_identity"], dict)):
            raise ValueError("invalid witness fixture identity")
        payload = {key: value for key, value in witness.items() if key != "witness_sha256"}
        if witness["witness_sha256"] != fingerprint(payload):
            raise ValueError("witness fingerprint does not match its contents")
    elif witness.get("format") != "interlock-witness-v1" or set(witness) != fields:
        raise ValueError("unsupported witness format")
    validate_scenario(witness["scenario"])
    if witness["scenario_sha256"] != fingerprint(witness["scenario"]):
        raise ValueError("scenario fingerprint does not match witness")
    return replay(witness["scenario"], witness["events"])
