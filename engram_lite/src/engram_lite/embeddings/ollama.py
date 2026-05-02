from __future__ import annotations
import requests
from typing import List
from .base import Embedder, EmbeddingResult, BatchEmbeddingResult


class OllamaEmbedder(Embedder):
    """Ollama embedding service. Uses nomic-embed-text by default (768-dim)."""

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: int = 30,
    ):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._dimension: int | None = None

    @property
    def model_name(self) -> str:
        return f"ollama:{self._model}"

    @property
    def dimension(self) -> int:
        if self._dimension is None:
            result = self.embed("dimension_probe")
            self._dimension = len(result.embedding)
        return self._dimension

    def embed(self, text: str) -> EmbeddingResult:
        response = requests.post(
            f"{self._base_url}/api/embeddings",
            json={"model": self._model, "prompt": text},
            timeout=self._timeout,
        )
        response.raise_for_status()
        embedding = response.json()["embedding"]
        return EmbeddingResult(
            text=text,
            embedding=embedding,
            model=self.model_name,
            dimension=len(embedding),
        )

    def embed_batch(self, texts: List[str]) -> BatchEmbeddingResult:
        embeddings = []
        failed = []
        dim = self.dimension
        for i, text in enumerate(texts):
            try:
                result = self.embed(text)
                embeddings.append(result.embedding)
            except Exception:
                embeddings.append([0.0] * dim)
                failed.append(i)
        return BatchEmbeddingResult(
            texts=texts,
            embeddings=embeddings,
            model=self.model_name,
            dimension=dim,
            failed_indices=failed or None,
        )
