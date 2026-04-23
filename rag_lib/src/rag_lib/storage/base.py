"""
rag_lib.storage.base

VectorStore Protocol and StoredChunk dataclass.
All storage backends implement VectorStore.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from llm_harness_core import RetrievedDocument


@dataclass
class StoredChunk:
    """A chunk as stored in and retrieved from the vector store.

    text:         The short text that was embedded (chunk.text).
    context_text: The expanded text sent to the LLM (chunk.context_text).
                  For sentence-window: surrounding sentences.
                  For hierarchical: parent section.
                  For fixed-size/semantic: same as text.
    score:        Cosine similarity [0, 1]. Higher is more relevant.
    chunk_id:     Deterministic ID: sha256(file_path:chunk_index:file_hash)[:16]
    source_id:    Original file path + chunk index, human-readable.
    doc_type:     Strategy selector (policy, spec, paper, thesis, etc.)
    metadata:     Strategy, page, section title, table flag, etc.
    """
    chunk_id: str
    text: str
    context_text: str
    score: float
    source_id: str
    doc_type: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_table(self) -> bool:
        return bool(self.metadata.get("is_table", False))

    @property
    def page(self) -> int | None:
        return self.metadata.get("page")

    @property
    def section(self) -> str | None:
        return self.metadata.get("section")

    def to_retrieved_document(
        self,
        *,
        text: str | None = None,
        stage: str | None = None,
        rank: int | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> RetrievedDocument:
        metadata = dict(self.metadata)
        metadata.setdefault("chunk_id", self.chunk_id)
        metadata.setdefault("doc_type", self.doc_type)
        metadata.setdefault("source_id", self.source_id)
        if stage is not None:
            metadata["stage"] = stage
        if rank is not None:
            metadata["rank"] = rank
        if extra_metadata:
            metadata.update(extra_metadata)
        return RetrievedDocument(
            text=text if text is not None else self.context_text,
            source=self.source_id,
            doc_id=self.chunk_id,
            score=self.score,
            title=metadata.get("title") or metadata.get("section"),
            metadata=metadata,
        )


@runtime_checkable
class VectorStore(Protocol):
    """Protocol for vector storage backends."""

    def add(
        self,
        chunks: list["TextChunk"],          # noqa: F821
        embeddings: list[list[float]],
        collection: str = "default",
    ) -> None:
        """Store chunks with their embeddings. Upserts on duplicate chunk_id."""
        ...

    def search(
        self,
        query_vector: list[float],
        n_results: int = 10,
        collection: str = "default",
    ) -> list[StoredChunk]:
        """Return up to n_results chunks by cosine similarity, score descending."""
        ...

    def delete_by_source(
        self,
        file_path: str,
        collection: str = "default",
    ) -> int:
        """Delete all chunks whose source_id starts with file_path. Returns count."""
        ...

    def list_collections(self) -> list[str]:
        """Return all collection names (without the collection_prefix)."""
        ...

    def delete_collection(self, collection: str) -> None:
        """Delete an entire collection."""
        ...

    def collection_metadata(self, collection: str) -> dict[str, Any]:
        """Return the metadata dict stored when the collection was created."""
        ...

    def count(self, collection: str = "default") -> int:
        """Return the number of chunks in a collection."""
        ...
