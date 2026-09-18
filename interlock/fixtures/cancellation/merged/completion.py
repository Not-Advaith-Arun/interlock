class Completer:
    def __init__(self):
        self.records = []

    def complete(self, future):
        future.set_result("ready")
        self.records.append({"result": "ready"})
