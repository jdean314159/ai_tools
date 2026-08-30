from __future__ import annotations

import sys
from types import SimpleNamespace

from engram.embeddings.sentence_transformers import SentenceTransformersEmbedder


def test_prefers_current_dimension_api(monkeypatch):
    calls = []

    class FakeModel:
        def __init__(self, model, device):
            calls.append((model, device))
        def get_embedding_dimension(self):
            return 384
        def get_sentence_embedding_dimension(self):
            raise AssertionError("deprecated method should not be used")

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=FakeModel))
    embedder = SentenceTransformersEmbedder(model="cached", device="cpu")
    assert embedder.dimension == 384
    assert calls == [("cached", "cpu")]


def test_supports_older_dimension_api(monkeypatch):
    class FakeModel:
        def __init__(self, model, device):
            pass
        def get_sentence_embedding_dimension(self):
            return 128

    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=FakeModel))
    assert SentenceTransformersEmbedder().dimension == 128
