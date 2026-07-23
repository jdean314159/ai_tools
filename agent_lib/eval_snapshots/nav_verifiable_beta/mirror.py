class BetaMirror:
    def execute(self):
        return self.publish()

    def publish(self):
        return mirror_event()


def mirror_event():
    return True
