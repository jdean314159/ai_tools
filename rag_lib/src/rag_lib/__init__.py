"""rag_lib — Production RAG library."""
from .pipeline import RAGPipeline, IngestResult
from .interop import RetrievalTrace, describe_rag_pipeline
from .errors import (
    RagLibError, EmbedderError, StorageError,
    LoaderError, ChunkerError, RerankerError, EvalError,
)
__version__ = "0.1.0"
__all__ = [
    "RAGPipeline", "IngestResult",
    "RagLibError", "EmbedderError", "StorageError",
    "LoaderError", "ChunkerError", "RerankerError", "EvalError",
    "RetrievalTrace", "describe_rag_pipeline",
]
