class GammaHistory:
    def dispatch(self):
        return self.commit()

    def commit(self):
        return history_change()


def history_change():
    return True
