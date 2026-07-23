class GammaReplica:
    def dispatch(self):
        return self.commit()

    def commit(self):
        return replica_change()


def replica_change():
    return True
