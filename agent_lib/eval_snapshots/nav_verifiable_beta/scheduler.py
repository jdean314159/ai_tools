class BetaScheduler:
    def execute(self):
        return self.publish()

    def publish(self):
        return schedule_event()


def schedule_event():
    return True
