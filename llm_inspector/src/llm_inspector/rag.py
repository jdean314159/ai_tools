"""
llm_inspector/rag.py

RAGInspector v0.1 — side-by-side RAG pipeline comparison (console output).

Phase 1 scope (Week 7-8):
  - RAGInspector: query multiple pipelines, print comparison table
  - EngramRAGAdapter: expose Engram as a RAGPipeline
  - ChromaDBRAGAdapter: thin wrapper for bare ChromaDB collections

Phase 2 (deferred):
  - Web UI (React + FastAPI)
  - MemoryInspector, ModelComparator, PromptInspector, DocumentInspector
  - Automatic quality scoring

Usage:
    from llm_inspector.rag import RAGInspector, EngramRAGAdapter

    inspector = RAGInspector()
    inspector.add_pipeline("Engram", EngramRAGAdapter(memory))
    inspector.add_pipeline("ChromaDB", ChromaDBRAGAdapter(collection, engine))

    results = inspector.query_all("What is the project status?")
    inspector.print_comparison(results)
"""
from __future__ import annotations

import time
import logging
from typing import Any

from llm_engines.contracts import Chunk, RAGPipeline, RAGResult

try:
    from llm_inspector.core import EvidenceFlow
except Exception:  # pragma: no cover
    EvidenceFlow = None  # type: ignore

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RAGInspector
# ---------------------------------------------------------------------------

