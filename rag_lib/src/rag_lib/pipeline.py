"""
rag_lib.pipeline

RAGPipeline: the single public entry point for rag_lib.
Implements llm_engines.contracts.rag.RAGPipeline Protocol.

Usage:
    from rag_lib import RAGPipeline

    pipeline = RAGPipeline()                    # uses ~/.rag_lib/rag_lib.yaml
    pipeline = RAGPipeline(config="my.yaml")    # explicit config

    result = pipeline.ingest("path/to/doc.pdf", doc_type="paper")
    chunks  = pipeline.retrieve("What is entropy-based anomaly detection?")
    prompt  = pipeline.assemble_prompt(query, chunks, max_context_tokens=3000)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import load_config, get
from .errors import RagLibError, LoaderError, StorageError
from .ingestion.loader import DocumentLoader, LoadedDocument
from .ingestion.chunker import Chunker
from .ingestion.embedder import OllamaEmbedder
from .ingestion.tables import TableProcessor
from .storage.chroma import ChromaStorage
from .retrieval.retriever import HybridRetriever
from .interop import RetrievalTrace, describe_rag_pipeline
from llm_harness_core import TraceEvent

if TYPE_CHECKING:
    from .eval.ragas_runner import EvalReport

logger = logging.getLogger(__name__)

# llm_engines.contracts types — imported lazily so rag_lib core can be
# imported without llm_engines installed (e.g. in unit tests with mocks)
try:
    from llm_engines.contracts import Chunk as ContractsChunk
except ImportError:
    ContractsChunk = None  # type: ignore


@dataclass
class IngestResult:
    """Result of a single document ingestion."""

    source_path: str
    doc_type: str
    chunks_stored: int
    tables_processed: int
    collection: str
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.chunks_stored > 0 and not self.errors


def infer_doc_type(path: "Path", text_sample: str = "") -> str:
    """Heuristic doc_type classifier based on filename, path, and content.

    Used by ingest_directory() when doc_type_map doesn't match.
    Returns a doc_type string suitable for the chunker routing table.

    Priority: filename patterns > parent directory name > content signals > fallback.
    """
    name = path.name.lower()
    parents = [p.lower() for p in path.parts[:-1]]

    # Filename patterns
    if any(k in name for k in ("thesis", "dissertation")):
        return "thesis"
    if any(k in name for k in ("readme", "guide", "howto", "tutorial", "faq")):
        return "guide"
    if any(k in name for k in ("policy", "procedure", "handbook")):
        return "policy"
    if any(k in name for k in ("runbook", "playbook", "sop")):
        return "runbook"
    if any(k in name for k in ("adr", "decision", "architecture")):
        return "adr"
    if any(k in name for k in ("spec", "specification", "requirements")):
        return "spec"
    if any(k in name for k in ("contract", "agreement", "terms")):
        return "contract"

    # Parent directory name signals
    dir_signals = {
        "anomaly": "paper",
        "detection": "paper",
        "insider": "paper",
        "netflow": "paper",
        "behavior": "paper",
        "behaviour": "paper",
        "intrusion": "paper",
        "rbac": "paper",
        "ai technique": "paper",
        "survey": "paper",
        "research": "paper",
        "paper": "paper",
        "policy": "policy",
        "hr": "hr",
        "human resource": "hr",
        "guide": "guide",
        "faq": "faq",
        "runbook": "runbook",
        "spec": "spec",
        "adr": "adr",
        "contract": "contract",
    }
    for parent in parents:
        for signal, dtype in dir_signals.items():
            if signal in parent:
                return dtype

    # Content signals (first 500 words)
    if text_sample:
        sample = text_sample[:2000].lower()
        if "abstract" in sample and "references" in sample:
            return "paper"
        if "table of contents" in sample or "chapter 1" in sample:
            return "thesis"
        if "whereas" in sample or "party" in sample or "agreement" in sample:
            return "contract"
        if "step 1" in sample or "prerequisite" in sample:
            return "runbook"

    return "unknown"


class RAGPipeline:
    """Production RAG pipeline with document-type-aware chunking and hybrid retrieval.

    Implements the llm_engines.contracts.rag.RAGPipeline Protocol:
        retrieve(query) → list[Chunk]
        assemble_prompt(query, chunks) → str
        generate(prompt) → str  (returns "" by default; callers provide engine)

    Args:
        config: Path to YAML config, dict, or None (loads ~/.rag_lib/rag_lib.yaml).
    """

    def __init__(self, config: str | Path | dict | None = None) -> None:
        if isinstance(config, dict):
            self._config = config
        else:
            self._config = load_config(config)

        self._setup_components()

    def describe_component(self):
        return describe_rag_pipeline(self)

    def inspect_query(
        self,
        query: str,
        *,
        collection: str = "default",
        max_context_tokens: int | None = None,
        system_prompt: str = "",
    ) -> RetrievalTrace:
        query_variants = [query]
        if self._expander is not None:
            try:
                expanded = [
                    q for q in self._expander.expand(query) if isinstance(q, str) and q.strip()
                ]
                if expanded:
                    query_variants = expanded
            except Exception as exc:
                logger.warning("Query expansion failed, using original query: %s", exc)

        dense_docs: list[Any] = []
        bm25_docs: list[Any] = []
        merged_map: dict[str, Any] = {}
        events: list[TraceEvent] = []
        retrieval_warnings: list[str] = []

        if len(query_variants) > 1:
            events.append(
                TraceEvent(
                    event_type="query_expanded",
                    source_package="rag_lib",
                    source_component=self._expander.__class__.__name__
                    if self._expander is not None
                    else "RAGPipeline",
                    payload={
                        "query_variants": list(query_variants),
                        "variant_count": len(query_variants),
                    },
                    severity="info",
                    message="Expanded retrieval query into variants.",
                    tags=("rag", "retrieval", "query_expansion"),
                )
            )

        for idx, q_variant in enumerate(query_variants, start=1):
            details = self._retriever.retrieve_with_details(q_variant, collection=collection)
            dense_results = details.get("dense_results", [])
            bm25_results = details.get("bm25_results", [])
            fused_results = details.get("fused_results", [])
            stage_warnings = [str(warning) for warning in details.get("warnings", [])]
            retrieval_warnings.extend(stage_warnings)
            dense_docs.extend(
                [
                    chunk.to_retrieved_document(
                        stage="dense", rank=rank, extra_metadata={"query_variant": q_variant}
                    )
                    for rank, chunk in enumerate(dense_results, start=1)
                ]
            )
            bm25_docs.extend(
                [
                    chunk.to_retrieved_document(
                        stage="bm25", rank=rank, extra_metadata={"query_variant": q_variant}
                    )
                    for rank, chunk in enumerate(bm25_results, start=1)
                ]
            )
            events.append(
                TraceEvent(
                    event_type="retrieval_stage1_completed",
                    source_package="rag_lib",
                    source_component="HybridRetriever",
                    payload={
                        "query_variant": q_variant,
                        "variant_index": idx,
                        "warnings": stage_warnings,
                        **dict(details.get("diagnostics", {})),
                    },
                    severity="warning" if stage_warnings else "info",
                    message=(
                        "Completed Stage 1 hybrid retrieval with warnings."
                        if stage_warnings
                        else "Completed Stage 1 hybrid retrieval."
                    ),
                    tags=("rag", "retrieval", "stage1"),
                )
            )
            for chunk in fused_results:
                existing = merged_map.get(chunk.chunk_id)
                if existing is None or chunk.score > existing.score:
                    merged_map[chunk.chunk_id] = chunk

        n_candidates = self._config.get("retriever", {}).get("n_candidates", 50)
        stage1_results = sorted(merged_map.values(), key=lambda c: c.score, reverse=True)[
            :n_candidates
        ]
        reranked_results = stage1_results
        if self._reranker is not None and stage1_results:
            n_results = self._config.get("retriever", {}).get("n_results", 5)
            try:
                reranked_results = self._reranker.rerank(query, stage1_results, k=n_results)
                events.append(
                    TraceEvent(
                        event_type="retrieval_reranked",
                        source_package="rag_lib",
                        source_component=self._reranker.__class__.__name__,
                        payload={
                            "input_count": len(stage1_results),
                            "output_count": len(reranked_results),
                            "top_chunk_ids": [chunk.chunk_id for chunk in reranked_results],
                        },
                        severity="info",
                        message="Applied cross-encoder reranking.",
                        tags=("rag", "retrieval", "rerank"),
                    )
                )
            except Exception as exc:
                logger.warning("Reranker failed, using Stage 1 results: %s", exc)
                events.append(
                    TraceEvent(
                        event_type="retrieval_rerank_failed",
                        source_package="rag_lib",
                        source_component=self._reranker.__class__.__name__,
                        payload={"error": str(exc), "input_count": len(stage1_results)},
                        severity="warning",
                        message="Reranker failed; Stage 1 results retained.",
                        tags=("rag", "retrieval", "rerank"),
                    )
                )

        prompt, selected_chunks, prompt_diag = self._retriever.assemble_prompt_with_selection(
            query=query,
            chunks=reranked_results,
            max_context_tokens=max_context_tokens,
            system_prompt=system_prompt,
        )
        events.append(
            TraceEvent(
                event_type="retrieval_prompt_assembled",
                source_package="rag_lib",
                source_component="HybridRetriever",
                payload={
                    "selected_chunk_ids": [chunk.chunk_id for chunk in selected_chunks],
                    **dict(prompt_diag),
                },
                severity="info",
                message="Assembled prompt from retrieved context.",
                tags=("rag", "retrieval", "prompt_assembly"),
            )
        )

        return RetrievalTrace(
            query=query,
            collection=collection,
            query_variants=tuple(query_variants),
            dense_results=tuple(dense_docs),
            bm25_results=tuple(bm25_docs),
            fused_results=tuple(
                chunk.to_retrieved_document(stage="fusion_final", rank=rank)
                for rank, chunk in enumerate(stage1_results, start=1)
            ),
            reranked_results=tuple(
                chunk.to_retrieved_document(stage="reranked", rank=rank)
                for rank, chunk in enumerate(reranked_results, start=1)
            ),
            selected_results=tuple(
                chunk.to_retrieved_document(stage="selected", rank=rank)
                for rank, chunk in enumerate(selected_chunks, start=1)
            ),
            assembled_prompt=prompt,
            events=tuple(events),
            diagnostics={
                "query": query,
                "collection": collection,
                "query_variant_count": len(query_variants),
                "candidate_count": len(stage1_results),
                "reranked_count": len(reranked_results),
                "selected_count": len(selected_chunks),
                "max_context_tokens": max_context_tokens,
                "system_prompt_present": bool(system_prompt.strip()),
                "warnings": retrieval_warnings,
            },
        )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest(
        self,
        path: str | Path,
        *,
        doc_type: str = "unknown",
        collection: str = "default",
    ) -> IngestResult:
        """Ingest a single document into the vector store.

        D14: Re-ingesting a modified file deletes old chunks first.
        Tables are extracted and converted to NL sentences before chunking.
        """
        path = Path(path)
        errors: list[str] = []

        # Load document
        try:
            doc: LoadedDocument = self._loader.load(path, doc_type=doc_type)
        except LoaderError as exc:
            logger.warning("Ingest failed for %s: %s", path.name, exc)
            return IngestResult(
                source_path=str(path),
                doc_type=doc_type,
                chunks_stored=0,
                tables_processed=0,
                collection=collection,
                errors=[str(exc)],
            )

        # D14: delete existing chunks for this file before re-ingesting
        deleted = self._store.delete_by_source(str(path), collection=collection)
        if deleted:
            logger.debug("Re-ingest: deleted %d old chunks from '%s'", deleted, path.name)

        # Process tables into NL sentences
        table_chunks, table_errors = self._process_tables(doc)
        errors.extend(table_errors)

        # Chunk the prose
        try:
            prose_chunks = self._chunker.chunk(doc)
        except RagLibError as exc:
            logger.warning("Chunking failed for %s: %s", path.name, exc)
            return IngestResult(
                source_path=str(path),
                doc_type=doc_type,
                chunks_stored=0,
                tables_processed=len(table_chunks),
                collection=collection,
                errors=[str(exc)],
            )

        all_chunks = prose_chunks + table_chunks

        # Contextual enrichment — sets embed_text on each chunk (opt-in)
        if self._enricher is not None:
            doc_intro = doc.text[: self._enricher._max_context_chars]
            doc_title = Path(path).name
            self._enricher.enrich(
                all_chunks,
                doc_title=doc_title,
                doc_type=doc_type,
                doc_intro=doc_intro,
                file_hash=doc.file_hash,
            )

        # Embed and store
        chunks_stored = self._embed_and_store(all_chunks, doc.file_hash, collection)

        # Update BM25 index (D12: rebuild after every ingest)
        self._update_bm25(collection)

        result = IngestResult(
            source_path=str(path),
            doc_type=doc_type,
            chunks_stored=chunks_stored,
            tables_processed=len(table_chunks),
            collection=collection,
            errors=errors,
        )
        logger.info(
            "Ingested '%s': %d chunks (%d from tables), collection='%s'",
            path.name,
            chunks_stored,
            len(table_chunks),
            collection,
        )
        return result

    def ingest_directory(
        self,
        directory: str | Path,
        *,
        doc_type_map: dict[str, str] | None = None,
        default_doc_type: str = "unknown",
        collection: str = "default",
        recursive: bool = True,
    ) -> list[IngestResult]:
        """Ingest all supported files from a directory.

        D15: Load all documents before querying — keep embed model warm.
        D16: Writes are serialized (threading.Lock in ChromaStorage).

        Args:
            directory:       Root directory.
            doc_type_map:    Maps filename patterns or subdirectory names to doc_types.
                             E.g. {"Anomaly Detection": "paper", "thesis*.pdf": "thesis"}
            default_doc_type: Used when no pattern matches.
            collection:      Target ChromaDB collection.
            recursive:       Walk subdirectories.
        """
        # When no doc_type_map or fallback needed, use heuristic classifier
        effective_default = default_doc_type
        docs = self._loader.load_directory(
            directory,
            doc_type_map=doc_type_map,
            default_doc_type=effective_default,
            recursive=recursive,
        )

        # Apply heuristic to docs that still have "unknown" doc_type
        for doc in docs:
            if doc.doc_type == "unknown" or doc.doc_type == effective_default:
                inferred = infer_doc_type(
                    Path(doc.source_path),
                    text_sample=doc.text[:2000],
                )
                if inferred != "unknown":
                    doc.doc_type = inferred

        results: list[IngestResult] = []
        for doc in docs:
            # D14: delete old chunks for each file
            deleted = self._store.delete_by_source(doc.source_path, collection=collection)
            if deleted:
                logger.debug("Re-ingest: deleted %d old chunks from '%s'", deleted, doc.source_path)

            table_chunks, table_errors = self._process_tables(doc)

            try:
                prose_chunks = self._chunker.chunk(doc)
            except RagLibError as exc:
                results.append(
                    IngestResult(
                        source_path=doc.source_path,
                        doc_type=doc.doc_type,
                        chunks_stored=0,
                        tables_processed=0,
                        collection=collection,
                        errors=[str(exc)],
                    )
                )
                continue

            all_chunks = prose_chunks + table_chunks

            # Contextual enrichment (opt-in)
            if self._enricher is not None:
                doc_intro = doc.text[: self._enricher._max_context_chars]
                self._enricher.enrich(
                    all_chunks,
                    doc_title=Path(doc.source_path).name,
                    doc_type=doc.doc_type,
                    doc_intro=doc_intro,
                    file_hash=doc.file_hash,
                )
            chunks_stored = self._embed_and_store(all_chunks, doc.file_hash, collection)

            results.append(
                IngestResult(
                    source_path=doc.source_path,
                    doc_type=doc.doc_type,
                    chunks_stored=chunks_stored,
                    tables_processed=len(table_chunks),
                    collection=collection,
                    errors=table_errors,
                )
            )

        # Rebuild BM25 once after the full directory ingest (D12)
        self._update_bm25(collection)

        total_chunks = sum(r.chunks_stored for r in results)
        logger.info(
            "ingest_directory: %d files, %d total chunks, collection='%s'",
            len(results),
            total_chunks,
            collection,
        )
        return results

    # ------------------------------------------------------------------
    # Retrieval (RAGPipeline Protocol)
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        *,
        collection: str = "default",
    ) -> list[Any]:  # list[contracts.Chunk] if available, else list[StoredChunk]
        """Retrieve relevant chunks for a query.

        Stage 1: Hybrid BM25 + dense retrieval (50 candidates).
        Stage 2: CrossEncoder reranking (if enabled).
        Returns list[llm_engines.contracts.Chunk] if llm_engines is installed,
        otherwise list[StoredChunk]. Both have .content, .source_id, .score fields.
        """
        trace = self.inspect_query(
            query,
            collection=collection,
            max_context_tokens=self._config.get("retriever", {}).get("max_context_tokens", 3000),
        )

        if ContractsChunk is not None:
            return [
                ContractsChunk(
                    content=doc.text,
                    source_id=doc.source,
                    score=doc.score or 0.0,
                    metadata=dict(doc.metadata),
                )
                for doc in (trace.reranked_results or trace.fused_results)
            ]

        stored = self._retriever.retrieve(query, collection=collection)
        if self._reranker is not None and stored:
            n_results = self._config.get("retriever", {}).get("n_results", 5)
            try:
                stored = self._reranker.rerank(query, stored, k=n_results)
            except Exception as exc:
                logger.warning("Reranker failed, using Stage 1 results: %s", exc)
        return stored

    def assemble_prompt(
        self,
        query: str,
        chunks: list[Any],
        max_context_tokens: int | None = None,
        system_prompt: str = "",
    ) -> str:
        """Build the LLM prompt from query and retrieved chunks.

        D8: max_context_tokens should match your model's context window
            minus expected output tokens. Logs a warning if not provided.
        """
        # Convert contracts.Chunk to StoredChunk if needed
        from .storage.base import StoredChunk

        stored_chunks: list[StoredChunk] = []
        for c in chunks:
            if isinstance(c, StoredChunk):
                stored_chunks.append(c)
            else:
                # contracts.Chunk or similar — adapt
                stored_chunks.append(
                    StoredChunk(
                        chunk_id=c.metadata.get("chunk_id", "") if hasattr(c, "metadata") else "",
                        text=c.content,
                        context_text=c.content,
                        score=c.score if hasattr(c, "score") else 0.0,
                        source_id=c.source_id if hasattr(c, "source_id") else "",
                        doc_type=c.metadata.get("doc_type", "") if hasattr(c, "metadata") else "",
                    )
                )

        return self._retriever.assemble_prompt(
            query=query,
            chunks=stored_chunks,
            max_context_tokens=max_context_tokens,
            system_prompt=system_prompt,
        )

    def generate(self, prompt: str) -> str:
        """Generate a response. Returns empty string by default.

        rag_lib is retrieval infrastructure. Callers provide the LLM engine
        via llm_engines. Override this method or use the engine directly.
        """
        return ""

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------

    def evaluate(
        self,
        test_queries: list[dict],
        *,
        judge_llm: Any,
        collection: str = "default",
        max_context_tokens: int | None = None,
        generation_llm: Any = None,
        generate_answers: bool = True,
        n_runs: int | None = None,
    ) -> EvalReport:
        """Run RAGAS evaluation against a ground-truth query set.

        Args:
            test_queries:   List of dicts with 'question' and 'ground_truths'.
                            Load with: from rag_lib.eval.ragas_runner import load_ground_truth
            judge_llm:      Required. LangchainLLMWrapper around a judge model.
                            Must differ from and be stronger than the generator.
            collection:     Collection to retrieve from.
            max_context_tokens: Token budget. Uses config default if None.
            generation_llm: LLM for generating answers (faithfulness + relevancy).
                            If None and generate_answers=True, pipeline.generate() used.
            generate_answers: If False, only retrieval metrics are measured.
            n_runs:         Override config eval.n_eval_runs.

        Returns:
            EvalReport with median scores across n_runs.
        """
        from .eval.ragas_runner import run_eval

        effective_n_runs = n_runs or get(self._config, "eval", "n_eval_runs", default=3)
        thresholds = {
            "context_recall": get(self._config, "eval", "context_recall_threshold", default=0.85),
            "context_precision": get(
                self._config, "eval", "context_precision_threshold", default=0.80
            ),
            "faithfulness": get(self._config, "eval", "faithfulness_threshold", default=0.88),
            "answer_relevancy": get(
                self._config, "eval", "answer_relevancy_threshold", default=0.80
            ),
        }
        return run_eval(
            pipeline=self,
            test_queries=test_queries,
            judge_llm=judge_llm,
            collection=collection,
            max_context_tokens=max_context_tokens,
            n_runs=effective_n_runs,
            generate_answers=generate_answers,
            generation_llm=generation_llm,
            thresholds=thresholds,
        )

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def delete_collection(self, collection: str) -> None:
        """Delete a collection and its BM25 index."""
        self._store.delete_collection(collection)
        for cache_path in (
            self._bm25_path / f"{collection}.json",
            self._bm25_path / f"{collection}.pkl",
        ):
            if cache_path.exists():
                cache_path.unlink()
        logger.info("Deleted collection '%s'", collection)

    def list_collections(self) -> list[str]:
        return self._store.list_collections()

    def collection_info(self, collection: str = "default") -> dict[str, Any]:
        return {
            "chunk_count": self._store.count(collection),
            "metadata": self._store.collection_metadata(collection),
        }

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_components(self) -> None:
        embedder_cfg = self._config.get("embedder", {})
        storage_cfg = self._config.get("storage", {})
        retriever_cfg = self._config.get("retriever", {})
        chunker_cfg = self._config.get("chunker", {})

        self._embed_model = embedder_cfg.get("model", "nomic-embed-text-v2-moe")
        self._bm25_path = Path(storage_cfg.get("bm25_path", "~/.rag_lib/bm25")).expanduser()

        self._embedder = OllamaEmbedder(
            host=embedder_cfg.get("host", "http://localhost:11434"),
            model=self._embed_model,
            timeout=embedder_cfg.get("timeout", 120),
            batch_size=embedder_cfg.get("batch_size", 32),
            keep_alive=embedder_cfg.get("keep_alive", 600),
            max_embed_tokens=chunker_cfg.get("max_embed_tokens", 1800),
        )

        self._store = ChromaStorage(
            path=storage_cfg.get("path", "~/.rag_lib/chroma"),
            collection_prefix=storage_cfg.get("collection_prefix", "rag_"),
            embed_model=self._embed_model,
        )

        self._loader = DocumentLoader(
            config=self._config,
            min_readable_words=self._config.get("loader", {}).get("min_readable_words", 50),
            ocr_word_threshold=self._config.get("loader", {}).get("ocr_word_threshold", 50),
        )

        self._chunker = Chunker(
            config=self._config,
            embedder=self._embedder,
            max_embed_tokens=chunker_cfg.get("max_embed_tokens", 1800),
        )

        self._table_processor = TableProcessor(
            config=self._config.get("tables", {}),
        )

        self._retriever = HybridRetriever(
            store=self._store,
            embedder=self._embedder,
            bm25_path=self._bm25_path,
            n_candidates=retriever_cfg.get("n_candidates", 50),
            n_results=retriever_cfg.get("n_results", 5),
            bm25_weight=retriever_cfg.get("bm25_weight", 0.4),
            max_context_tokens=retriever_cfg.get("max_context_tokens", 3000),
        )

        # Reranker — off by default (D10)
        reranker_cfg = self._config.get("reranker", {})
        self._reranker = None
        if reranker_cfg.get("enabled", False):
            from .retrieval.reranker import CrossEncoderReranker

            self._reranker = CrossEncoderReranker(
                model=reranker_cfg.get("model", "cross-encoder/ms-marco-MiniLM-L-6-v2"),
                device=reranker_cfg.get("device", "auto"),
            )
            logger.info("CrossEncoder reranker enabled.")

        # Query expander — off by default (D19)
        expander_cfg = self._config.get("expander", {})
        self._expander = None
        if expander_cfg.get("enabled", False):
            from .retrieval.expander import QueryExpander

            self._expander = QueryExpander(
                host=embedder_cfg.get("host", "http://localhost:11434"),
                model=expander_cfg.get("model", "qwen3:8b"),
                cache_size=expander_cfg.get("cache_size", 256),
            )
            logger.info("Query expander enabled (model=%s).", expander_cfg.get("model", "qwen3:8b"))

        # Contextual enricher — off by default
        enricher_cfg = self._config.get("enricher", {})
        self._enricher = None
        if enricher_cfg.get("enabled", False):
            from .ingestion.enricher import ContextualEnricher

            self._enricher = ContextualEnricher(
                provider=enricher_cfg.get("provider", "ollama"),
                model=enricher_cfg.get("model", "qwen3:8b"),
                host=enricher_cfg.get("host", embedder_cfg.get("host", "http://localhost:11434")),
                api_key_env=enricher_cfg.get("api_key_env", "ANTHROPIC_API_KEY"),
                timeout=enricher_cfg.get("timeout", 30),
                keep_alive=enricher_cfg.get("keep_alive", 60),
                max_context_chars=enricher_cfg.get("max_context_chars", 1000),
                batch_size=enricher_cfg.get("batch_size", 1),
                cache=enricher_cfg.get("cache", True),
                max_embed_tokens=chunker_cfg.get("max_embed_tokens", 1800),
            )
            logger.info(
                "Contextual enricher enabled (provider=%s, model=%s).",
                enricher_cfg.get("provider", "ollama"),
                enricher_cfg.get("model", "qwen3:8b"),
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _process_tables(
        self,
        doc: LoadedDocument,
    ) -> tuple[list[Any], list[str]]:
        """Convert table data to TextChunks via NL sentence reconstruction."""
        from .ingestion.chunker import TextChunk

        chunks: list[TextChunk] = []
        errors: list[str] = []

        for i, table in enumerate(doc.tables):
            try:
                sentences = self._table_processor.process(table)
                if not sentences:
                    continue
                table_text = " ".join(sentences)
                idx = f"table_{i}"
                chunks.append(
                    TextChunk(
                        text=table_text,
                        context_text=table_text,
                        source_id=f"{doc.source_path}:{idx}",
                        doc_type=doc.doc_type,
                        chunk_index=0,
                        metadata={
                            "strategy": "table",
                            "is_table": True,
                            "table_index": i,
                            "file_hash": doc.file_hash,
                        },
                    )
                )
            except Exception as exc:
                errors.append(f"Table {i} in {Path(doc.source_path).name}: {exc}")

        return chunks, errors

    def _embed_and_store(
        self,
        chunks: list[Any],
        file_hash: str,
        collection: str,
    ) -> int:
        """Embed chunks and store in ChromaDB. Returns count stored."""
        if not chunks:
            return 0

        # Annotate file_hash for content-addressed IDs
        for chunk in chunks:
            chunk.metadata["file_hash"] = file_hash

        # Use embed_text (contextually enriched) if set; falls back to text
        texts = [c.embed_text if c.embed_text else c.text for c in chunks]
        try:
            embeddings = self._embedder.embed(texts, validate_tokens=True)
        except RagLibError as exc:
            logger.warning("Embedding failed: %s", exc)
            return 0

        try:
            self._store.add(chunks, embeddings, collection=collection)
        except StorageError as exc:
            logger.warning("Storage failed: %s", exc)
            return 0

        return len(chunks)

    def _update_bm25(self, collection: str) -> None:
        """Rebuild BM25 index after ingestion (D12)."""
        try:
            all_chunks = self._retriever._load_all_chunks_from_store(collection)
            if all_chunks:
                self._retriever.build_bm25_index(all_chunks, collection)
        except Exception as exc:
            logger.warning("BM25 rebuild failed for '%s': %s", collection, exc)
