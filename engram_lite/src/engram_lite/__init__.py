# Core — re-exported from engram
from engram.memory.augment import AugmentRequest, AugmentResult, PromptAugmenter
from .project_memory import ProjectMemory
from .interop import augment_result_to_interop_result, describe_memory, trace_to_memory_records
from .version import __version__

# Embeddings
from engram.embeddings import Embedder, EmbeddingResult, BatchEmbeddingResult
from engram.embeddings import OllamaEmbedder
from engram.embeddings import EmbeddingCache, CachedEmbedder
from engram.embeddings import EmbeddingService

# Storage — re-exported from engram
from engram.storage import ChromaDBStore, DimensionMismatchError, SchemaManager

# Semantic
from engram.semantic import SemanticGraph
from engram.semantic import SemanticExtractor, ExtractedFact, ExtractionResult
from engram.memory.semantic_forgetting import ForgettingConfig, ForgettingPolicy
from engram.memory.contradiction import detect_contradiction

# Telemetry — re-exported from engram
from engram.telemetry import Telemetry, TelemetryEvent, log_sink, json_file_sink

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
