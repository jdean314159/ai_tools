from __future__ import annotations
import pytest
import tempfile
from unittest.mock import MagicMock

from engram.embeddings.base import Embedder, EmbeddingResult, BatchEmbeddingResult


class MockEmbedder(Embedder):
    """Deterministic mock embedder. Hash-based 8-dim vectors. No Ollama required."""

    DIMENSION = 8

    @property
    def model_name(self) -> str:
        return "mock:test"

    @property
    def dimension(self) -> int:
        return self.DIMENSION

    def embed(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            text=text,
            embedding=self._text_to_vector(text),
            model=self.model_name,
            dimension=self.DIMENSION,
        )

    def embed_batch(self, texts: list) -> BatchEmbeddingResult:
        return BatchEmbeddingResult(
            texts=texts,
            embeddings=[self._text_to_vector(t) for t in texts],
            model=self.model_name,
            dimension=self.DIMENSION,
        )

    def _text_to_vector(self, text: str) -> list:
        import hashlib
        h = hashlib.md5(text.encode()).digest()
        return [(b - 128) / 128.0 for b in h[:self.DIMENSION]]


class MockLLMEngine:
    """Mock LLM engine returning preset responses."""

    def __init__(self, response_text: str = "[]"):
        self._response_text = response_text

    def generate(self, request):
        result = MagicMock()
        result.message.content = self._response_text
        return result


@pytest.fixture
def mock_embedder():
    return MockEmbedder()


@pytest.fixture
def mock_llm():
    return MockLLMEngine()


@pytest.fixture
def temp_memory(mock_embedder):
    """Full-featured memory with mock embedder (no Ollama needed)."""
    from engram import ProjectMemory
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = ProjectMemory(
            base_dir=tmpdir,
            project_id="test_project",
            session_id="session_1",
            embedder=mock_embedder,
            auto_pair_assistant=True,
            enable_semantic_graph=True,
        )
        yield mem
        mem.close()


@pytest.fixture
def temp_memory_no_embedder():
    """Text-only memory (backward compat)."""
    from engram import ProjectMemory
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = ProjectMemory(
            base_dir=tmpdir,
            project_id="test_project",
            session_id="session_1",
        )
        yield mem
        mem.close()
