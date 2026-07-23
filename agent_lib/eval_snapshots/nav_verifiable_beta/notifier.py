class BetaNotifier:
    def execute(self):
        return self.publish()

    def publish(self):
        return notify_event()


def notify_event():
    return True
