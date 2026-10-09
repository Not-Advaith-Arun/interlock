"""Execute independent handlers for the bounded multi-job lost-ack protocol.

The loss-gated timer is an environment restriction, not a producer notification.
Envelope identities and provenance remain observable even when a job is retried.
"""

from collections import Counter
from dataclasses import asdict, dataclass

from .fixtures.multijob_retry import services
from .fixtures.multijob_retry.base.producer import Producer as BaseProducer
from .fixtures.multijob_retry.base.worker import Worker as BaseWorker
from .fixtures.multijob_retry.left.producer import Producer as LeftProducer
from .fixtures.multijob_retry.left.worker import Worker as LeftWorker
from .fixtures.multijob_retry.right.producer import Producer as RightProducer
from .fixtures.multijob_retry.right.worker import Worker as RightWorker
from .fixtures.multijob_retry.merged.producer import Producer as MergedProducer
from .fixtures.multijob_retry.merged.worker import Worker as MergedWorker

JOBS = (services.Job("a", "Notify account A"), services.Job("b", "Notify account B"))
CASE = {
    "kind": "synthetic",
    "invariants": ["at_most_one_effect_per_job", "completion_requires_matching_effect",
                   "acknowledgement_matches_completed_job"],
    "scope": "Two jobs; only a's original ack may be lost, and a may retry once after that loss. Atomic handlers; other acks reliable; no early timeouts, crashes, or liveness claim.",
    "event_alignment": "Events identify job and attempt; disabled actions stutter. Request/ack envelopes retain exact parent IDs.",
    "fault_model": "The scheduler permits timeout:a:0 only after dropping ack:a:0; the producer receives no loss notification.",
}
CONFLICT_CONFIGS = {
    "base": {"max_in_flight": 1, "retain_all_jobs": True},
    "left": {"max_in_flight": 2, "retain_all_jobs": True},
    "right": {"max_in_flight": 1, "retain_all_jobs": False},
    "merged": {"max_in_flight": 2, "retain_all_jobs": False},
}
FIXED_CONFIGS = {version: {**config, "retain_all_jobs": True} for version, config in CONFLICT_CONFIGS.items()}


@dataclass(frozen=True)
class RetryJobRevision:
    producer: type
    worker: type
    producer_path: str
    worker_path: str

    @property
    def sources(self):
        return {"producer": self.producer_path, "worker": self.worker_path}


def _revision(name, producer, worker, worker_name=None):
    return RetryJobRevision(producer, worker, f"fixtures/multijob_retry/{name}/producer.py",
                            f"fixtures/multijob_retry/{worker_name or name}/worker.py")


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


