"""Observe independently executed early/stale retry callbacks and both-job loss."""

from dataclasses import asdict, dataclass

from .multijob_retry_fixture import MultiJobRetryRuntime, JOBS, CONFLICT_CONFIGS, FIXED_CONFIGS
from .fixtures.multijob_retry.base.worker import Worker as RetainingWorker
from .fixtures.multijob_retry.right.worker import Worker as LastJobWorker
from .fixtures.retry_envelope.serial import Producer as SerialProducer
from .fixtures.retry_envelope.pipelined import Producer as PipelinedProducer

# Frozen before implementing/searching the model. This direct diagnostic remains
# separate from bounded exhaustive exploration, including at shallower depths.
BRANCH_FAILURE_PROBE = ('submit:a', 'timeout:a:0', 'deliver:a:0', 'acknowledge:a:0',
                        'submit:b', 'deliver:b:0', 'deliver:a:1')

CASE = {
    "kind": "synthetic",
    "invariants": ["at_most_one_effect_per_job", "completion_requires_matching_effect",
                   "acknowledgement_matches_completed_job"],
    "scope": "Two jobs, one consumable original-attempt timer and at most one retry per job; any emitted ack may be dropped. Atomic handlers; no crashes, request loss, repeated retries, physical time, or liveness claim.",
    "event_alignment": "Job/attempt identities; disabled actions stutter independently. A stale callback is consumed and recorded even when ignored by the producer.",
    "fault_model": "Timers may arrive before request delivery or after completion. In-flight retries survive acknowledgement; single-entry dedup is independently unsafe in right.",
    "suite_scope": "Opt-in broader envelope; unchanged exploration caps may report incomplete. Not part of the eight-case complete suite.",
}


@dataclass(frozen=True)
class EnvelopeRevision:
    producer: type
    worker: type
    producer_path: str
    worker_path: str

    @property
    def sources(self):
        return {"producer": self.producer_path, "worker": self.worker_path}


def _revision(pipeline, retain):
    return EnvelopeRevision(PipelinedProducer if pipeline else SerialProducer,
                            RetainingWorker if retain else LastJobWorker,
                            "fixtures/retry_envelope/" + ("pipelined.py" if pipeline else "serial.py"),
                            "fixtures/multijob_retry/" + ("base" if retain else "right") + "/worker.py")


CONFLICT_REVISIONS = {version: _revision(config["max_in_flight"] == 2, config["retain_all_jobs"])
                      for version, config in CONFLICT_CONFIGS.items()}
FIXED_REVISIONS = {version: _revision(config["max_in_flight"] == 2, True)
                   for version, config in FIXED_CONFIGS.items()}


class RetryEnvelopeRuntime(MultiJobRetryRuntime):
    def __init__(self, revision):
        super().__init__(revision)
        self.timers = []
        self.timer_records = []
        self.timer_deliveries = []
        self.retried = []

    def enabled(self):
        events = []
        if len(self.producer.submitted) < len(JOBS) and len(self.producer.pending) < self.producer.MAX_IN_FLIGHT:
            events.append("submit:" + JOBS[len(self.producer.submitted)].job_id)
        events.extend("deliver:" + message.message_id.removeprefix("request:") for message in self.transport.requests)
        for message in self.transport.acknowledgements:
            token = message.message_id.removeprefix("ack:")
            events.extend(("acknowledge:" + token, "drop_ack:" + token))
        events.extend("timeout:" + timer["timer_id"].removeprefix("timer:") for timer in self.timers)
        return tuple(sorted(events))

    def dispatch(self, event):
        if event not in self.enabled():
            return False
        action, token = event.split(":", 1)
        self.clock += 1
        if action == "submit":
            self.producer.submit(next(job for job in JOBS if job.job_id == token))
            timer = {"timer_id": f"timer:{token}:0", "parent_id": f"request:{token}:0",
                     "job_id": token, "attempt": 0}
            self.timers.append(timer)
            self.timer_records.append(timer)
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
            self.transport.dropped.append(self.transport.take(self.transport.acknowledgements, "ack:" + token))
        elif action == "timeout":
            timer = next(timer for timer in self.timers if timer["timer_id"] == "timer:" + token)
            self.timers.remove(timer)
            sent = self.producer.on_timeout(timer["job_id"], timer["attempt"])
            self.timer_deliveries.append({**timer, "retry_sent": sent})
            if sent:
                self.retried.append(timer["job_id"])
        self._record_violations()
        return True

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
                          "retried": list(self.retried),
                          "timed_out": [timer["job_id"] for timer in self.timer_deliveries],
                          "ignored_timers": [timer["job_id"] for timer in self.timer_deliveries if not timer["retry_sent"]]},
                "enabled": list(self.enabled()), "effect_records": [asdict(effect) for effect in self.effects.records],
                "request_records": [asdict(message) for message in self.transport.requests],
                "ack_records": [asdict(message) for message in self.transport.acknowledgements],
                "lost_ack_records": [asdict(message) for message in self.transport.dropped],
                "message_records": sorted((asdict(message) for message in self.transport.sent), key=lambda message: message["message_id"]),
                "timer_records": [dict(timer) for timer in self.timer_records],
                "pending_timer_records": [dict(timer) for timer in self.timers],
                "timer_deliveries": [dict(timer) for timer in self.timer_deliveries],
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

        def timer(job):
            return {"timer_id": f"timer:{job}:0", "parent_id": f"request:{job}:0", "job_id": job, "attempt": 0}

        sent = [request(job + ":0") for job in state["submitted"]]
        sent.extend(request(job + ":1") for job in state["retried"])
        sent.extend(acknowledgement(token) for token in state["delivered"])
        return {"effect_records": [{"job_id": token.split(":")[0], "payload": payloads[token.split(":")[0]],
                                    "request_id": "request:" + token} for token in state["effects"]],
                "request_records": [request(token) for token in state["requests"]],
                "ack_records": [acknowledgement(token) for token in state["acks"]],
                "lost_ack_records": [acknowledgement(token) for token in state["dropped"]],
                "message_records": sorted(sent, key=lambda message: message["message_id"]),
                "timer_records": [timer(job) for job in state["submitted"]],
                "pending_timer_records": [timer(job) for job in state["submitted"] if job not in state["timed_out"]],
                "timer_deliveries": [{**timer(job), "retry_sent": job in state["retried"]} for job in state["timed_out"]],
                "pending_jobs": [job for job in state["submitted"] if job not in state["completed"]],
                "attempts": {job: int(job in state["retried"]) for job in state["submitted"]}}
