from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from llm_harness_core import (
    CapabilityDescriptor,
    CapabilityKind,
    OperationResult,
    RetrievedDocument,
    TraceEvent,
)


def _doc_provenance(doc: RetrievedDocument) -> dict[str, Any]:
    metadata = dict(doc.metadata)
    return {
        "doc_id": doc.doc_id,
        "source": doc.source,
        "title": doc.title,
        "stage": metadata.get("stage"),
        "rank": metadata.get("rank"),
        "query_variant": metadata.get("query_variant"),
        "doc_type": metadata.get("doc_type"),
    }


def _doc_transformations(doc: RetrievedDocument) -> tuple[str, ...]:
    metadata = dict(doc.metadata)
    stage = metadata.get("stage")
    transforms: list[str] = []
    if metadata.get("query_variant"):
        transforms.append("query_variant")
    if stage in {"dense", "bm25", "fusion_final", "reranked", "selected"}:
        transforms.append(stage)
    if stage == "selected":
        transforms.append("prompt_assembly")
    return tuple(transforms)


def _doc_to_evidence_flow(doc: RetrievedDocument) -> dict[str, Any]:
    metadata = dict(doc.metadata)
    return {
        "source": "rag",
        "before_text": doc.text,
        "after_text": doc.text,
        "stage": metadata.get("stage") or "retrieved",
        "score": doc.score,
        "provenance": _doc_provenance(doc),
        "transformations": list(_doc_transformations(doc)),
        "excluded": False,
        "exclusion_reason": None,
        "meta": metadata,
    }


def _doc_to_dict(doc: RetrievedDocument) -> dict[str, Any]:
    return {
        "text": doc.text,
        "source": doc.source,
        "doc_id": doc.doc_id,
        "score": doc.score,
        "title": doc.title,
        "metadata": dict(doc.metadata),
    }


def _event_to_dict(event: TraceEvent) -> dict[str, Any]:
    return {
        "event_type": event.event_type,
        "source_package": event.source_package,
        "source_component": event.source_component,
        "payload": dict(event.payload),
        "severity": event.severity,
        "message": event.message,
        "event_id": event.event_id,
        "span_id": event.span_id,
        "parent_span_id": event.parent_span_id,
        "ts": event.ts,
        "tags": list(event.tags),
    }


@dataclass(frozen=True)
class RetrievalTrace:
    query: str
    collection: str = "default"
    query_variants: tuple[str, ...] = ()
    dense_results: tuple[RetrievedDocument, ...] = ()
    bm25_results: tuple[RetrievedDocument, ...] = ()
    fused_results: tuple[RetrievedDocument, ...] = ()
    reranked_results: tuple[RetrievedDocument, ...] = ()
    selected_results: tuple[RetrievedDocument, ...] = ()
    assembled_prompt: str = ""
    events: tuple[TraceEvent, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_operation_result(self) -> OperationResult[dict[str, Any]]:
        value = {
            "query": self.query,
            "collection": self.collection,
            "query_variants": list(self.query_variants),
            "dense_results": [_doc_to_dict(doc) for doc in self.dense_results],
            "bm25_results": [_doc_to_dict(doc) for doc in self.bm25_results],
            "fused_results": [_doc_to_dict(doc) for doc in self.fused_results],
            "reranked_results": [_doc_to_dict(doc) for doc in self.reranked_results],
            "selected_results": [_doc_to_dict(doc) for doc in self.selected_results],
            "assembled_prompt": self.assembled_prompt,
            "events": [_event_to_dict(event) for event in self.events],
        }
        diagnostics = dict(self.diagnostics)
        diagnostics.setdefault("evidence_flows", [_doc_to_evidence_flow(doc) for doc in self.selected_results])
        diagnostics.setdefault("selected_count", len(self.selected_results))
        return OperationResult.success(value, diagnostics=diagnostics)

    def to_serializable_dict(self) -> dict[str, Any]:
        result = self.to_operation_result()
        value = dict(result.value or {})
        value["diagnostics"] = dict(result.diagnostics)
        return value


def describe_rag_pipeline(pipeline: Any) -> CapabilityDescriptor:
    retriever = getattr(pipeline, "_retriever", None)
    reranker = getattr(pipeline, "_reranker", None)
    expander = getattr(pipeline, "_expander", None)
    metadata = {
        "has_reranker": reranker is not None,
        "has_query_expander": expander is not None,
        "retriever": retriever.__class__.__name__ if retriever is not None else None,
    }
    return CapabilityDescriptor(
        kind=CapabilityKind.RAG_PIPELINE,
        provider="rag_lib",
        component=pipeline.__class__.__name__,
        version="0.1.0",
        summary="Inspectable retrieval-augmented pipeline with hybrid search and prompt assembly.",
        features=(
            "hybrid_retrieval",
            "retrieval_trace_events",
            "retrieved_documents",
            "prompt_assembly",
        ) + (("reranker",) if reranker is not None else ()) + (("query_expansion",) if expander is not None else ()),
        input_types=("query", "collection", "augment_request"),
        output_types=("retrieved_document[]", "trace_event[]", "operation_result", "prompt"),
        metadata=metadata,
    )


def summarize_documents(documents: Iterable[RetrievedDocument]) -> list[dict[str, Any]]:
    return [_doc_to_dict(doc) for doc in documents]
