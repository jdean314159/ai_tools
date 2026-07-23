class GammaTransaction:
    def dispatch(self):
        return self.commit()

    def commit(self):
        return transaction_change()


def transaction_change():
    return True
