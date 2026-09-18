"""A bounded producer supporting correlated and legacy FIFO acknowledgements."""


class Producer:
    MAX_IN_FLIGHT = 1

    def __init__(self, transport):
        self.transport = transport
        self.submitted = []
        self.pending = {}
        self.completed = []

    def submit(self, job):
        if job.job_id in self.submitted:
            raise ValueError("job already submitted")
        if len(self.pending) >= self.MAX_IN_FLIGHT:
            raise ValueError("producer is at capacity")
        self.submitted.append(job.job_id)
        self.pending[job.job_id] = job
        self.transport.send_job(job)

    def on_acknowledgement(self, acknowledgement):
        job_id = acknowledgement.job_id
        if job_id is None:
            job_id = next(iter(self.pending), None)
        if job_id not in self.pending:
            return None
        del self.pending[job_id]
        self.completed.append(job_id)
        return job_id
