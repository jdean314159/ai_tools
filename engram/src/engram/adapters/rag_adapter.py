"""
engram/adapters/rag_adapter.py

EngramRAGAdapter: expose ProjectMemory as a RetrievalTrace-compatible interface.

Lets the llm_inspector_ui compare Engram memory retrieval against rag_lib
RAG retrieval side-by-side, using the same RetrievalTrace contract.

Engram layer → RetrievalTrace slot mapping:
    semantic layer  →  dense_results   (fact/preference lookup; closest to dense search)
    episodic layer  →  bm25_results    (temporal/lexical retrieval; closest to BM25)
    cold layer      →  fused_results   (fallback long-term storage)
    all combined    →  selected_results (what the prompt actually receives)

No live model calls are made by this adapter; it wraps existing
ProjectMemory.get_context() which handles its own retrieval.

Usage:
    from engram.adapters.rag_adapter import EngramRAGAdapter
    from engram import ProjectMemory

    pm = ProjectMemory(project_id="myapp", ...)
    adapter = EngramRAGAdapter(pm)

    trace = adapter.inspect_query("What database should I use?")
    # trace.selected_results  — RetrievedDocument list
    # trace.events            — per-stage TraceEvents
    # trace.assembled_prompt  — ready-to-use prompt string
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SOURCE_PKG = "engram"
_COMPONENT = "EngramRAGAdapter"


def _text_from_semantic_row(row: Dict[str, Any]) -> str:
    """Extract text from a semantic memory dict (multiple possible key names)."""
    for key in ("canonical_content", "text", "content", "value"):
        val = row.get(key)
        if val and isinstance(val, str):
            return val
    return str(row)


def _score_from_row(row: Dict[str, Any]) -> float:
    """Extract a 0-1 relevance score from a memory row dict."""
    for key in ("match_score", "score", "relevance"):
        val = row.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return 0.0


class EngramRAGAdapter:
    """Wraps ProjectMemory as a rag_lib-compatible RetrievalTrace producer.

    The adapter does NOT manage the ProjectMemory lifecycle (open/close/
    session management).  Callers are responsible for that.

    Args:
        memory:         A ProjectMemory instance (or any object that exposes
                        ``get_context(query, max_tokens, ...)`` returning a
                        ContextResult with ``.episodic``, ``.semantic``,
                        ``.cold`` lists and per-layer token counts).
        max_tokens:     Token budget passed to get_context(). Default 2048.
        episodic_n:     Max episodic episodes to retrieve.
        semantic_n:     Max semantic entries to retrieve.
        cold_n:         Max cold-storage entries to retrieve (fallback).
    """

    def __init__(
        self,
        memory: Any,
        *,
        max_tokens: int = 2048,
        episodic_n: int = 5,
        semantic_n: int = 5,
        cold_n: int = 5,
    ) -> None:
        self._memory = memory
        self._max_tokens = max_tokens
        self._episodic_n = episodic_n
        self._semantic_n = semantic_n
        self._cold_n = cold_n

    # ------------------------------------------------------------------
    # Primary interface: mirrors rag_lib.RAGPipeline
    # ------------------------------------------------------------------

    def inspect_query(
        self,
        query: str,
        *,
        collection: str = "engram",
        max_context_tokens: Optional[int] = None,
        system_prompt: str = "",
    ) -> Any:
        """Run Engram memory retrieval and return a RetrievalTrace.

        The ``collection`` parameter is accepted for interface compatibility;
        Engram uses project_id for isolation, not collection names.

        Returns:
            rag_lib.interop.RetrievalTrace (imported lazily to avoid hard dep)
        """
        from llm_harness_core import RetrievedDocument, TraceEvent
        from rag_lib.interop import RetrievalTrace

        budget = max_context_tokens or self._max_tokens
        t0 = time.perf_counter()

        ctx = self._memory.get_context(
            query=query,
            max_tokens=budget,
            episodic_n=self._episodic_n,
            semantic_n=self._semantic_n,
            cold_n=self._cold_n,
        )

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        events: List[TraceEvent] = []

        # --- semantic layer → dense_results ---
        semantic_docs: List[RetrievedDocument] = []
        for i, row in enumerate(ctx.semantic):
            text = _text_from_semantic_row(row) if isinstance(row, dict) else str(row)
            score = _score_from_row(row) if isinstance(row, dict) else 0.0
            mem_type = row.get("type", "semantic") if isinstance(row, dict) else "semantic"
            semantic_docs.append(RetrievedDocument(
                text=text,
                source="engram:semantic",
                doc_id=f"sem_{i}",
                score=score,
                metadata={
                    "stage": "semantic",
                    "rank": i + 1,
                    "memory_type": mem_type,
                    "layer": "semantic",
                },
            ))

        events.append(TraceEvent(
            event_type="engram_semantic_retrieved",
            source_package=_SOURCE_PKG,
            source_component=_COMPONENT,
            payload={
                "count": len(semantic_docs),
                "token_count": ctx.semantic_tokens,
                "query": query,
            },
            severity="info",
            message=f"Engram semantic layer: {len(semantic_docs)} entries, "
                    f"{ctx.semantic_tokens} tokens.",
            tags=("engram", "retrieval", "semantic"),
        ))

        # --- episodic layer → bm25_results ---
        episodic_docs: List[RetrievedDocument] = []
        for i, ep in enumerate(ctx.episodic):
            text = getattr(ep, "text", str(ep))
            ep_id = getattr(ep, "id", f"ep_{i}")
            ts = getattr(ep, "timestamp", None)
            meta: Dict[str, Any] = {
                "stage": "episodic",
                "rank": i + 1,
                "layer": "episodic",
            }
            if ts is not None:
                meta["timestamp"] = ts
            episodic_docs.append(RetrievedDocument(
                text=text,
                source="engram:episodic",
                doc_id=str(ep_id),
                score=0.0,  # Engram scores episodic by recency/importance, not 0-1
                metadata=meta,
            ))

        events.append(TraceEvent(
            event_type="engram_episodic_retrieved",
            source_package=_SOURCE_PKG,
            source_component=_COMPONENT,
            payload={
                "count": len(episodic_docs),
                "token_count": ctx.episodic_tokens,
                "query": query,
            },
            severity="info",
            message=f"Engram episodic layer: {len(episodic_docs)} episodes, "
                    f"{ctx.episodic_tokens} tokens.",
            tags=("engram", "retrieval", "episodic"),
        ))

        # --- cold layer → fused_results ---
        cold_docs: List[RetrievedDocument] = []
        for i, row in enumerate(ctx.cold):
            text = _text_from_semantic_row(row) if isinstance(row, dict) else str(row)
            score = _score_from_row(row) if isinstance(row, dict) else 0.0
            cold_docs.append(RetrievedDocument(
                text=text,
                source="engram:cold",
                doc_id=f"cold_{i}",
                score=score,
                metadata={
                    "stage": "cold",
                    "rank": i + 1,
                    "layer": "cold",
                },
            ))

        if cold_docs:
            events.append(TraceEvent(
                event_type="engram_cold_retrieved",
                source_package=_SOURCE_PKG,
                source_component=_COMPONENT,
                payload={
                    "count": len(cold_docs),
                    "token_count": ctx.cold_tokens,
                    "query": query,
                },
                severity="info",
                message=f"Engram cold layer (fallback): {len(cold_docs)} entries.",
                tags=("engram", "retrieval", "cold"),
            ))

        # --- selected = all retrieved, ordered: semantic → episodic → cold ---
        all_docs: List[RetrievedDocument] = []
        for rank, doc in enumerate(semantic_docs + episodic_docs + cold_docs, start=1):
            all_docs.append(RetrievedDocument(
                text=doc.text,
                source=doc.source,
                doc_id=doc.doc_id,
                score=doc.score,
                metadata={**dict(doc.metadata), "stage": "selected", "combined_rank": rank},
            ))

        # --- assembled prompt ---
        prompt = self._build_prompt(query, all_docs, system_prompt=system_prompt)

        events.append(TraceEvent(
            event_type="engram_prompt_assembled",
            source_package=_SOURCE_PKG,
            source_component=_COMPONENT,
            payload={
                "total_retrieved": len(all_docs),
                "total_tokens": ctx.total_tokens,
                "elapsed_ms": elapsed_ms,
                "layers": {
                    "semantic": len(semantic_docs),
                    "episodic": len(episodic_docs),
                    "cold": len(cold_docs),
                },
            },
            severity="info",
            message=f"Engram retrieval complete: {len(all_docs)} items, "
                    f"{ctx.total_tokens} tokens, {elapsed_ms}ms.",
            tags=("engram", "retrieval", "prompt_assembly"),
        ))

        return RetrievalTrace(
            query=query,
            collection=collection,
            query_variants=(query,),
            dense_results=tuple(semantic_docs),   # semantic ≈ dense
            bm25_results=tuple(episodic_docs),    # episodic ≈ BM25/temporal
            fused_results=tuple(cold_docs),       # cold ≈ fallback
            reranked_results=(),                  # Engram reranks internally
            selected_results=tuple(all_docs),
            assembled_prompt=prompt,
            events=tuple(events),
            diagnostics={
                "query": query,
                "collection": collection,
                "semantic_count": len(semantic_docs),
                "episodic_count": len(episodic_docs),
                "cold_count": len(cold_docs),
                "selected_count": len(all_docs),
                "total_tokens": ctx.total_tokens,
                "token_budget": budget,
                "elapsed_ms": elapsed_ms,
                "source": "engram",
            },
        )

    def retrieve(self, query: str, *, collection: str = "engram") -> List[Any]:
        """Retrieve memories for query. Returns list of RetrievedDocument."""
        trace = self.inspect_query(query, collection=collection)
        return list(trace.selected_results)

    def assemble_prompt(
        self,
        query: str,
        chunks: List[Any],
        max_context_tokens: Optional[int] = None,
        system_prompt: str = "",
    ) -> str:
        """Build a prompt from query and previously-retrieved documents."""
        return self._build_prompt(query, chunks, system_prompt=system_prompt)

    def generate(self, prompt: str) -> str:
        """Not implemented — callers supply the LLM engine."""
        return ""

    def describe_component(self) -> Any:
        """Return a CapabilityDescriptor for this adapter."""
        from llm_harness_core import CapabilityDescriptor, CapabilityKind
        project_id = getattr(self._memory, "project_id", "unknown")
        return CapabilityDescriptor(
            kind=CapabilityKind.MEMORY,
            provider="engram",
            component=_COMPONENT,
            version="0.1.0",
            summary=(
                "Engram multi-layer memory exposed as a RetrievalTrace-compatible "
                "retrieval interface. Retrieves from semantic, episodic, and cold layers."
            ),
            features=(
                "semantic_retrieval",
                "episodic_retrieval",
                "cold_storage_fallback",
                "retrieval_trace_events",
                "multi_layer",
            ),
            input_types=("query", "augment_request"),
            output_types=("retrieved_document[]", "trace_event[]", "operation_result", "prompt"),
            metadata={
                "project_id": project_id,
                "max_tokens": self._max_tokens,
            },
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        query: str,
        docs: List[Any],
        *,
        system_prompt: str = "",
    ) -> str:
        """Assemble a plain-text prompt from retrieved memory docs."""
        parts: List[str] = []
        if system_prompt:
            parts.append(system_prompt)

        if docs:
            parts.append("## Retrieved memory context")
            for doc in docs:
                text = doc.text if hasattr(doc, "text") else str(doc)
                source = getattr(doc, "source", "")
                layer = dict(getattr(doc, "metadata", {})).get("layer", "")
                label = f"[{layer}]" if layer else ""
                parts.append(f"{label} {text}".strip())
            parts.append("")

        parts.append(f"## User\n{query}")
        return "\n\n".join(p for p in parts if p)
