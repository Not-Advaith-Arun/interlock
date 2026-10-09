"""Independent bounded model with both-job early/stale timers and ack loss."""

from collections import Counter
from copy import deepcopy


class RetryEnvelopeModel:
    def validate(self, config):
        if set(config) != {"max_in_flight", "retain_all_jobs"}:
            raise ValueError("multi-job-retry-envelope-v2 requires max_in_flight and retain_all_jobs")
        if type(config["max_in_flight"]) is not int or config["max_in_flight"] not in (1, 2):
            raise ValueError("max_in_flight must be 1 or 2")
        if type(config["retain_all_jobs"]) is not bool:
            raise ValueError("retain_all_jobs must be a boolean")

    def initial(self, config):
        return {"submitted": [], "requests": [], "acks": [], "delivered": [],
                "dropped": [], "effects": [], "remembered": [], "completed": [],
                "completion_causes": [], "retried": [], "timed_out": [], "ignored_timers": []}

    def enabled(self, state, config):
        events = []
        if len(state["submitted"]) < 2 and len(state["submitted"]) - len(state["completed"]) < config["max_in_flight"]:
            events.append("submit:" + ("a", "b")[len(state["submitted"])])
        events.extend("deliver:" + token for token in state["requests"])
        events.extend("acknowledge:" + token for token in state["acks"])
        events.extend("drop_ack:" + token for token in state["acks"])
        events.extend("timeout:" + job + ":0" for job in state["submitted"] if job not in state["timed_out"])
        return tuple(events)

    def step(self, state, event, config):
        result = deepcopy(state)
        action, token = event.split(":", 1)
        job = token.split(":")[0]
        if action == "submit":
            result["submitted"].append(job)
            result["requests"].append(job + ":0")
        elif action == "deliver":
            result["requests"].remove(token)
            result["delivered"].append(token)
            if job not in result["remembered"]:
                result["effects"].append(token)
            result["remembered"] = sorted(set(result["remembered"]) | {job}) if config["retain_all_jobs"] else [job]
            result["acks"].append(token)
        elif action == "acknowledge":
            result["acks"].remove(token)
            if job not in result["completed"]:
                result["completed"].append(job)
                result["completion_causes"].append({"job_id": job, "acknowledgement_id": "ack:" + token})
        elif action == "drop_ack":
            result["acks"].remove(token)
            result["dropped"].append(token)
        elif action == "timeout":
            result["timed_out"].append(job)
            if job in result["completed"]:
                result["ignored_timers"].append(job)
            else:
                result["retried"].append(job)
                result["requests"].append(job + ":1")
        else:
            raise ValueError(f"unknown retry envelope event: {event}")
        return result

    def violations(self, state, config):
        violations = []
        counts = Counter(token.split(":")[0] for token in state["effects"])
        if any(count > 1 for count in counts.values()):
            violations.append("at_most_one_effect_per_job")
        if any(not counts[job] for job in state["completed"]):
            violations.append("completion_requires_matching_effect")
        if any(cause["acknowledgement_id"].split(":")[1] != cause["job_id"] for cause in state["completion_causes"]):
            violations.append("acknowledgement_matches_completed_job")
        return tuple(sorted(violations))
