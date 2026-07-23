class BetaWorkflow:
    def execute(self):
        return self.transform()

    def transform(self):
        return self.approve()

    def approve(self):
        return self.publish()

    def publish(self):
        return emit_event()


def emit_event():
    return True
