from __future__ import annotations
from .base import Embedder
from .ollama import OllamaEmbedder


class EmbeddingService:
    """Factory for creating embedders."""

    @staticmethod
    def ollama(
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
        timeout: int = 30,
    ) -> Embedder:
        return OllamaEmbedder(model=model, base_url=base_url, timeout=timeout)

    @staticmethod
    def sentence_transformers(
        model: str = "all-MiniLM-L6-v2",
        device: str = "cpu",
    ) -> Embedder:
        try:
            from .sentence_transformers import SentenceTransformersEmbedder

            return SentenceTransformersEmbedder(model=model, device=device)
        except ImportError:
            raise ImportError(
                "sentence-transformers not installed: pip install engram[sentence-transformers]"
            )

    @staticmethod
    def from_config(config: dict) -> Embedder:
        backend = config.get("backend", "ollama")
        if backend == "ollama":
            return EmbeddingService.ollama(
                model=config.get("model", "nomic-embed-text"),
                base_url=config.get("base_url", "http://localhost:11434"),
                timeout=config.get("timeout", 30),
            )
        elif backend == "sentence_transformers":
            return EmbeddingService.sentence_transformers(
                model=config.get("model", "all-MiniLM-L6-v2"),
                device=config.get("device", "cpu"),
            )
        else:
            raise ValueError(f"Unknown embedder backend: {backend}")
