"""Pure, deterministic models. Scenario JSON never imports or executes code."""

from typing import Any, Protocol

from .multijob import MultiJobModel
from .multijob_retry import MultiJobRetryModel
from .retry_envelope import RetryEnvelopeModel

State = dict[str, Any]
Config = dict[str, Any]


class Model(Protocol):
    def validate(self, config: Config) -> None: ...
    def initial(self, config: Config) -> State: ...
    def enabled(self, state: State, config: Config) -> tuple[str, ...]: ...
    def step(self, state: State, event: str, config: Config) -> State: ...
    def violations(self, state: State, config: Config) -> tuple[str, ...]: ...


class RetryModel:
    """One logical job, delayed acknowledgements, atomic worker deduplication."""

    def validate(self, config: Config) -> None:
        if set(config) != {"retry_limit", "deduplicate"}:
            raise ValueError("retry-v1 requires exactly retry_limit and deduplicate")
        if type(config["retry_limit"]) is not int or not 0 <= config["retry_limit"] <= 16:
            raise ValueError("retry_limit must be an integer between 0 and 16")
        if type(config["deduplicate"]) is not bool:
            raise ValueError("deduplicate must be a boolean")

    def initial(self, config: Config) -> State:
        return {"submitted": False, "client_done": False, "attempts": 0,
                "requests": 0, "acks": 0, "effects": 0, "seen": False}

    def enabled(self, state: State, config: Config) -> tuple[str, ...]:
        events = []
        if not state["submitted"]:
            events.append("submit")
        if state["requests"]:
            events.append("deliver")
        if state["acks"]:
            events.extend(("acknowledge", "drop_ack"))
        if (state["submitted"] and not state["client_done"]
                and state["attempts"] <= config["retry_limit"]):
            events.append("timeout")
        return tuple(events)

    def step(self, state: State, event: str, config: Config) -> State:
        result = dict(state)
        if event == "submit":
            result.update(submitted=True, attempts=1, requests=1)
        elif event == "deliver":
            result["requests"] -= 1
            result["acks"] += 1
            if not config["deduplicate"] or not result["seen"]:
                result["effects"] += 1
            result["seen"] = True
        elif event == "acknowledge":
            result["acks"] -= 1
            result["client_done"] = True
        elif event == "drop_ack":
            result["acks"] -= 1
        elif event == "timeout":
            result["attempts"] += 1
            result["requests"] += 1
        else:
            raise ValueError(f"unknown retry event: {event}")
        return result

    def violations(self, state: State, config: Config) -> tuple[str, ...]:
        return ("at_most_one_effect_per_job",) if state["effects"] > 1 else ()


class CancellationModel:
    """One future and one completion callback, with externally ordered cancellation.

    This state machine does not execute asyncio or import the bundled handlers.
    A cancelled future must never receive an unguarded completion callback.
    """

    def validate(self, config: Config) -> None:
        if set(config) != {"deferred", "guard_cancelled"}:
            raise ValueError("cancellation-v1 requires exactly deferred and guard_cancelled")
        if any(type(value) is not bool for value in config.values()):
            raise ValueError("deferred and guard_cancelled must be booleans")

    def initial(self, config: Config) -> State:
        return {"future": "absent", "callbacks": 0, "errors": 0}

    def enabled(self, state: State, config: Config) -> tuple[str, ...]:
        events = []
        if state["future"] == "absent":
            events.append("start")
        if state["future"] == "pending":
            events.append("cancel")
        if state["callbacks"]:
            events.append("fire_callback")
        return tuple(events)

    def step(self, state: State, event: str, config: Config) -> State:
        result = dict(state)
        if event == "start":
            result.update(future="pending" if config["deferred"] else "finished",
                          callbacks=int(config["deferred"]))
        elif event == "cancel":
            result["future"] = "cancelled"
        elif event == "fire_callback":
            result["callbacks"] -= 1
            if result["future"] == "cancelled":
                if not config["guard_cancelled"]:
                    result["errors"] += 1
            else:
                result["future"] = "finished"
        else:
            raise ValueError(f"unknown cancellation event: {event}")
        return result

    def violations(self, state: State, config: Config) -> tuple[str, ...]:
        return ("no_completion_after_cancellation",) if state["errors"] else ()


class FiniteStateModel:
    """User-defined finite graphs without expressions, eval, or subprocesses."""

    def validate(self, config: Config) -> None:
        if set(config) != {"initial", "states"}:
            raise ValueError("fsm-v1 requires exactly initial and states")
        states = config["states"]
        if not isinstance(states, dict) or not 1 <= len(states) <= 256:
            raise ValueError("states must be an object containing 1..256 states")
        if any(not isinstance(name, str) or not name or len(name) > 120 for name in states):
            raise ValueError("state names must be nonempty strings of at most 120 characters")
        if not isinstance(config["initial"], str) or config["initial"] not in states:
            raise ValueError("initial must name an existing state")
        for name, state in states.items():
            if not isinstance(state, dict) or set(state) != {"on", "violations"}:
                raise ValueError(f"state {name!r} requires exactly on and violations")
            if not isinstance(state["on"], dict) or len(state["on"]) > 64:
                raise ValueError("on must be an object containing at most 64 transitions")
            for event, target in state["on"].items():
                if not isinstance(event, str) or not event or len(event) > 120:
                    raise ValueError("event names must be nonempty strings of at most 120 characters")
                if not isinstance(target, str) or target not in states:
                    raise ValueError(f"transition {event!r} has an unknown destination")
            violations = state["violations"]
            if (not isinstance(violations, list) or len(violations) > 64
                    or any(not isinstance(v, str) or not v or len(v) > 200 for v in violations)):
                raise ValueError("violations must be a list of at most 64 nonempty short strings")

    def initial(self, config: Config) -> State:
        return {"state": config["initial"]}

    def enabled(self, state: State, config: Config) -> tuple[str, ...]:
        return tuple(config["states"][state["state"]]["on"])

    def step(self, state: State, event: str, config: Config) -> State:
        return {"state": config["states"][state["state"]]["on"][event]}

    def violations(self, state: State, config: Config) -> tuple[str, ...]:
        return tuple(config["states"][state["state"]]["violations"])


MODELS: dict[str, Model] = {"retry-v1": RetryModel(), "fsm-v1": FiniteStateModel(),
                           "cancellation-v1": CancellationModel(), "multi-job-v1": MultiJobModel(),
                           "multi-job-retry-v1": MultiJobRetryModel(),
                           "multi-job-retry-envelope-v2": RetryEnvelopeModel()}
