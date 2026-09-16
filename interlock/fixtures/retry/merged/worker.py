"""Worker handler: the effect and duplicate check form one atomic delivery."""


class Worker:
    def __init__(self, transport, effects):
        self.transport = transport
        self.effects = effects
        self.completed_jobs = set()

    def receive(self, job):
        self.effects.perform(job)
        self.completed_jobs.add(job.job_id)
        self.transport.send_ack(job.job_id)
