"""Producer handler: retry policy is source code, not a model configuration."""


class Producer:
    MAX_ATTEMPTS = 1
    RETRY_DELAY = 10

    def __init__(self, transport, clock):
        self.transport = transport
        self.clock = clock
        self.job = None
        self.completed = False
        self.attempts = 0
        self.deadline = None

    def submit(self, job):
        if self.job is not None:
            raise ValueError("this producer accepts one logical job")
        self.job = job
        self._send()

    def _send(self):
        self.transport.send_job(self.job)
        self.attempts += 1
        self.deadline = (self.clock.now + self.RETRY_DELAY
                         if self.attempts < self.MAX_ATTEMPTS else None)

    def on_timeout(self):
        if self.completed or self.deadline is None or self.clock.now < self.deadline:
            return False
        self._send()
        return True

    def on_acknowledgement(self, acknowledgement):
        if self.job is not None and acknowledgement.job_id == self.job.job_id:
            self.completed = True
            self.deadline = None
