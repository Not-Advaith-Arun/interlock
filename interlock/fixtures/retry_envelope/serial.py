"""Correlated producer with one timer and at most one retry per logical job."""


class Producer:
    MAX_IN_FLIGHT = 1

    def __init__(self, transport):
        self.transport = transport
        self.submitted = []
        self.pending = {}
        self.completed = []
        self.attempts = {}

    def submit(self, job):
        if job.job_id in self.submitted or len(self.pending) >= self.MAX_IN_FLIGHT:
            raise ValueError("duplicate job or capacity exceeded")
        self.submitted.append(job.job_id)
        self.pending[job.job_id] = job
        self.attempts[job.job_id] = 0
        self.transport.send_job(job, 0)

    def on_timeout(self, job_id, attempt):
        # Timers know nothing about delivery or acknowledgement loss. A stale
        # callback after completion or a changed attempt must not recreate work.
        if job_id not in self.pending or self.attempts[job_id] != attempt or attempt != 0:
            return False
        self.attempts[job_id] = 1
        self.transport.send_job(self.pending[job_id], 1)
        return True

    def on_acknowledgement(self, acknowledgement):
        job_id = acknowledgement.job_id
        if job_id not in self.pending:
            return None
        del self.pending[job_id]
        self.completed.append(job_id)
        return job_id
