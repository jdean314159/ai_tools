"""
tests/contract_tests/test_embedding_model.py

Conformance tests for the EmbeddingModel Protocol.

Requires a dedicated embedding model — chat models (qwen3:8b etc.) do not
support the /api/embed endpoint. Pass --embed-model to enable these tests:

    pytest tests/contract_tests/test_embedding_model.py \
        --backend ollama --embed-model nomic-embed-text
"""
from __future__ import annotations

import pytest

from llm_engines.contracts import (
    EmbeddingModel,
    EmbeddingRequest,
    EmbeddingResponse,
)


@pytest.fixture(scope="module")
def embed_engine(request: pytest.FixtureRequest) -> EmbeddingModel:
    backend = request.config.getoption("--backend", default="mock")
    embed_model = request.config.getoption("--embed-model", default=None)

    if embed_model is None:
        pytest.skip(
            "Pass --embed-model <name> to run embedding tests. "
            "Example: --embed-model nomic-embed-text"
        )

    if backend == "mock":
        pytest.skip("MockEngine does not implement EmbeddingModel")

    if backend == "ollama":
        from llm_engines.backends.ollama import OllamaEngine
        return OllamaEngine(model=embed_model)

    if backend == "openai":
        from llm_engines.backends.openai import OpenAIEngine
        return OpenAIEngine(model=embed_model or "text-embedding-3-small")

    pytest.skip(f"No embedding fixture for backend '{backend}'")


class TestEmbeddingModel:

    def test_returns_embedding_response(self, embed_engine: EmbeddingModel) -> None:
        req = EmbeddingRequest(texts=["Hello world"])
        resp = embed_engine.embed(req)
        assert isinstance(resp, EmbeddingResponse)

    def test_vector_count_matches_input(self, embed_engine: EmbeddingModel) -> None:
        texts = ["First sentence.", "Second sentence.", "Third sentence."]
        resp = embed_engine.embed(EmbeddingRequest(texts=texts))
        assert len(resp.vectors) == len(texts)

    def test_vectors_are_non_empty(self, embed_engine: EmbeddingModel) -> None:
        resp = embed_engine.embed(EmbeddingRequest(texts=["Test"]))
        assert resp.dimensions > 0
        assert len(resp.vectors[0]) == resp.dimensions

    def test_vectors_are_floats(self, embed_engine: EmbeddingModel) -> None:
        resp = embed_engine.embed(EmbeddingRequest(texts=["Test"]))
        assert all(isinstance(v, float) for v in resp.vectors[0])

    def test_similar_texts_have_high_cosine_similarity(
        self, embed_engine: EmbeddingModel
    ) -> None:
        import math
        resp = embed_engine.embed(EmbeddingRequest(texts=[
            "The cat sat on the mat.",
            "A cat is sitting on a mat.",
            "Quantum field theory describes subatomic particles.",
        ]))
        v1, v2, v3 = resp.vectors

        def cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            mag_a = math.sqrt(sum(x ** 2 for x in a))
            mag_b = math.sqrt(sum(x ** 2 for x in b))
            return dot / (mag_a * mag_b + 1e-9)

        sim_similar = cosine(v1, v2)
        sim_different = cosine(v1, v3)
        assert sim_similar > sim_different, (
            f"Similar texts should have higher cosine similarity "
            f"({sim_similar:.3f}) than dissimilar ({sim_different:.3f})"
        )

    def test_model_name_and_backend_populated(self, embed_engine: EmbeddingModel) -> None:
        resp = embed_engine.embed(EmbeddingRequest(texts=["Test"]))
        assert resp.model_name
        assert resp.backend
