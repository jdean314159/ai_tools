from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class EmbeddingResult:
    text: str
    embedding: List[float]
    model: str
    dimension: int


@dataclass
class BatchEmbeddingResult:
    texts: List[str]
    embeddings: List[List[float]]
    model: str
    dimension: int
    failed_indices: Optional[List[int]] = None


class Embedder(ABC):
    """Abstract embedder interface. Thread-safe, deterministic."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        pass

    @abstractmethod
    def embed(self, text: str) -> EmbeddingResult:
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> BatchEmbeddingResult:
        pass

    def embed_with_fallback(
        self, text: str, default: Optional[List[float]] = None
    ) -> EmbeddingResult:
        try:
            return self.embed(text)
        except Exception:
            if default is not None:
                return EmbeddingResult(
                    text=text,
                    embedding=default,
                    model=f"{self.model_name}_fallback",
                    dimension=len(default),
                )
            raise
