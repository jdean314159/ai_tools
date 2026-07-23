class BetaReporter:
    def execute(self):
        return self.publish()

    def publish(self):
        return report_event()


def report_event():
    return True
