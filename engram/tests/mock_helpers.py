"""Mock helpers for tests - no pytest dependency."""
from __future__ import annotations
from unittest.mock import MagicMock
from engram.embeddings.base import Embedder, EmbeddingResult, BatchEmbeddingResult


class MockEmbedder(Embedder):
    """Deterministic 8-dim embedder using text hash. No Ollama required."""
    DIMENSION = 8

    @property
    def model_name(self) -> str:
        return "mock:test"

    @property
    def dimension(self) -> int:
        return self.DIMENSION

    def embed(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            text=text, embedding=self._vec(text),
            model=self.model_name, dimension=self.DIMENSION,
        )

    def embed_batch(self, texts: list) -> BatchEmbeddingResult:
        return BatchEmbeddingResult(
            texts=texts, embeddings=[self._vec(t) for t in texts],
            model=self.model_name, dimension=self.DIMENSION,
        )

    def _vec(self, text: str) -> list:
        import hashlib
        h = hashlib.md5(text.encode()).digest()
        return [(b - 128) / 128.0 for b in h[:self.DIMENSION]]


class MockLLMEngine:
    def __init__(self, response_text: str = "[]"):
        self._response_text = response_text

    def generate(self, request):
        result = MagicMock()
        result.message.content = self._response_text
        return result
