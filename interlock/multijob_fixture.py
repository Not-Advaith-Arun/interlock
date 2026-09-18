"""Actual two-job producer/worker execution under message-identity scheduling.

JSON never selects executable paths. This adapter imports only bundled handlers
and does not import or call the model. Envelope provenance stays in the harness;
the producer receives only the acknowledgement's application payload.
"""

from dataclasses import asdict, dataclass

from .fixtures.multijob import services
from .fixtures.multijob.base.producer import Producer as BaseProducer
from .fixtures.multijob.base.worker import Worker as BaseWorker
from .fixtures.multijob.left.producer import Producer as LeftProducer
from .fixtures.multijob.left.worker import Worker as LeftWorker
from .fixtures.multijob.right.producer import Producer as RightProducer
from .fixtures.multijob.right.worker import Worker as RightWorker
from .fixtures.multijob.merged.producer import Producer as MergedProducer
from .fixtures.multijob.merged.worker import Worker as MergedWorker

JOBS = (services.Job("a", "Notify account A"), services.Job("b", "Notify account B"))
CASE = {
    "kind": "synthetic",
    "invariants": ["completion_requires_matching_effect", "acknowledgement_matches_completed_job"],
    "scope": "Two jobs, one request each; independently reordered delivery and acknowledgement; atomic handlers, no loss or retries.",
    "event_alignment": "Events identify message instances by job; disabled actions stutter in that revision.",
}
CONFLICT_CONFIGS = {
    "base": {"max_in_flight": 1, "correlate_ack": True},
    "left": {"max_in_flight": 2, "correlate_ack": True},
    "right": {"max_in_flight": 1, "correlate_ack": False},
    "merged": {"max_in_flight": 2, "correlate_ack": False},
}
FIXED_CONFIGS = {v: {**config, "correlate_ack": True} for v, config in CONFLICT_CONFIGS.items()}


@dataclass(frozen=True)
class JobRevision:
    producer: type
    worker: type
    producer_path: str
    worker_path: str

    @property
    def sources(self):
        return {"producer": self.producer_path, "worker": self.worker_path}


def _revision(name, producer, worker, worker_name=None):
    return JobRevision(producer, worker, f"fixtures/multijob/{name}/producer.py",
                       f"fixtures/multijob/{worker_name or name}/worker.py")


CONFLICT_REVISIONS = {
    "base": _revision("base", BaseProducer, BaseWorker),
    "left": _revision("left", LeftProducer, LeftWorker),
    "right": _revision("right", RightProducer, RightWorker),
    "merged": _revision("merged", MergedProducer, MergedWorker),
}
FIXED_REVISIONS = {
    **CONFLICT_REVISIONS,
    "right": _revision("right", RightProducer, BaseWorker, "base"),
    "merged": _revision("merged", MergedProducer, LeftWorker, "left"),
}


class MultiJobRuntime:
    def __init__(self, revision):
        self.transport = services.Transport()
        self.effects = services.EffectSink()
        self.producer = revision.producer(self.transport)
        self.worker = revision.worker(self.transport, self.effects)
        self.completion_causes = []
        self.violations = set()
        self.clock = 0

    def enabled(self):
        events = []
        if (len(self.producer.submitted) < len(JOBS)
                and len(self.producer.pending) < self.producer.MAX_IN_FLIGHT):
            events.append("submit:" + JOBS[len(self.producer.submitted)].job_id)
        events.extend("deliver:" + message.message_id.removeprefix("request:")
                      for message in self.transport.requests)
        events.extend("acknowledge:" + message.message_id.removeprefix("ack:")
                      for message in self.transport.acknowledgements)
        return tuple(sorted(events))

    def dispatch(self, event):
        if event not in self.enabled():
            return False
        action, job_id = event.split(":", 1)
        self.clock += 1  # Logical handler steps, not a wall clock.
        if action == "submit":
            self.producer.submit(next(job for job in JOBS if job.job_id == job_id))
        elif action == "deliver":
            request = self.transport.take(self.transport.requests, "request:" + job_id)
            self.worker.receive(request)
        elif action == "acknowledge":
            message = self.transport.take(self.transport.acknowledgements, "ack:" + job_id)
            completed = self.producer.on_acknowledgement(message.payload)
            if completed is not None:
                self.completion_causes.append({"job_id": completed, "acknowledgement_id": message.message_id})
        self._record_violations()
        return True

    def _record_violations(self):
        performed = {effect.job_id for effect in self.effects.records}
        if any(job not in performed for job in self.producer.completed):
            self.violations.add("completion_requires_matching_effect")
        if any(record["acknowledgement_id"] != "ack:" + record["job_id"] for record in self.completion_causes):
            self.violations.add("acknowledgement_matches_completed_job")

    def snapshot(self):
        self._record_violations()
        return {"state": {"submitted": list(self.producer.submitted),
                          "requests": [m.message_id.removeprefix("request:") for m in self.transport.requests],
                          "acks": [m.message_id.removeprefix("ack:") for m in self.transport.acknowledgements],
                          "effects": [effect.job_id for effect in self.effects.records],
                          "completed": list(self.producer.completed),
                          "completion_causes": [dict(record) for record in self.completion_causes]},
                "enabled": list(self.enabled()), "effect_records": [asdict(effect) for effect in self.effects.records],
                "request_records": [asdict(message) for message in self.transport.requests],
                "ack_records": [asdict(message) for message in self.transport.acknowledgements],
                "message_records": sorted((asdict(message) for message in self.transport.sent), key=lambda m: m["message_id"]),
                "pending_jobs": list(self.producer.pending), "clock": self.clock,
                "violations": sorted(self.violations), "passed": not self.violations}

    @staticmethod
    def expected_observations(state, config):
        payloads = {job.job_id: job.payload for job in JOBS}

        def request(job):
            return {"message_id": "request:" + job, "parent_id": None,
                    "payload": {"job_id": job, "payload": payloads[job]}}

        def acknowledgement(job):
            return {"message_id": "ack:" + job, "parent_id": "request:" + job,
                    "payload": {"job_id": job if config["correlate_ack"] else None}}

        return {"effect_records": [{"job_id": job, "payload": payloads[job], "request_id": "request:" + job}
                                   for job in state["effects"]],
                "request_records": [request(job) for job in state["requests"]],
                "ack_records": [acknowledgement(job) for job in state["acks"]],
                "message_records": sorted([request(job) for job in state["submitted"]]
                                          + [acknowledgement(job) for job in state["effects"]], key=lambda m: m["message_id"]),
                "pending_jobs": [job for job in state["submitted"] if job not in state["completed"]]}
