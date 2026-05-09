"""engram.embeddings — public embedding primitives."""
from .base import Embedder, EmbeddingResult, BatchEmbeddingResult
from .ollama import OllamaEmbedder
from .cache import EmbeddingCache, CachedEmbedder
from .factory import EmbeddingService

__all__ = [
    "Embedder", "EmbeddingResult", "BatchEmbeddingResult",
    "OllamaEmbedder", "EmbeddingService",
    "EmbeddingCache", "CachedEmbedder",
]

# Optional: sentence-transformers backend
from .sentence_transformers import SentenceTransformersEmbedder
__all__ = __all__ + ["SentenceTransformersEmbedder"]
"""engram.embeddings — public embedding primitives."""
from .base import Embedder, EmbeddingResult, BatchEmbeddingResult
from .ollama import OllamaEmbedder
from .cache import EmbeddingCache, CachedEmbedder
from .factory import EmbeddingService

__all__ = [
    "Embedder", "EmbeddingResult", "BatchEmbeddingResult",
    "OllamaEmbedder", "EmbeddingService",
    "EmbeddingCache", "CachedEmbedder",
]

# Optional: sentence-transformers backend
from .sentence_transformers import SentenceTransformersEmbedder
__all__ = __all__ + ["SentenceTransformersEmbedder"]
