"""Message instances and effects for the independent bundled application."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    job_id: str
    payload: str


@dataclass(frozen=True)
class Request:
    job_id: str
    payload: str
    attempt: int


@dataclass(frozen=True)
class Acknowledgement:
    job_id: str
    attempt: int


@dataclass(frozen=True)
class Envelope:
    message_id: str
    parent_id: str | None
    payload: Request | Acknowledgement


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
        self.dropped = []

    def send_job(self, job, attempt):
        parent = f"request:{job.job_id}:0" if attempt else None
        message = Envelope(f"request:{job.job_id}:{attempt}", parent,
                           Request(job.job_id, job.payload, attempt))
        self.requests.append(message)
        self.sent.append(message)

    def send_ack(self, request):
        message = Envelope(f"ack:{request.payload.job_id}:{request.payload.attempt}", request.message_id,
                           Acknowledgement(request.payload.job_id, request.payload.attempt))
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

    def perform(self, request):
        self.records.append(Effect(request.payload.job_id, request.payload.payload, request.message_id))
