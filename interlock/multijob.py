"""Pure two-job protocol model with independently reorderable message delivery.

The receiver supports legacy uncorrelated acknowledgements by completing the
oldest pending job. That is safe at capacity one, but unsafe with pipelining.
No handler, transport, or fixture code is imported by this model.
"""

from copy import deepcopy

JOB_IDS = ("a", "b")


class MultiJobModel:
    def validate(self, config: dict) -> None:
        if set(config) != {"max_in_flight", "correlate_ack"}:
            raise ValueError("multi-job-v1 requires exactly max_in_flight and correlate_ack")
        if type(config["max_in_flight"]) is not int or config["max_in_flight"] not in (1, 2):
            raise ValueError("max_in_flight must be 1 or 2")
        if type(config["correlate_ack"]) is not bool:
            raise ValueError("correlate_ack must be a boolean")

    def initial(self, config: dict) -> dict:
        return {"submitted": [], "requests": [], "acks": [], "effects": [],
                "completed": [], "completion_causes": []}

    def enabled(self, state: dict, config: dict) -> tuple[str, ...]:
        events = []
        outstanding = len(state["submitted"]) - len(state["completed"])
        if len(state["submitted"]) < len(JOB_IDS) and outstanding < config["max_in_flight"]:
            events.append("submit:" + JOB_IDS[len(state["submitted"])])
        events.extend("deliver:" + job for job in state["requests"])
        events.extend("acknowledge:" + job for job in state["acks"])
        return tuple(events)

    def step(self, state: dict, event: str, config: dict) -> dict:
        result = deepcopy(state)
        action, job = event.split(":", 1)
        if action == "submit":
            result["submitted"].append(job)
            result["requests"].append(job)
        elif action == "deliver":
            result["requests"].remove(job)
            result["effects"].append(job)
            result["acks"].append(job)
        elif action == "acknowledge":
            result["acks"].remove(job)
            pending = [item for item in result["submitted"] if item not in result["completed"]]
            completed = job if config["correlate_ack"] else pending[0]
            result["completed"].append(completed)
            result["completion_causes"].append({"job_id": completed, "acknowledgement_id": "ack:" + job})
        else:
            raise ValueError(f"unknown multi-job event: {event}")
        return result

    def violations(self, state: dict, config: dict) -> tuple[str, ...]:
        violations = []
        if any(job not in state["effects"] for job in state["completed"]):
            violations.append("completion_requires_matching_effect")
        if any(record["acknowledgement_id"] != "ack:" + record["job_id"]
               for record in state["completion_causes"]):
            violations.append("acknowledgement_matches_completed_job")
        return tuple(sorted(violations))
