class Scheduler:
    def start(self, loop, future, completer):
        completer.complete(future)
