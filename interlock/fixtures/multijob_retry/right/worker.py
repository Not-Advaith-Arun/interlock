"""Atomic job processing with deduplication over logical job identity."""


class Worker:
    RETAIN_ALL_JOBS = False

    def __init__(self, transport, effects):
        self.transport = transport
        self.effects = effects
        self.completed_jobs = set()

    def receive(self, request):
        job_id = request.payload.job_id
        if job_id not in self.completed_jobs:
            self.effects.perform(request)
        if not self.RETAIN_ALL_JOBS:
            self.completed_jobs.clear()
        self.completed_jobs.add(job_id)
        self.transport.send_ack(request)
