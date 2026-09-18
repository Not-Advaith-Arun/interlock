"""Process a request atomically and acknowledge its job identity."""


class Worker:
    def __init__(self, transport, effects):
        self.transport = transport
        self.effects = effects

    def receive(self, request):
        job = request.payload
        self.effects.perform(job, request.message_id)
        self.transport.send_ack(request.message_id, job.job_id)
