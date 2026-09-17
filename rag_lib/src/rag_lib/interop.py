from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Collection, Iterable, Mapping

from llm_harness_core import (
    CapabilityDescriptor,
    CapabilityKind,
    OperationResult,
    RetrievedDocument,
    TraceEvent,
)


_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_RETRIEVAL_CHANNELS = frozenset({"dense", "bm25"})
_CHANNEL_DIAGNOSTICS = frozenset({"bm25_search_failed", "bm25_candidates_unmaterialized"})


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
        diagnostics.setdefault(
            "evidence_flows", [_doc_to_evidence_flow(doc) for doc in self.selected_results]
        )
        diagnostics.setdefault("selected_count", len(self.selected_results))
        return OperationResult.success(value, diagnostics=diagnostics)

    def to_serializable_dict(self) -> dict[str, Any]:
        result = self.to_operation_result()
        value = dict(result.value or {})
        value["diagnostics"] = dict(result.diagnostics)
        return value

    def to_identifier_projection(
        self,
        *,
        entry_id_by_source: Mapping[str, str],
        allowed_entry_ids: Collection[str],
        use_selected_results: bool = False,
    ) -> dict[str, Any]:
        """Return a fail-closed trace projection containing no source text or paths.

        This is a building block for evaluator traces, not the complete M3 trace
        schema. Callers must supply the frozen-corpus entry-id mapping and exact
        allowlist. Unresolved, path-like, or out-of-allowlist identifiers are
        rejected rather than copied into the projection.
        """

        allowed = frozenset(allowed_entry_ids)
        if not allowed:
            raise ValueError("allowed_entry_ids must not be empty")
        invalid_allowed = sorted(
            repr(entry_id)
            for entry_id in allowed
            if not isinstance(entry_id, str) or _SAFE_IDENTIFIER_RE.fullmatch(entry_id) is None
        )
        if invalid_allowed:
            raise ValueError(f"allowed_entry_ids contains unsafe identifiers: {invalid_allowed!r}")

        stage_events = [
            event for event in self.events if event.event_type == "retrieval_stage1_completed"
        ]
        if not stage_events:
            raise ValueError("retrieval trace has no Stage 1 channel execution evidence")
        dense_count = 0
        bm25_count = 0
        channel_diagnostics: set[str] = set()
        for event in stage_events:
            payload = dict(event.payload)
            for field_name in ("dense_count", "bm25_count"):
                value = payload.get(field_name)
                if type(value) is not int or value < 0:
                    raise ValueError(f"retrieval Stage 1 event has invalid {field_name}: {value!r}")
            dense_count += payload["dense_count"]
            bm25_count += payload["bm25_count"]
            warnings = payload.get("warnings", [])
            if not isinstance(warnings, list) or any(
                not isinstance(warning, str) for warning in warnings
            ):
                raise ValueError("retrieval Stage 1 event has invalid warnings")
            unknown_warnings = set(warnings) - _CHANNEL_DIAGNOSTICS
            if unknown_warnings:
                raise ValueError(
                    f"retrieval Stage 1 event has unsupported diagnostics: "
                    f"{sorted(unknown_warnings)!r}"
                )
            channel_diagnostics.update(warnings)

        channel_execution = {
            "dense": {
                "attempted": True,
                "status": "completed",
                "result_count": dense_count,
                "diagnostic_codes": [],
            },
            "bm25": {
                "attempted": True,
                "status": "degraded" if channel_diagnostics else "completed",
                "result_count": bm25_count,
                "diagnostic_codes": sorted(channel_diagnostics),
            },
        }

        documents = self.selected_results if use_selected_results else self.reranked_results
        if not documents and not use_selected_results:
            documents = self.fused_results

        retrieved: list[dict[str, Any]] = []
        for rank, doc in enumerate(documents, start=1):
            metadata = dict(doc.metadata)
            source_id = str(metadata.get("source_id") or doc.source)
            source_base = source_id.rsplit(":", 1)[0] if ":" in source_id else source_id
            entry_id = entry_id_by_source.get(source_id) or entry_id_by_source.get(source_base)
            if entry_id is None:
                raise ValueError(f"No corpus entry id mapped for retrieved chunk {doc.doc_id!r}")
            if _SAFE_IDENTIFIER_RE.fullmatch(entry_id) is None:
                raise ValueError(
                    f"Unsafe corpus entry id mapped for retrieved chunk {doc.doc_id!r}"
                )
            if entry_id not in allowed:
                raise ValueError(f"Corpus entry id is outside the allowed set: {entry_id!r}")
            if not isinstance(doc.doc_id, str) or _SAFE_IDENTIFIER_RE.fullmatch(doc.doc_id) is None:
                raise ValueError(f"Retrieved chunk has unsafe chunk id: {doc.doc_id!r}")
            if metadata.get("context_truncated"):
                raise ValueError(
                    f"Retrieved chunk {doc.doc_id!r} has truncated model-visible context"
                )
            chunk_digest = metadata.get("chunk_digest")
            if (
                not isinstance(chunk_digest, str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", chunk_digest) is None
            ):
                chunk_digest = "sha256:" + hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
            channels = metadata.get("retrieval_channels", ())
            if not isinstance(channels, (list, tuple)) or not channels:
                raise ValueError(
                    f"Retrieved chunk {doc.doc_id!r} has no retrieval channel metadata"
                )
            if any(not isinstance(channel, str) for channel in channels):
                raise ValueError(f"Retrieved chunk {doc.doc_id!r} has invalid retrieval channels")
            if len(channels) != len(set(channels)) or not set(channels) <= _RETRIEVAL_CHANNELS:
                raise ValueError(f"Retrieved chunk {doc.doc_id!r} has invalid retrieval channels")
            dense_rank = metadata.get("dense_rank")
            bm25_rank = metadata.get("bm25_rank")
            for channel, channel_rank in (("dense", dense_rank), ("bm25", bm25_rank)):
                if (channel in channels) != (type(channel_rank) is int and channel_rank >= 1):
                    raise ValueError(
                        f"Retrieved chunk {doc.doc_id!r} has inconsistent {channel} rank metadata"
                    )
            if not math.isfinite(doc.score):
                raise ValueError(f"Retrieved chunk {doc.doc_id!r} has a non-finite score")
            retrieved.append(
                {
                    "entry_id": entry_id,
                    "chunk_id": doc.doc_id,
                    "chunk_digest": chunk_digest,
                    "rank": rank,
                    "fused_score": format(doc.score, ".12g"),
                    "dense_rank": dense_rank,
                    "bm25_rank": bm25_rank,
                    "retrieval_channels": list(channels),
                }
            )

        return {
            "projection_schema_version": "2",
            "query_digest": "sha256:" + hashlib.sha256(self.query.encode("utf-8")).hexdigest(),
            "channel_execution": channel_execution,
            "retrieved": retrieved,
        }


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
        )
        + (("reranker",) if reranker is not None else ())
        + (("query_expansion",) if expander is not None else ()),
        input_types=("query", "collection", "augment_request"),
        output_types=("retrieved_document[]", "trace_event[]", "operation_result", "prompt"),
        metadata=metadata,
    )


def summarize_documents(documents: Iterable[RetrievedDocument]) -> list[dict[str, Any]]:
    return [_doc_to_dict(doc) for doc in documents]
