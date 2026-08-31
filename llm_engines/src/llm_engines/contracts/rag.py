"""
contracts/rag.py

RAGPipeline Protocol and associated types.
Canonical definition — llm_inspector imports from here, not the reverse.

ADR: Covered under llm-inspector Phase 1 decisions.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class Chunk(BaseModel):
    """A single retrieved chunk from a RAG pipeline."""

    content: str
    source_id: str
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGResult(BaseModel):
    """Full result from one RAG pipeline for one query."""

    pipeline_name: str
    query: str
    chunks: list[Chunk] = Field(default_factory=list)
    assembled_prompt: str = ""
    response: str = ""
    latency_ms: float = 0.0
    token_count: int = 0
    error: str | None = None


@runtime_checkable
class RAGPipeline(Protocol):
    """
    Any RAG system that can be compared by llm_inspector.

    Implementing this Protocol allows the system to be passed to
    RAGInspector.compare_pipelines() for side-by-side comparison.
    """

    def retrieve(self, query: str) -> list[Chunk]:
        """Retrieve relevant chunks for a query."""
        ...

    def assemble_prompt(self, query: str, chunks: list[Chunk]) -> str:
        """Build the final prompt from query + retrieved chunks."""
        ...

    def generate(self, prompt: str) -> str:
        """Generate a response from the assembled prompt."""
        ...
