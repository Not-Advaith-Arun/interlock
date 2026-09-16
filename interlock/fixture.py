"""Compare an explicit model with trusted, statically imported application code.

The application handlers never import the model. This adapter uses model replay
as an oracle and observes actual queues, producer state, and business effects.
"""

from collections import Counter, deque
from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path

from .engine import replay
from .models import MODELS
from .scenario import VERSIONS, canonical, fingerprint, validate_scenario
from .fixtures.retry import services
from .fixtures.retry.base.producer import Producer as BaseProducer
from .fixtures.retry.base.worker import Worker as BaseWorker
from .fixtures.retry.left.producer import Producer as LeftProducer
from .fixtures.retry.left.worker import Worker as LeftWorker
from .fixtures.retry.right.producer import Producer as RightProducer
from .fixtures.retry.right.worker import Worker as RightWorker
from .fixtures.retry.merged.producer import Producer as MergedProducer
from .fixtures.retry.merged.worker import Worker as MergedWorker
from .fixtures.retry.fixed.worker import Worker as FixedWorker

MAX_FIXTURE_SCHEDULES = 10_000
JOB = services.Job("job-0001", "Send the bundled fixture notification")


@dataclass(frozen=True)
class Revision:
    producer: type
    worker: type
    producer_path: str
    worker_path: str


@dataclass(frozen=True)
class Fixture:
    configs: dict
    revisions: dict[str, Revision]


def _revision(name, producer, worker, worker_name=None):
    return Revision(producer, worker, f"fixtures/retry/{name}/producer.py",
                    f"fixtures/retry/{worker_name or name}/worker.py")


CONFLICT = Fixture(
    {"base": {"retry_limit": 0, "deduplicate": True},
     "left": {"retry_limit": 1, "deduplicate": True},
     "right": {"retry_limit": 0, "deduplicate": False},
     "merged": {"retry_limit": 1, "deduplicate": False}},
    {"base": _revision("base", BaseProducer, BaseWorker),
     "left": _revision("left", LeftProducer, LeftWorker),
     "right": _revision("right", RightProducer, RightWorker),
     "merged": _revision("merged", MergedProducer, MergedWorker)},
)
FIXED = Fixture(
    {"base": {"retry_limit": 0, "deduplicate": True},
     "left": {"retry_limit": 1, "deduplicate": True},
     "right": {"retry_limit": 0, "deduplicate": True},
     "merged": {"retry_limit": 1, "deduplicate": True}},
    {"base": CONFLICT.revisions["base"], "left": CONFLICT.revisions["left"],
     "right": _revision("right", RightProducer, FixedWorker, "fixed"),
     "merged": _revision("merged", MergedProducer, FixedWorker, "fixed")},
)
FIXTURES = {"retry-conflict": CONFLICT, "retry-fixed": FIXED}


def validate_fixture(scenario, name):
    validate_scenario(scenario)
    if name not in FIXTURES:
        raise ValueError("fixture must be one of: " + ", ".join(sorted(FIXTURES)))
    if scenario["model"] != "retry-v1" or scenario["versions"] != FIXTURES[name].configs:
        raise ValueError(f"fixture {name!r} only supports its exact bundled retry-v1 configurations")
    return FIXTURES[name]


def source_identity(name):
    """Hash installed bundled source; no path comes from scenario JSON."""
    fixture = FIXTURES[name]
    paths = {"fixture.py", "models.py", "engine.py", "scenario.py", "fixtures/retry/services.py"}
    paths.update(path for revision in fixture.revisions.values()
                 for path in (revision.producer_path, revision.worker_path))
    root = Path(__file__).parent
    files = {path: hashlib.sha256((root / path).read_bytes()).hexdigest() for path in sorted(paths)}
    return {"sha256": hashlib.sha256(canonical(files).encode()).hexdigest(), "files": files,
            "versions": {version: {"producer": revision.producer_path, "worker": revision.worker_path}
                         for version, revision in fixture.revisions.items()}}


class FixtureRuntime:
    """A real handler instance with controlled message and timer delivery."""

    def __init__(self, revision: Revision):
        self.clock = services.ManualClock()
        self.transport = services.MemoryTransport()
        self.effects = services.EffectSink()
        self.producer = revision.producer(self.transport, self.clock)
        self.worker = revision.worker(self.transport, self.effects)
        self._violated = False

    def enabled(self):
        events = []
        if self.producer.job is None:
            events.append("submit")
        if self.transport.requests:
            events.append("deliver")
        if self.transport.acknowledgements:
            events.extend(("acknowledge", "drop_ack"))
        if not self.producer.completed and self.producer.deadline is not None:
            events.append("timeout")
        return tuple(sorted(events))

    def dispatch(self, event):
        if event not in self.enabled():
            return False
        if event == "submit":
            self.producer.submit(JOB)
        elif event == "deliver":
            self.worker.receive(self.transport.requests.popleft())
        elif event == "acknowledge":
            self.producer.on_acknowledgement(self.transport.acknowledgements.popleft())
        elif event == "drop_ack":
            self.transport.acknowledgements.popleft()
        elif event == "timeout":
            self.clock.advance_to(self.producer.deadline)
            self.producer.on_timeout()
        return True

    def snapshot(self):
        effects = [asdict(effect) for effect in self.effects.records]
        counts = Counter(effect["job_id"] for effect in effects)
        self._violated |= any(count > 1 for count in counts.values())
        violations = ["at_most_one_effect_per_job"] if self._violated else []
        return {"state": {"submitted": self.producer.job is not None,
                          "client_done": self.producer.completed, "attempts": self.producer.attempts,
                          "requests": len(self.transport.requests),
                          "acks": len(self.transport.acknowledgements), "effects": len(effects),
                          "seen": JOB.job_id in self.worker.completed_jobs},
                "enabled": list(self.enabled()), "effect_records": effects,
                "violations": violations, "passed": not violations,
                "clock": self.clock.now,
                "pending_deadline": self.producer.deadline,
                "request_job_ids": [job.job_id for job in self.transport.requests],
                "ack_job_ids": [ack.job_id for ack in self.transport.acknowledgements]}


