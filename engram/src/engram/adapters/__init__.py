"""
engram/adapters/

Adapters connecting Engram to external systems.

EngramLLMAdapter: use any llm_engines backend for embedding/extraction.
EngramRAGAdapter: expose Engram as a RAGPipeline for llm_inspector comparison.
"""
from engram.adapters.llm_adapter import EngramLLMAdapter

__all__ = ["EngramLLMAdapter", "EngramRAGAdapter"]


def __getattr__(name: str):
    if name == "EngramRAGAdapter":
        from engram.adapters.rag_adapter import EngramRAGAdapter
        return EngramRAGAdapter
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")