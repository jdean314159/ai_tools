class AlphaPipeline:
    def run(self):
        return self.prepare()

    def prepare(self):
        return self.validate()

    def validate(self):
        return self.persist()

    def persist(self):
        return write_record()


def write_record():
    return True