def replay_fixture(scenario, events, name):
    fixture = validate_fixture(scenario, name)
    modeled = replay(scenario, events)  # Validates event type, count, and legality.
    runtimes = {version: FixtureRuntime(fixture.revisions[version]) for version in VERSIONS}
    trace = []
    first_mismatch = None
    actual_stuttered = []
    for expected_step in modeled["trace"]:
        event = expected_step["event"]
        exceptions = {}
        if event is not None:
            actual_stuttered = []
            for version, runtime in runtimes.items():
                try:
                    if not runtime.dispatch(event):
                        actual_stuttered.append(version)
                except Exception as error:
                    exceptions[version] = f"{type(error).__name__}: {error}"
        actual = {version: runtime.snapshot() for version, runtime in runtimes.items()}
        mismatches = []
        for version in VERSIONS:
            expected = expected_step["outcomes"][version]
            observed = actual[version]
            expected_values = {
                "state": expected["state"], "violations": expected["violations"],
                "enabled": sorted(MODELS[scenario["model"]].enabled(expected["state"], scenario["versions"][version])),
                "effect_records": [asdict(services.Effect(JOB.job_id, JOB.payload))] * expected["state"]["effects"],
                "request_job_ids": [JOB.job_id] * expected["state"]["requests"],
                "ack_job_ids": [JOB.job_id] * expected["state"]["acks"],
            }
            for field, value in expected_values.items():
                if observed[field] != value:
                    mismatches.append({"version": version, "field": field, "expected": value, "observed": observed[field]})
            if version in exceptions:
                mismatches.append({"version": version, "field": "handler_exception", "expected": None,
                                   "observed": exceptions[version]})
        if actual_stuttered != expected_step["stuttered"]:
            mismatches.append({"version": "all", "field": "stuttered",
                               "expected": expected_step["stuttered"], "observed": actual_stuttered})
        item = {"step": expected_step["step"], "event": event,
                "model_outcomes": expected_step["outcomes"], "observed": actual,
                "stuttered": actual_stuttered[:], "agreement": not mismatches,
                "mismatches": mismatches}
        trace.append(item)
        if mismatches:
            first_mismatch = {"step": item["step"], "event": event, "differences": mismatches}
            break
    final = trace[-1]["observed"]
    actual_interaction = not final["merged"]["passed"] and all(final[v]["passed"] for v in VERSIONS[:3])
    return {"format": "interlock-fixture-replay-v1", "fixture": name,
            "source_identity": source_identity(name), "scenario_sha256": fingerprint(scenario),
            "events": list(events), "executed_steps": len(trace) - 1,
            "agreement": first_mismatch is None, "first_mismatch": first_mismatch,
            "model_interaction_reproduced": modeled["interaction_reproduced"],
            "interaction_reproduced": actual_interaction and first_mismatch is None,
            "observed_outcomes": final, "trace": trace,
            "scope": "Trusted bundled handlers; this schedule only. No arbitrary repository execution or general branch analysis."}


def check_fixture(scenario, name, *, max_depth=8, max_schedules=MAX_FIXTURE_SCHEDULES):
    """Check every legal model event prefix up to the bound, without state merging.

    This deliberately differs from model search's state deduplication: paths to a
    repeated model state can expose hidden implementation history. Each prefix
    starts fresh handler instances. A hard schedule cap reports incomplete work.
    """
    validate_fixture(scenario, name)
    if type(max_depth) is not int or not 0 <= max_depth <= 64:
        raise ValueError("max_depth must be an integer between 0 and 64")
    if type(max_schedules) is not int or not 1 <= max_schedules <= MAX_FIXTURE_SCHEDULES:
        raise ValueError(f"max_schedules must be between 1 and {MAX_FIXTURE_SCHEDULES}")
    queue = deque([()])
    checked = checked_steps = maximum_depth = 0
    failure = None
    while queue and checked < max_schedules:
        events = queue.popleft()
        result = replay_fixture(scenario, events, name)
        checked += 1
        checked_steps += result["executed_steps"]
        maximum_depth = max(maximum_depth, len(events))
        if not result["agreement"]:
            failure = result
            break
        if len(events) < max_depth:
            enabled = sorted({event for outcome in result["observed_outcomes"].values() for event in outcome["enabled"]})
            queue.extend(events + (event,) for event in enabled)
    complete = not queue and failure is None
    return {"format": "interlock-fixture-check-v1", "fixture": name,
            "status": "fixture_mismatch" if failure else "agreement" if complete else "incomplete",
            "source_identity": source_identity(name), "scenario_sha256": fingerprint(scenario),
            "bounds": {"max_depth": max_depth, "max_schedules": max_schedules},
            "coverage": {"complete_up_to_depth": complete, "schedules_checked": checked,
                         "event_steps_executed": checked_steps, "depth_reached": maximum_depth},
            "first_mismatch": failure,
            "scope": "All checked legal prefixes against bundled handlers; no unbounded or arbitrary-source fidelity claim."}
