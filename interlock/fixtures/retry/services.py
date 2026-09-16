"""Injected dependencies. No model imports, wall-clock reads, files, or sockets."""

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class Job:
    job_id: str
    payload: str


@dataclass(frozen=True)
class Acknowledgement:
    job_id: str


@dataclass(frozen=True)
class Effect:
    job_id: str
    payload: str


class ManualClock:
    def __init__(self):
        self.now = 0

    def advance_to(self, deadline: int) -> None:
        if type(deadline) is not int or deadline < self.now:
            raise ValueError("clock cannot move backwards")
        self.now = deadline


class MemoryTransport:
    def __init__(self):
        self.requests = deque()
        self.acknowledgements = deque()

    def send_job(self, job: Job) -> None:
        self.requests.append(job)

    def send_ack(self, job_id: str) -> None:
        self.acknowledgements.append(Acknowledgement(job_id))


class EffectSink:
    """Each append is an observable business effect for the submitted job."""
    def __init__(self):
        self.records = []

    def perform(self, job: Job) -> None:
        self.records.append(Effect(job.job_id, job.payload))
