"""Public API for Engram.

Engram is a local-first memory runtime for LLM applications. The main entry
point for most applications is :class:`ProjectMemory`.

Public surface:
- ProjectMemory: orchestrates the memory layers for one project
- TokenBudget / ContextResult: memory context data containers
- WorkingMemory / ColdStorage: lightweight explicit memory layers
- Lazy exports for episodic, semantic, filter, and neural components
"""

__version__ = "0.1.19"

from .project_memory import (
    ContextResult,
    ProjectMemory,
    TokenBudget,
    wrap_memory_block,
    assemble_prompt,
    truncate_to_tokens,
)
from .memory.cold_storage import ColdStorage
from .memory.working_memory import Message, WorkingMemory
from .memory.ingestion import IngestionDecision, IngestionPolicy, MemoryIngestor
from .memory.retrieval import RetrievalCandidate, RetrievalPolicy, UnifiedRetriever
from .memory.lifecycle import LifecycleConfig, LifecycleReport, MemoryLifecycleManager
from .interop import (
    describe_memory,
    prompt_result_to_interop_result,
    response_to_interop_result,
    trace_to_interop_events,
    trace_to_memory_records,
)
from .memory.types import Node, ProjectType, Relationship

import importlib

__all__ = [
    "ProjectMemory",
    "TokenBudget",
    "ContextResult",
    "wrap_memory_block",
    "assemble_prompt",
    "truncate_to_tokens",
    "WorkingMemory",
    "Message",
    "ColdStorage",
    "describe_memory",
    "trace_to_memory_records",
    "trace_to_interop_events",
    "prompt_result_to_interop_result",
    "response_to_interop_result",
    "MemoryIngestor",
    "IngestionDecision",
    "IngestionPolicy",
    "UnifiedRetriever",
    "RetrievalCandidate",
    "RetrievalPolicy",
    "MemoryLifecycleManager",
    "LifecycleConfig",
    "LifecycleReport",
    "ProjectType",
    "Node",
    "Relationship",
    "GraphExtractor",
    "ExtractionConfig",
    "ExtractionStats",
    "ForgettingPolicy",
    "ForgettingConfig",
    "EmbeddingCache",
    "EmbeddingService",
    "NeuralCoordinator",
    "MemoryContext",
    "SemanticLayerProtocol",
    "export_to_file",
    "export_stats",
    "ExportConfig",
    "__version__",
]

# ---------------------------------------------------------------------------
# Lazy attributes — loaded on first access, cached in globals().
#
# Format: name -> (module_path, attr_name)
# attr_name=None means return the module itself (for submodule access).
# To add a new lazy export, add one line here — no other changes needed.
# ---------------------------------------------------------------------------
_LAZY_ATTRS: dict = {
    # Submodule
    "engine":              ("engram.engine",                    None),
    # Episodic layer
    "EpisodicMemory":      ("engram.memory.episodic_memory",    "EpisodicMemory"),
    "Episode":             ("engram.memory.episodic_memory",    "Episode"),
    # Semantic layer
    "SemanticMemory":      ("engram.memory.semantic_memory",    "SemanticMemory"),
    "SemanticLayerProtocol": ("engram.memory.retrieval",        "SemanticLayerProtocol"),
    # Filters
    "SurpriseFilter":      ("engram.filters.surprise_filter",   "SurpriseFilter"),
    # Neural / RTRL
    "TITANSMemory":        ("engram.rtrl.core",                 "TITANSMemory"),
    "NeuralMemory":        ("engram.rtrl.neural_memory",        "NeuralMemory"),
    "NeuralMemoryConfig":  ("engram.rtrl.neural_memory",        "NeuralMemoryConfig"),
    # Graph extraction
    "GraphExtractor":      ("engram.memory.extraction",         "GraphExtractor"),
    "ExtractionConfig":    ("engram.memory.extraction",         "ExtractionConfig"),
    "ExtractionStats":     ("engram.memory.extraction",         "ExtractionStats"),
    # Forgetting
    "ForgettingPolicy":    ("engram.memory.forgetting",         "ForgettingPolicy"),
    "ForgettingConfig":    ("engram.memory.forgetting",         "ForgettingConfig"),
    # Embedding
    "EmbeddingCache":      ("engram.memory.embedding_cache",    "EmbeddingCache"),
    "EmbeddingService":    ("engram.memory.embedding_service",  "EmbeddingService"),
    # Coordination
    "NeuralCoordinator":   ("engram.memory.neural_coordinator", "NeuralCoordinator"),
    "MemoryContext":       ("engram.memory.memory_context",     "MemoryContext"),
    # Fine-tuning export
    "export_to_file":      ("engram.finetune.export",           "export_to_file"),
    "export_stats":        ("engram.finetune.export",           "export_stats"),
    "ExportConfig":        ("engram.finetune.export",           "ExportConfig"),
}


def __getattr__(name: str):
    if name not in _LAZY_ATTRS:
        raise AttributeError(f"module 'engram' has no attribute {name!r}")
    module_path, attr_name = _LAZY_ATTRS[name]
    module = importlib.import_module(module_path)
    obj = module if attr_name is None else getattr(module, attr_name)
    globals()[name] = obj
    return obj
