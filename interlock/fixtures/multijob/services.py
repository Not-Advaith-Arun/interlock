"""Injected transport and effect recording, independent of the abstract model."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    job_id: str
    payload: str


@dataclass(frozen=True)
class Acknowledgement:
    job_id: str | None


@dataclass(frozen=True)
class Envelope:
    message_id: str
    parent_id: str | None
    payload: Job | Acknowledgement


@dataclass(frozen=True)
class Effect:
    job_id: str
    payload: str
    request_id: str


class Transport:
    def __init__(self):
        self.requests = []
        self.acknowledgements = []
        self.sent = []

    def send_job(self, job):
        message = Envelope("request:" + job.job_id, None, job)
        self.requests.append(message)
        self.sent.append(message)

    def send_ack(self, request_id, job_id):
        message = Envelope("ack:" + request_id.removeprefix("request:"), request_id,
                           Acknowledgement(job_id))
        self.acknowledgements.append(message)
        self.sent.append(message)

    @staticmethod
    def take(queue, message_id):
        for index, message in enumerate(queue):
            if message.message_id == message_id:
                return queue.pop(index)
        raise ValueError(f"message unavailable: {message_id}")


class EffectSink:
    def __init__(self):
        self.records = []

    def perform(self, job, request_id):
        self.records.append(Effect(job.job_id, job.payload, request_id))
