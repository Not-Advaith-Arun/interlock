class Scheduler:
    def start(self, loop, future, completer):
        loop.call_later(10, completer.complete, future)
