from __future__ import annotations
from typing import List
from .base import Embedder, EmbeddingResult, BatchEmbeddingResult


class SentenceTransformersEmbedder(Embedder):
    """Offline sentence-transformers embedder. No Ollama required."""

    def __init__(self, model: str = "all-MiniLM-L6-v2", device: str = "cpu"):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed: pip install sentence-transformers"
            )
        self._model_name = model
        self._model = SentenceTransformer(model, device=device)
        self._dimension = self._model.get_sentence_embedding_dimension()

    @property
    def model_name(self) -> str:
        return f"sentence_transformers:{self._model_name}"

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> EmbeddingResult:
        embedding = self._model.encode(text).tolist()
        return EmbeddingResult(
            text=text, embedding=embedding,
            model=self.model_name, dimension=self._dimension,
        )

    def embed_batch(self, texts: List[str]) -> BatchEmbeddingResult:
        embeddings = self._model.encode(texts).tolist()
        return BatchEmbeddingResult(
            texts=texts, embeddings=embeddings,
            model=self.model_name, dimension=self._dimension,
        )
