class GammaAudit:
    def dispatch(self):
        return self.commit()

    def commit(self):
        return audit_change()


def audit_change():
    return True
