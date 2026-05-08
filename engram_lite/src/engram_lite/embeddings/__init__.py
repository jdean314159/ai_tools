"""Compatibility re-exports from engram.embeddings."""

from engram.embeddings import (
    BatchEmbeddingResult,
    CachedEmbedder,
    Embedder,
    EmbeddingCache,
    EmbeddingResult,
    EmbeddingService,
    OllamaEmbedder,
)

try:
    from engram.embeddings import SentenceTransformersEmbedder
except ImportError:
    SentenceTransformersEmbedder = None

__all__ = [
    "Embedder",
    "EmbeddingResult",
    "BatchEmbeddingResult",
    "OllamaEmbedder",
    "EmbeddingService",
    "EmbeddingCache",
    "CachedEmbedder",
    "SentenceTransformersEmbedder",
]
