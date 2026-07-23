class GammaController:
    def dispatch(self):
        return self.route()

    def route(self):
        return self.authorize()

    def authorize(self):
        return self.commit()

    def commit(self):
        return save_change()


def save_change():
    return True
