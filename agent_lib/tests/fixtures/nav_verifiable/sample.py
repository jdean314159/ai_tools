class Store:
    def add(self, value):
        return value


class Pipeline:
    def ingest(self, value):
        return self._prepare(value)

    def _prepare(self, value):
        return self._store_add(value)

    def _store_add(self, value):
        return self.store.add(value)