class MultiJobRetryRuntime:
    def __init__(self, revision):
        self.transport = services.Transport()
        self.effects = services.EffectSink()
        self.producer = revision.producer(self.transport)
        self.worker = revision.worker(self.transport, self.effects)
        self.delivered = []
        self.completion_causes = []
        self.violations = set()
        self.clock = 0

    def enabled(self):
        events = []
        if len(self.producer.submitted) < len(JOBS) and len(self.producer.pending) < self.producer.MAX_IN_FLIGHT:
            events.append("submit:" + JOBS[len(self.producer.submitted)].job_id)
        events.extend("deliver:" + message.message_id.removeprefix("request:") for message in self.transport.requests)
        events.extend("acknowledge:" + message.message_id.removeprefix("ack:") for message in self.transport.acknowledgements)
        if any(message.message_id == "ack:a:0" for message in self.transport.acknowledgements):
            events.append("drop_ack:a:0")
        if (any(message.message_id == "ack:a:0" for message in self.transport.dropped)
                and "a" in self.producer.pending and not self.producer.retry_sent):
            events.append("timeout:a:0")
        return tuple(sorted(events))

    def dispatch(self, event):
        if event not in self.enabled():
            return False
        action, token = event.split(":", 1)
        self.clock += 1
        if action == "submit":
            self.producer.submit(next(job for job in JOBS if job.job_id == token))
        elif action == "deliver":
            request = self.transport.take(self.transport.requests, "request:" + token)
            self.worker.receive(request)
            self.delivered.append(token)
        elif action == "acknowledge":
            message = self.transport.take(self.transport.acknowledgements, "ack:" + token)
            completed = self.producer.on_acknowledgement(message.payload)
            if completed is not None:
                self.completion_causes.append({"job_id": completed, "acknowledgement_id": message.message_id})
        elif action == "drop_ack":
            message = self.transport.take(self.transport.acknowledgements, "ack:" + token)
            self.transport.dropped.append(message)
        elif action == "timeout":
            self.producer.on_timeout()
        self._record_violations()
        return True

    def _record_violations(self):
        counts = Counter(effect.job_id for effect in self.effects.records)
        if any(count > 1 for count in counts.values()):
            self.violations.add("at_most_one_effect_per_job")
        if any(job not in counts for job in self.producer.completed):
            self.violations.add("completion_requires_matching_effect")
        for cause in self.completion_causes:
            source = next(message for message in self.transport.sent if message.message_id == cause["acknowledgement_id"])
            if source.payload.job_id != cause["job_id"]:
                self.violations.add("acknowledgement_matches_completed_job")

    def snapshot(self):
        self._record_violations()
        return {"state": {"submitted": list(self.producer.submitted),
                          "requests": [message.message_id.removeprefix("request:") for message in self.transport.requests],
                          "acks": [message.message_id.removeprefix("ack:") for message in self.transport.acknowledgements],
                          "delivered": list(self.delivered),
                          "dropped": [message.message_id.removeprefix("ack:") for message in self.transport.dropped],
                          "effects": [effect.request_id.removeprefix("request:") for effect in self.effects.records],
                          "remembered": sorted(self.worker.completed_jobs),
                          "completed": list(self.producer.completed),
                          "completion_causes": [dict(cause) for cause in self.completion_causes],
                          "retried": self.producer.retry_sent},
                "enabled": list(self.enabled()), "effect_records": [asdict(effect) for effect in self.effects.records],
                "request_records": [asdict(message) for message in self.transport.requests],
                "ack_records": [asdict(message) for message in self.transport.acknowledgements],
                "lost_ack_records": [asdict(message) for message in self.transport.dropped],
                "message_records": sorted((asdict(message) for message in self.transport.sent), key=lambda message: message["message_id"]),
                "pending_jobs": list(self.producer.pending), "attempts": dict(self.producer.attempts),
                "clock": self.clock, "violations": sorted(self.violations), "passed": not self.violations}

    @staticmethod
    def expected_observations(state, config):
        payloads = {job.job_id: job.payload for job in JOBS}

        def request(token):
            job, attempt = token.split(":")
            return {"message_id": "request:" + token, "parent_id": f"request:{job}:0" if attempt == "1" else None,
                    "payload": {"job_id": job, "payload": payloads[job], "attempt": int(attempt)}}

        def acknowledgement(token):
            job, attempt = token.split(":")
            return {"message_id": "ack:" + token, "parent_id": "request:" + token,
                    "payload": {"job_id": job, "attempt": int(attempt)}}

        sent = [request(job + ":0") for job in state["submitted"]]
        if state["retried"]:
            sent.append(request("a:1"))
        sent.extend(acknowledgement(token) for token in state["delivered"])
        return {"effect_records": [{"job_id": token.split(":")[0], "payload": payloads[token.split(":")[0]],
                                    "request_id": "request:" + token} for token in state["effects"]],
                "request_records": [request(token) for token in state["requests"]],
                "ack_records": [acknowledgement(token) for token in state["acks"]],
                "lost_ack_records": [acknowledgement(token) for token in state["dropped"]],
                "message_records": sorted(sent, key=lambda message: message["message_id"]),
                "pending_jobs": [job for job in state["submitted"] if job not in state["completed"]],
                "attempts": {job: int(job == "a" and state["retried"]) for job in state["submitted"]}}