class RAGInspector:
    """
    Compare multiple RAG pipelines side-by-side on the same queries.

    All pipelines receive the same query. Results are printed to console.
    The inspector does not judge quality — it surfaces data for the developer.
    """

    def __init__(self) -> None:
        self._pipelines: list[tuple[str, RAGPipeline]] = []
        self._last_traces: dict[tuple[str, str], Any] = {}
        self._last_traces: dict[tuple[str, str], Any] = {}

    def add_pipeline(self, name: str, pipeline: RAGPipeline) -> None:
        """Register a RAG pipeline for comparison."""
        self._pipelines.append((name, pipeline))

    def query_all(self, query: str) -> list[RAGResult]:
        """
        Run query through all registered pipelines.

        Returns a list of RAGResult, one per pipeline. Errors are caught and
        stored in RAGResult.error so a single failure doesn't abort the run.
        """
        if not self._pipelines:
            raise ValueError("No pipelines registered. Call add_pipeline() first.")

        results = []
        for name, pipeline in self._pipelines:
            result = self._run_pipeline(name, query, pipeline)
            results.append(result)
        return results

    def compare_pipelines(
        self,
        queries: list[str],
        print_results: bool = True,
    ) -> dict[str, list[RAGResult]]:
        """
        Run a list of queries through all pipelines and optionally print results.

        Returns:
            Dict mapping query string → list of RAGResult (one per pipeline).
        """
        all_results: dict[str, list[RAGResult]] = {}
        for query in queries:
            results = self.query_all(query)
            all_results[query] = results
            if print_results:
                self.print_comparison(results)
                print()
        return all_results

    def _run_pipeline(self, name: str, query: str, pipeline: RAGPipeline) -> RAGResult:
        t0 = time.perf_counter()
        try:
            trace = None
            if hasattr(pipeline, "inspect_query"):
                try:
                    trace = pipeline.inspect_query(query)
                    self._last_traces[(name, query)] = trace
                except Exception as exc:
                    logger.warning("Pipeline '%s' inspect_query failed on query '%s': %s", name, query, exc)
            if trace is not None:
                chunks = [
                    Chunk(
                        content=doc.text,
                        source_id=doc.source or (doc.doc_id or ""),
                        score=float(doc.score or 0.0),
                        metadata=dict(doc.metadata),
                    )
                    for doc in getattr(trace, "selected_results", [])
                ]
                prompt = getattr(trace, "assembled_prompt", "")
            else:
                chunks = pipeline.retrieve(query)
                prompt = pipeline.assemble_prompt(query, chunks)
            response = pipeline.generate(prompt)
            latency_ms = (time.perf_counter() - t0) * 1000
            token_count = sum(
                len((c.content or "").split()) for c in chunks
            )
            return RAGResult(
                pipeline_name=name,
                query=query,
                chunks=chunks,
                assembled_prompt=prompt,
                response=response,
                latency_ms=round(latency_ms, 1),
                token_count=token_count,
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            logger.warning("Pipeline '%s' failed on query '%s': %s", name, query, e)
            return RAGResult(
                pipeline_name=name,
                query=query,
                latency_ms=round(latency_ms, 1),
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Console output
    # ------------------------------------------------------------------

    def _trace_for_result(self, result: RAGResult) -> Any | None:
        return self._last_traces.get((result.pipeline_name, result.query))

    def _evidence_flows_for_result(self, result: RAGResult) -> list[EvidenceFlow]:
        trace = self._trace_for_result(result)
        if trace is None or EvidenceFlow is None:
            return []
        diagnostics = {}
        if hasattr(trace, "to_operation_result"):
            try:
                diagnostics = dict(trace.to_operation_result().diagnostics)
            except Exception:
                diagnostics = {}
        flows = []
        for raw in diagnostics.get("evidence_flows", []):
            flows.append(EvidenceFlow(
                source=str(raw.get("source", "rag")),
                before_text=str(raw.get("before_text", "")),
                after_text=str(raw.get("after_text", raw.get("before_text", ""))),
                stage=str(raw.get("stage", "retrieved")),
                score=raw.get("score"),
                provenance=dict(raw.get("provenance", {})),
                transformations=tuple(raw.get("transformations", [])),
                excluded=bool(raw.get("excluded", False)),
                exclusion_reason=raw.get("exclusion_reason"),
                meta=dict(raw.get("meta", {})),
            ))
        return flows

    def print_comparison(self, results: list[RAGResult]) -> None:
        """Print a formatted side-by-side comparison to stdout."""
        if not results:
            print("No results to compare.")
            return

        query = results[0].query
        print(f"\n{'='*70}")
        print(f"Query: {query}")
        print(f"{'='*70}")

        for result in results:
            status = "ERROR" if result.error else "OK"
            print(f"\n[{result.pipeline_name}]  {status}  "
                  f"latency={result.latency_ms:.0f}ms  "
                  f"chunks={len(result.chunks)}  "
                  f"~tokens={result.token_count}")

            if result.error:
                print(f"  Error: {result.error}")
                continue

            for i, chunk in enumerate(result.chunks, 1):
                preview = chunk.content[:120].replace("\n", " ")
                print(f"  Chunk {i} (score={chunk.score:.3f}): {preview}")
                if len(chunk.content) > 120:
                    print(f"           ... [{len(chunk.content)} chars total]")

            flows = self._evidence_flows_for_result(result)
            if flows:
                print("  Evidence flow:")
                for flow in flows[:5]:
                    p = flow.provenance
                    xforms = ",".join(flow.transformations) if flow.transformations else "-"
                    print(
                        f"    - {flow.stage} score={flow.score if flow.score is not None else '-'} "
                        f"xforms={xforms} provenance={p}"
                    )

            if result.response:
                resp_preview = result.response[:200].replace("\n", " ")
                print(f"  Response: {resp_preview}")
                if len(result.response) > 200:
                    print(f"            ... [{len(result.response)} chars total]")

        print(f"\n{'-'*70}")
        # Summary line
        ok = [r for r in results if not r.error]
        if ok:
            fastest = min(ok, key=lambda r: r.latency_ms)
            most_chunks = max(ok, key=lambda r: len(r.chunks))
            print(f"Fastest: {fastest.pipeline_name} ({fastest.latency_ms:.0f}ms)")
            if len(ok) > 1:
                print(f"Most chunks: {most_chunks.pipeline_name} ({len(most_chunks.chunks)})")


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

class EngramRAGAdapter:
    """
    Expose an Engram ProjectMemory (or EngramMemory) as a RAGPipeline.

    Retrieves from episodic + semantic layers with conflict suppression.
    """

    def __init__(
        self,
        memory: Any,
        engine: Any | None = None,
        max_results: int = 5,
        suppress_superseded: bool = True,
    ) -> None:
        """
        Args:
            memory:             EngramMemory or ProjectMemory instance.
            engine:             ChatModel for generation. If None, uses
                                the engine configured on the memory object.
            max_results:        Max chunks to retrieve per query.
            suppress_superseded: Apply ADR-004 superseded episode suppression.
        """
        self.memory = memory
        self._engine = engine
        self.max_results = max_results
        self.suppress_superseded = suppress_superseded

    def retrieve(self, query: str) -> list[Chunk]:
        """Retrieve relevant chunks via Engram's unified retriever."""
        try:
            # Try the unified retriever path (ProjectMemory)
            if hasattr(self.memory, "retrieve"):
                raw_results = self.memory.retrieve(query=query, max_tokens=2048)
                chunks = []
                # Episodic results
                for ep in getattr(raw_results, "episodic", []):
                    text = getattr(ep, "text", "") or str(ep)
                    chunks.append(Chunk(
                        content=text,
                        source_id=str(getattr(ep, "id", "")),
                        score=float(getattr(ep, "importance", 0.5) or 0.5),
                        metadata={"layer": "episodic"},
                    ))
                # Semantic results
                for row in getattr(raw_results, "semantic", []):
                    text = str(row.get("content") or row.get("text") or row)
                    chunks.append(Chunk(
                        content=text,
                        source_id=str(row.get("id", "")),
                        score=float(row.get("match_score", 0.5)),
                        metadata={"layer": "semantic", "type": row.get("type", "")},
                    ))
                return chunks[:self.max_results]

            # Fallback: EngramMemory.query_episodic
            if hasattr(self.memory, "query_episodic"):
                episodes = self.memory.query_episodic(query, k=self.max_results)
                return [
                    Chunk(
                        content=getattr(ep, "text", str(ep)),
                        source_id=str(getattr(ep, "id", "")),
                        score=float(getattr(ep, "importance", 0.5) or 0.5),
                        metadata={"layer": "episodic"},
                    )
                    for ep in episodes
                ]
        except Exception as e:
            logger.warning("EngramRAGAdapter.retrieve failed: %s", e)
        return []

    def assemble_prompt(self, query: str, chunks: list[Chunk]) -> str:
        if not chunks:
            return f"Question: {query}\n\nAnswer:"
        context_parts = [f"[{i+1}] {c.content}" for i, c in enumerate(chunks)]
        context = "\n\n".join(context_parts)
        return (
            f"Use the following context to answer the question.\n\n"
            f"Context:\n{context}\n\n"
            f"Question: {query}\n\nAnswer:"
        )

    def generate(self, prompt: str) -> str:
        engine = self._engine
        if engine is None:
            # Try to get engine from the memory object
            engine = getattr(self.memory, "engine", None) or \
                     getattr(self.memory, "_engine", None)
        if engine is None:
            return "[No engine configured for generation]"

        try:
            from llm_engines.contracts import ChatMessage, GenerationRequest
            request = GenerationRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                max_tokens=512,
                temperature=0.7,
            )
            response = engine.generate(request)
            return response.message.content or ""
        except Exception as e:
            logger.warning("EngramRAGAdapter.generate failed: %s", e)
            return f"[Generation failed: {e}]"


class ChromaDBRAGAdapter:
    """
    Expose a raw ChromaDB collection as a RAGPipeline.

    Useful for comparing Engram's multi-layer retrieval against
    a simple single-collection vector search.
    """

    def __init__(
        self,
        collection: Any,
        engine: Any,
        n_results: int = 5,
        embed_fn: Any | None = None,
    ) -> None:
        """
        Args:
            collection: ChromaDB collection object.
            engine:     ChatModel for generation.
            n_results:  Number of results to retrieve.
            embed_fn:   Optional callable(texts) → embeddings. If None,
                        ChromaDB uses its own embedding function.
        """
        self.collection = collection
        self._engine = engine
        self.n_results = n_results
        self._embed_fn = embed_fn

    def retrieve(self, query: str) -> list[Chunk]:
        try:
            kwargs: dict[str, Any] = {"n_results": self.n_results}
            if self._embed_fn is not None:
                embeddings = self._embed_fn([query])
                kwargs["query_embeddings"] = embeddings
            else:
                kwargs["query_texts"] = [query]

            results = self.collection.query(**kwargs)
            chunks = []
            docs = (results.get("documents") or [[]])[0]
            ids = (results.get("ids") or [[]])[0]
            distances = (results.get("distances") or [[]])[0]
            metadatas = (results.get("metadatas") or [[]])[0]

            for doc, doc_id, dist, meta in zip(docs, ids, distances, metadatas):
                # ChromaDB returns L2 distance; convert to a [0,1] score
                score = max(0.0, 1.0 - float(dist))
                chunks.append(Chunk(
                    content=doc,
                    source_id=str(doc_id),
                    score=score,
                    metadata=meta or {},
                ))
            return chunks
        except Exception as e:
            logger.warning("ChromaDBRAGAdapter.retrieve failed: %s", e)
            return []

    def assemble_prompt(self, query: str, chunks: list[Chunk]) -> str:
        if not chunks:
            return f"Question: {query}\n\nAnswer:"
        context = "\n\n".join(f"[{i+1}] {c.content}" for i, c in enumerate(chunks))
        return (
            f"Context:\n{context}\n\n"
            f"Question: {query}\n\nAnswer:"
        )

    def generate(self, prompt: str) -> str:
        try:
            from llm_engines.contracts import ChatMessage, GenerationRequest
            request = GenerationRequest(
                messages=[ChatMessage(role="user", content=prompt)],
                max_tokens=512,
                temperature=0.7,
            )
            response = self._engine.generate(request)
            return response.message.content or ""
        except Exception as e:
            logger.warning("ChromaDBRAGAdapter.generate failed: %s", e)
            return f"[Generation failed: {e}]"
