# Core
from .contracts import AugmentRequest, AugmentResult, PromptAugmenter
from .project_memory import ProjectMemory
from .interop import augment_result_to_interop_result, describe_memory, trace_to_memory_records
from .version import __version__

# Embeddings
from .embeddings.base import Embedder, EmbeddingResult, BatchEmbeddingResult
from .embeddings.ollama import OllamaEmbedder
from .embeddings.cache import EmbeddingCache, CachedEmbedder
from .embeddings.factory import EmbeddingService

# Storage
from .storage.chromadb_store import ChromaDBStore, DimensionMismatchError
from .storage.schema import SchemaManager

# Semantic
from .semantic.graph import SemanticGraph
from .semantic.extractor import SemanticExtractor, ExtractedFact, ExtractionResult
from .semantic.forgetting import ForgettingConfig, ForgettingPolicy
from .semantic.contradiction import detect_contradiction

# Telemetry
from .telemetry import Telemetry, TelemetryEvent, log_sink, json_file_sink

__all__ = [
    "__version__",
    # Core
    "AugmentRequest", "AugmentResult", "PromptAugmenter",
    "ProjectMemory",
    "describe_memory", "trace_to_memory_records",
    "augment_result_to_interop_result",
    # Embeddings
    "Embedder", "EmbeddingResult", "BatchEmbeddingResult",
    "OllamaEmbedder", "EmbeddingService",
    "EmbeddingCache", "CachedEmbedder",
    # Storage
    "ChromaDBStore", "DimensionMismatchError", "SchemaManager",
    # Semantic
    "SemanticGraph",
    "SemanticExtractor", "ExtractedFact", "ExtractionResult",
    "ForgettingConfig", "ForgettingPolicy",
    "detect_contradiction",
    # Telemetry
    "Telemetry", "TelemetryEvent", "log_sink", "json_file_sink",
]
