"""Bounded producer with one retryable job and correlated acknowledgements."""


class Producer:
    MAX_IN_FLIGHT = 2

    def __init__(self, transport):
        self.transport = transport
        self.submitted = []
        self.pending = {}
        self.completed = []
        self.attempts = {}
        self.retry_sent = False

    def submit(self, job):
        if job.job_id in self.submitted or len(self.pending) >= self.MAX_IN_FLIGHT:
            raise ValueError("duplicate job or capacity exceeded")
        self.submitted.append(job.job_id)
        self.pending[job.job_id] = job
        self.attempts[job.job_id] = 0
        self.transport.send_job(job, 0)

    def on_timeout(self):
        # The injected scheduler chooses this timer after a lost ack. The
        # application is never notified of the transport's loss decision.
        if "a" not in self.pending or self.retry_sent:
            return False
        self.retry_sent = True
        self.attempts["a"] = 1
        self.transport.send_job(self.pending["a"], 1)
        return True

    def on_acknowledgement(self, acknowledgement):
        job_id = acknowledgement.job_id
        if job_id not in self.pending:
            return None
        del self.pending[job_id]
        self.completed.append(job_id)
        return job_id
