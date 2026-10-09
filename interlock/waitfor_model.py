"""Finite cancellation-resolution model; no asyncio or source execution."""

from collections import deque
import json

CASES = ("completed_external", "pending_external", "no_cancel", "timeout", "timeout_suppressed")
POLICIES = ("before", "fix")


class WaitForModel:
    def __init__(self, policy, case):
        if policy not in POLICIES or case not in CASES:
            raise ValueError("unknown historical policy or case")
        self.policy, self.case = policy, case
        self.completed = case in ("completed_external", "no_cancel")
        self.origin = ("external" if case.endswith("external") else
                       "timer" if case.startswith("timeout") else "none")

    @staticmethod
    def initial():
        return {"inner": "absent", "outer": "absent", "origin": "none",
                "pending_cancel": "none", "cancel_accepted": False,
                "suppressed": False, "reached_end": False, "violation": False}

    def enabled(self, state):
        if state["inner"] == "absent":
            return ("start_inner",)
        if state["outer"] == "absent":
            if self.completed and state["inner"] == "pending":
                return ("complete_inner",)
            return ("start_outer",)
        if state["outer"] in ("returned", "cancelled", "timed_out"):
            return ()
        if state["pending_cancel"] != "none":
            return ("resume_outer",)
        events = []
        if state["origin"] == "none":
            if self.origin == "external":
                events.append("external_cancel")
            elif self.origin == "timer":
                events.append("deadline")
        if state["outer"] == "waiting" and state["inner"] == "result":
            events.append("resume_outer")
        if state["outer"] == "post_wait" and (self.origin == "none" or state["origin"] != "none"):
            events.append("finish_outer")
        return tuple(sorted(events))

    def step(self, state, event):
        if event not in self.enabled(state):
            raise ValueError(f"disabled historical event: {event}")
        result = dict(state)
        if event == "start_inner":
            result["inner"] = "pending"
        elif event == "complete_inner":
            result["inner"] = "result"
        elif event == "start_outer":
            result["outer"] = ("post_wait" if self.policy == "fix" and result["inner"] == "result" else "waiting")
        elif event == "external_cancel":
            result.update(origin="external", pending_cancel="external", cancel_accepted=True)
            if result["inner"] == "pending":
                result["inner"] = "cancelled"
        elif event == "deadline":
            result.update(origin="timer", pending_cancel="timer")
            if self.case == "timeout_suppressed":
                result.update(inner="suppressed_result", suppressed=True)
            else:
                result["inner"] = "cancelled"
        elif event == "resume_outer":
            origin = result["pending_cancel"]
            if origin == "external":
                result["outer"] = ("post_wait" if self.policy == "before" and
                                   result["outer"] == "waiting" and result["inner"] == "result" else "cancelled")
            elif origin == "timer":
                result["outer"] = "post_wait" if result["suppressed"] else "timed_out"
            else:
                result["outer"] = "post_wait"
            result["pending_cancel"] = "none"
        elif event == "finish_outer":
            result.update(outer="returned", reached_end=True)
        if result["cancel_accepted"] and (result["outer"] == "returned" or result["reached_end"]):
            result["violation"] = True
        return result

    @staticmethod
    def projection(state):
        return {"outer": state["outer"], "inner": state["inner"],
                "result": 42 if state["outer"] == "returned" and state["suppressed"] else
                          "done" if state["outer"] == "returned" else None,
                "cancel_accepted": state["cancel_accepted"], "reached_end": state["reached_end"],
                "origin": state["origin"], "suppressed": state["suppressed"],
                "violation": state["violation"]}

    def calibration(self):
        """The declared source schedule, separate from other model orderings."""
        state, events = self.initial(), []
        while self.enabled(state):
            enabled = self.enabled(state)
            event = "external_cancel" if "external_cancel" in enabled else enabled[0]
            events.append(event)
            state = self.step(state, event)
        return {"events": events, "projection": self.projection(state)}


def explore(policy, case, *, max_depth=12, max_states=512, max_prefixes=4096):
    for value, maximum in ((max_depth, 12), (max_states, 512), (max_prefixes, 4096)):
        if type(value) is not int or not 0 < value <= maximum:
            raise ValueError("historical exploration budgets must be positive and within frozen caps")
    model = WaitForModel(policy, case)
    initial = model.initial()
    queue = deque([(initial, ())])
    seen = {json.dumps(initial, sort_keys=True)}
    prefixes = transitions = depth_limited = 0
    first_failure = None
    reason = "exhausted"
    while queue:
        if prefixes >= max_prefixes:
            reason = "prefix_budget"
            break
        state, events = queue.popleft()
        prefixes += 1
        if state["violation"] and first_failure is None:
            first_failure = list(events)
        enabled = model.enabled(state)
        if len(events) == max_depth:
            depth_limited += bool(enabled)
            continue
        for event in enabled:
            following = model.step(state, event)
            key = json.dumps(following, sort_keys=True)
            if key not in seen and len(seen) >= max_states:
                reason = "state_budget"
                break
            seen.add(key)
            transitions += 1
            queue.append((following, events + (event,)))
        if reason == "state_budget":
            break
    if reason == "exhausted" and depth_limited:
        reason = "depth_bound"
    return {"policy": policy, "case": case, "complete": reason == "exhausted",
            "termination": reason, "states": len(seen), "prefixes": prefixes,
            "transitions": transitions, "depth_limited_prefixes": depth_limited,
            "queued_prefixes": len(queue), "first_violation": first_failure,
            "bounds": {"depth": max_depth, "states": max_states, "prefixes": max_prefixes},
            "calibration": model.calibration()}


def model_report():
    return {"scope": "Finite cancellation-resolution decisions only; not event-loop or source-prefix coverage.",
            "results": [explore(policy, case) for policy in POLICIES for case in CASES]}
