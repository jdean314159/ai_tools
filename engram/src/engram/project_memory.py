from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .contracts import AugmentRequest, AugmentResult
from .interop import describe_memory
from .memory import (
    LightweightIngestionPolicy,
    canonicalize_episode,
    dedupe_ranked_rows,
    normalize_text,
    score_episode_match,
    score_text,
    text_similarity,
)
from .prompting.builder import build_prompt_from_context
from .telemetry import Telemetry
from .utils.tokens import get_token_counter

if TYPE_CHECKING:
    from .embeddings.base import Embedder
    from .semantic.graph import SemanticGraph
    from .semantic.extractor import SemanticExtractor
    from .semantic.forgetting import ForgettingPolicy, ForgettingConfig

logger = logging.getLogger(__name__)


@dataclass
class PromptBudget:
    total_prompt_tokens: int = 4096


class ProjectMemory:
    """
    engram v0.2: production memory system with hybrid retrieval,
    automatic assistant pairing, and semantic graph with forgetting.
    """

    augmenter_id = "engram"

    def describe_component(self):
        return describe_memory(self)

    def __init__(
        self,
        *,
        retriever: Any = None,
        system_prompt: str = "",
        total_prompt_tokens: int = 4096,
        token_counter: Optional[Callable[[str], int]] = None,
        token_counter_model: str = "cl100k_base",
        base_dir: str | Path | None = None,
        project_id: str = "default",
            project_type: Any = None,
            llm_engine: Any = None,
            session_id: str | None = None,

        # Embedding / vector search
        embedder: Optional[Any] = None,
        enable_embedding_cache: bool = True,
        chromadb_collection_name: Optional[str] = None,

        # Assistant pairing
        auto_pair_assistant: bool = True,
        paired_exchange_importance: float = 0.6,
        orphan_assistant_handling: str = "skip",

        # Semantic graph
        enable_semantic_graph: bool = True,
        extractor: Optional[Any] = None,
        forgetting_config: Optional[Any] = None,
        contradiction_threshold: float = 0.85,

        # Telemetry
        telemetry: Optional[Telemetry] = None,

        # Relevance thresholds (decoy resistance)
        vector_similarity_threshold: float = 0.4,
        min_relevance_score: float = 0.0,

        **kwargs: Any,
    ) -> None:
        self.retriever = retriever
        self.system_prompt = system_prompt or ""
        self.base_dir = Path(base_dir) if base_dir is not None else None
        self.project_id = project_id
        self.session_id = session_id
        self.project_type = project_type
        self.llm_engine = llm_engine
        self.extra_config = dict(kwargs)

        self.budget = PromptBudget(total_prompt_tokens=int(total_prompt_tokens))
        self.telemetry = telemetry or Telemetry()
        self._vector_similarity_threshold = float(vector_similarity_threshold)
        self._min_relevance_score = float(min_relevance_score)

        # Token counter
        if token_counter:
            self._token_counter = token_counter
        else:
            self._token_counter = get_token_counter(token_counter_model)

        # Internal state
        self._sessions: dict[str, list[dict[str, str]]] = {}
        self._loaded_sessions: set[str] = set()
        self._episodes: list[dict[str, Any]] = []
        self.helpers = None
        self._quality = LightweightIngestionPolicy.from_config(kwargs)
        self._quality_stats = {
            "stored": 0,
            "filtered": 0,
            "dedup_blocked": 0,
            "topic_replaced": 0,
            "auto_ingested": 0,
            "assistant_auto_ingest_skipped": 0,
        }
        self._pairing_stats = {
            "paired_exchanges": 0,
            "orphan_assistants": 0,
            "user_only_stored": 0,
        }
        self._semantic_stats = {
            "facts_extracted": 0,
            "contradictions_detected": 0,
            "facts_superseded": 0,
        }

        # Storage setup
        self._storage_root = self._compute_storage_root()
        self._episodes_path = (
            self._storage_root / "episodes.jsonl"
            if self._storage_root is not None else None
        )
        self._sessions_dir = (
            self._storage_root / "sessions"
            if self._storage_root is not None else None
        )
        self._ensure_storage_dirs()
        self._load_episodes()

        # Writer lock (only when persistent storage configured)
        self._writer_lock = None
        if self._storage_root is not None:
            from .concurrency import WriterLock
            self._writer_lock = WriterLock(self._storage_root)
            self._writer_lock.acquire()

        # Schema versioning
        if self._storage_root is not None:
            from .storage.schema import SchemaManager
            from .version import SCHEMA_VERSION
            schema_mgr = SchemaManager(self._storage_root)
            if schema_mgr.get_version() is None:
                schema_mgr.set_version(SCHEMA_VERSION)
            elif schema_mgr.needs_migration(SCHEMA_VERSION):
                current = schema_mgr.get_version()
                logger.warning(
                    f"Project schema {current} differs from engram {SCHEMA_VERSION}. "
                    f"Consider running: engram-lite-migrate {self._storage_root}"
                )

        # Embedder + ChromaDB
        self.embedder = None
        self.chromadb = None
        if embedder is not None:
            if enable_embedding_cache and self._storage_root is not None:
                from .embeddings.cache import EmbeddingCache, CachedEmbedder
                cache = EmbeddingCache(self._storage_root / "embedding_cache.db")
                self.embedder = CachedEmbedder(embedder, cache)
            else:
                self.embedder = embedder

            if self._storage_root is not None:
                from .storage.chromadb_store import ChromaDBStore
                chroma_dir = self._storage_root / "episodic"
                collection_name = chromadb_collection_name or f"{project_id}_episodes"
                try:
                    self.chromadb = ChromaDBStore(
                        persist_directory=chroma_dir,
                        collection_name=collection_name,
                        embedding_dimension=self.embedder.dimension,
                    )
                except Exception as e:
                    from .storage.chromadb_store import DimensionMismatchError
                    if isinstance(e, DimensionMismatchError):
                        raise  # Always propagate — caller must fix their embedder
                    logger.warning(f"ChromaDB init failed: {e}. Falling back to text-only search.")
                    self.chromadb = None

            # Warn if ChromaDB count wildly differs from JSONL count
            if self.chromadb and self._episodes:
                chroma_count = self.chromadb.count()
                jsonl_count = len(self._episodes)
                if jsonl_count > 0:
                    ratio = chroma_count / jsonl_count
                    if ratio < 0.8 or ratio > 1.2:
                        logger.warning(
                            f"ChromaDB count ({chroma_count}) differs significantly from "
                            f"JSONL count ({jsonl_count}). "
                            f"Run: engram-lite-reconcile <project_dir>"
                        )

        # Pairing config
        self._auto_pair_assistant = auto_pair_assistant
        self._paired_importance = paired_exchange_importance
        if orphan_assistant_handling not in ("skip", "store", "warn"):
            raise ValueError(
                f"orphan_assistant_handling must be 'skip', 'store', or 'warn', "
                f"got '{orphan_assistant_handling}'"
            )
        self._orphan_handling = orphan_assistant_handling

        # Semantic graph
        self.semantic = None
        self.forgetting_policy = None
        if enable_semantic_graph and self._storage_root is not None:
            try:
                from .semantic.graph import SemanticGraph
            except ImportError:
                logger.warning(
                    "networkx is not installed — semantic graph disabled. "
                    "Install it with: pip install 'engram-lite[graph]'"
                )
                SemanticGraph = None  # type: ignore[assignment,misc]

            if SemanticGraph is not None:
                try:
                    self.semantic = SemanticGraph(
                        persist_path=self._storage_root / "semantic_graph.json"
                    )
                except Exception as e:
                    logger.error(
                        f"Semantic graph failed to load (corrupted?): {e}. "
                        f"Starting with empty graph."
                    )
                    graph_path = self._storage_root / "semantic_graph.json"
                    if graph_path.exists():
                        backup = graph_path.with_suffix(".json.corrupted")
                        graph_path.rename(backup)
                        logger.warning(f"Corrupted graph saved to {backup}")
                    self.semantic = SemanticGraph(
                        persist_path=self._storage_root / "semantic_graph.json"
                    )
        if forgetting_config is not None and self.semantic is not None:
            from .semantic.forgetting import ForgettingPolicy
            self.forgetting_policy = ForgettingPolicy(forgetting_config)

        self.extractor = extractor
        self._contradiction_threshold = contradiction_threshold

        # Start session if provided
        if session_id is not None:
            self.new_session(session_id)

    # ------------------------------------------------------------------
    # Storage helpers (unchanged from v0.1)
    # ------------------------------------------------------------------

    def _default_token_counter(self, text: str) -> int:
        text = text or ""
        if not text.strip():
            return 0
        return max(1, len(text.split()))

    def _compute_storage_root(self) -> Path | None:
        if self.base_dir is None:
            return None
        safe = str(self.project_id or "default").strip() or "default"
        return self.base_dir / safe

    def _ensure_storage_dirs(self) -> None:
        if self._storage_root is None:
            return
        self._storage_root.mkdir(parents=True, exist_ok=True)
        if self._sessions_dir is not None:
            self._sessions_dir.mkdir(parents=True, exist_ok=True)

    def _read_jsonl(self, path: Path | None) -> list[dict[str, Any]]:
        if path is None or not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except Exception:
                continue
            if isinstance(value, dict):
                rows.append(value)
        return rows

    def _append_jsonl(self, path: Path | None, payload: dict[str, Any]) -> None:
        if path is None:
            return
        self._ensure_storage_dirs()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _rewrite_jsonl(self, path: Path | None, rows: list[dict[str, Any]]) -> None:
        if path is None:
            return
        self._ensure_storage_dirs()
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _session_path(self, session_id: str) -> Path | None:
        if self._sessions_dir is None:
            return None
        safe = str(session_id).strip() or "default"
        return self._sessions_dir / f"{safe}.jsonl"

    def _load_session(self, session_id: str) -> None:
        if session_id in self._loaded_sessions:
            return
        rows = self._read_jsonl(self._session_path(session_id))
        self._sessions[session_id] = [
            {"role": str(r.get("role", "unknown")), "text": str(r.get("text", ""))}
            for r in rows
        ]
        self._loaded_sessions.add(session_id)

    def _load_episodes(self) -> None:
        rows = self._read_jsonl(self._episodes_path)
        self._episodes = []
        malformed = 0
        for row in rows:
            try:
                metadata = dict(row.get("metadata") or {})
                created_at = row.get("created_at", metadata.get("created_at"))
                access_count = int(row.get("access_count", metadata.get("access_count", 0)) or 0)
                self._episodes.append({
                    "id": str(row.get("id") or f"ep_{uuid.uuid4().hex[:12]}"),
                    "text": str(row.get("text", "")),
                    "metadata": metadata,
                    "importance": float(row.get("importance", 0.0)),
                    "created_at": float(created_at) if created_at is not None else None,
                    "access_count": access_count,
                    "normalized_text": str(
                        row.get("normalized_text")
                        or metadata.get("normalized_text")
                        or normalize_text(str(row.get("text", "")))
                    ),
                })
            except Exception as e:
                malformed += 1
                logger.warning(f"Skipped malformed episode row: {e}")
        if malformed > 0:
            logger.warning(
                f"Loaded {len(self._episodes)} episodes, skipped {malformed} malformed rows. "
                f"Consider running: engram-lite-reconcile <project_dir>"
            )
            self._rewrite_jsonl(self._episodes_path, self._episodes)

    def _episode_text(self, item: Any) -> str:
        if isinstance(item, dict):
            return str(item.get("text", ""))
        for attr in ("text", "content", "message", "value"):
            if hasattr(item, attr):
                value = getattr(item, attr, None)
                if isinstance(value, str):
                    return value
        return str(item)

    def _merge_unique_items(self, left: list[Any], right: list[Any]) -> list[Any]:
        merged: list[Any] = []
        for item in list(left) + list(right):
            text = self._episode_text(item).strip()
            if not text:
                continue
            if any(
                text_similarity(text, self._episode_text(e)) >= self._quality.dedup_threshold
                for e in merged
            ):
                continue
            merged.append(item)
        return merged

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def new_session(self, session_id: str) -> None:
        self._load_session(session_id)
        self._sessions.setdefault(session_id, [])
        self.session_id = session_id

    def get_recent_turns(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        self._load_session(session_id)
        return self._sessions.get(session_id, [])[-limit:]

    # ------------------------------------------------------------------
    # Turn ingestion with pairing
    # ------------------------------------------------------------------

    def add_turn(self, role: str, text: str, session_id: str | None = None) -> None:
        session_id = session_id or self.session_id or "default"
        self.new_session(session_id)
        entry = {"role": str(role), "text": str(text)}
        self._sessions[session_id].append(entry)
        self._append_jsonl(self._session_path(session_id), entry)

        normalized_role = str(role or "").strip().lower()
        auto_ingest_roles = {str(r).strip().lower() for r in self._quality.auto_ingest_roles}

        # User turns: auto-ingest to episodic
        if self._quality.auto_ingest_turns and str(text or "").strip() and normalized_role in auto_ingest_roles:
            auto_metadata = {
                "session_id": session_id, "role": normalized_role, "source": "turn_auto_ingest",
            }
            canonical_preview = canonicalize_episode(str(text), auto_metadata)
            decision = score_text(
                text=canonical_preview.text,
                role=normalized_role,
                metadata={**canonical_preview.metadata, "importance": 0.0},
                policy=self._quality,
            )
            if decision.should_store_episode:
                episode_id = self.store_episode(
                    str(text),
                    metadata={**auto_metadata, "ingestion_reasons": list(decision.reasons)},
                    importance=decision.importance,
                    bypass_filter=True,
                )
                if episode_id:
                    self._quality_stats["auto_ingested"] += 1
                    self._pairing_stats["user_only_stored"] += 1
                    # Fact extraction on user turns
                    if self.extractor and self.semantic:
                        self._extract_and_store_facts(str(text), normalized_role, session_id, episode_id)
            return

        # Assistant turns: auto-pair if enabled
        if normalized_role == "assistant" and self._auto_pair_assistant:
            self._handle_assistant_turn(str(text), session_id)
            return

        # Everything else: session-only
        if normalized_role == "assistant":
            self._quality_stats["assistant_auto_ingest_skipped"] += 1
        logger.debug(f"Turn role '{role}' stored to session only")

    def build_prompt_interop(
        self,
        user_message: str,
        *,
        query: str | None = None,
        max_prompt_tokens: int | None = None,
        reserve_output_tokens: int = 512,
    ) -> Any:
        from llm_harness_core import OperationResult
        from .inspection import build_interop_events
        result = self.build_prompt(
            user_message=user_message,
            query=query,
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            return_trace=True,
        )
        trace = result.get("trace")
        trace_events = build_interop_events(trace) if trace is not None else []
        return OperationResult(
            ok=True,
            value=result.get("prompt"),
            diagnostics={
                "trace": trace,
                "prompt_tokens": result.get("prompt_tokens"),
                "trace_events": trace_events,
            },
        )

    def _handle_assistant_turn(self, assistant_text: str, session_id: str) -> None:
        session_history = self._sessions.get(session_id, [])

        # Need at least 2 entries: [user, assistant(current)]
        if len(session_history) < 2:
            self._handle_orphan_assistant(assistant_text, session_id)
            return

        preceding = session_history[-2]  # current is already appended as -1
        if str(preceding.get("role", "")).strip().lower() != "user":
            self._handle_orphan_assistant(assistant_text, session_id)
            return

        user_text = preceding.get("text", "")
        paired_text = f"User: {user_text}\nAssistant: {assistant_text}"

        episode_id = self.store_episode(
            paired_text,
            metadata={
                "type": "exchange",
                "session_id": session_id,
                "user_text": user_text,
                "assistant_text": assistant_text,
            },
            importance=self._paired_importance,
        )

        self._pairing_stats["paired_exchanges"] += 1
        self.telemetry.emit("assistant_paired", {
            "session_id": session_id,
            "episode_id": episode_id,
        })

    def _handle_orphan_assistant(self, assistant_text: str, session_id: str) -> None:
        self._pairing_stats["orphan_assistants"] += 1
        # Keep legacy counter in sync so existing tests checking
        # quality_stats["assistant_auto_ingest_skipped"] continue to pass.
        self._quality_stats["assistant_auto_ingest_skipped"] += 1

        if self._orphan_handling == "store":
            # bypass_filter=True: explicit store request should not be blocked
            # by the quality filter (text may be short, e.g. "Orphaned response.")
            self.store_episode(
                assistant_text,
                metadata={"type": "orphan_assistant", "session_id": session_id},
                importance=self._paired_importance * 0.5,
                bypass_filter=True,
            )
        elif self._orphan_handling == "warn":
            logger.warning(
                f"Orphan assistant turn (no preceding user). "
                f"Session: {session_id}. Use orphan_assistant_handling='store' to keep."
            )

    def _extract_and_store_facts(
        self,
        text: str,
        role: str,
        session_id: str,
        source_episode_id: Optional[str] = None,
    ) -> None:
        if not self.extractor or not self.semantic:
            return
        try:
            from .semantic.contradiction import detect_contradiction
            result = self.extractor.extract(text, role)

            for fact in result.facts:
                fact_id = f"fact:{uuid.uuid4().hex[:8]}"

                existing = self.semantic.query_facts(
                    subject=fact.subject,
                    fact_type=fact.fact_type,
                    include_superseded=False,
                )

                self.semantic.add_fact(
                    fact_id=fact_id,
                    fact_type=fact.fact_type,
                    subject=fact.subject,
                    value=fact.value,
                    confidence=fact.confidence,
                    source_episode_id=source_episode_id,
                    metadata={"role": role, "session_id": session_id},
                )
                self._semantic_stats["facts_extracted"] += 1

                if existing:
                    contradicted_id = detect_contradiction(
                        new_fact={"subject": fact.subject, "value": fact.value, "fact_type": fact.fact_type},
                        existing_facts=existing,
                        embedder=self.embedder,
                        similarity_threshold=self._contradiction_threshold,
                    )
                    if contradicted_id:
                        self.semantic.supersede_fact(contradicted_id, fact_id)
                        self._semantic_stats["contradictions_detected"] += 1
                        self._semantic_stats["facts_superseded"] += 1

            if result.facts:
                self.semantic.save()

            self.telemetry.emit("facts_extracted", {
                "count": len(result.facts),
                "llm_used": result.llm_used,
            })
        except Exception as e:
            logger.debug(f"Fact extraction failed: {e}")

    # ------------------------------------------------------------------
    # Batch operations
    # ------------------------------------------------------------------

    def add_turns_batch(self, turns: List[dict], session_id: str) -> dict:
        stats = {"added": 0}
        for turn in turns:
            self.add_turn(
                role=turn.get("role", "user"),
                text=turn.get("text", ""),
                session_id=session_id,
            )
            stats["added"] += 1
        return stats

    def store_episodes_batch(self, episodes: List[dict]) -> dict:
        stats = {"stored": 0, "indexed": 0}
        texts = [ep.get("text", "") for ep in episodes]

        embeddings = None
        if self.embedder and self.chromadb:
            try:
                batch_result = self.embedder.embed_batch(texts)
                embeddings = batch_result.embeddings
            except Exception as e:
                logger.warning(f"Batch embedding failed: {e}")

        episode_ids = []
        metadatas = []
        for i, ep in enumerate(episodes):
            eid = self.store_episode(
                ep.get("text", ""),
                metadata=ep.get("metadata", {}),
                importance=ep.get("importance", 0.5),
            )
            if eid:
                episode_ids.append(eid)
                metadatas.append({**ep.get("metadata", {}), "importance": ep.get("importance", 0.5)})
                stats["stored"] += 1

        if embeddings and self.chromadb and episode_ids:
            try:
                self.chromadb.add_batch(
                    episode_ids=episode_ids,
                    texts=[episodes[i]["text"] for i in range(len(episode_ids))],
                    embeddings=embeddings[:len(episode_ids)],
                    metadatas=metadatas,
                )
                stats["indexed"] = len(episode_ids)
            except Exception as e:
                logger.warning(f"Batch ChromaDB indexing failed: {e}")

        return stats

    # ------------------------------------------------------------------
    # Episode storage
    # ------------------------------------------------------------------

    def store_episode(
        self,
        text: str,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        bypass_filter: bool = False,
        bypass_dedup: bool = False,
    ) -> str:
        canonical = canonicalize_episode(text, metadata)
        payload_metadata = dict(canonical.metadata or {})
        cleaned_text = str(canonical.text or "").strip()
        if not cleaned_text:
            self._quality_stats["filtered"] += 1
            return ""

        decision = score_text(
            text=cleaned_text,
            role=str(payload_metadata.get("role", payload_metadata.get("source_role", "user"))),
            metadata={**payload_metadata, "importance": importance},
            policy=self._quality,
        )
        if not bypass_filter and not decision.should_store_episode:
            self._quality_stats["filtered"] += 1
            return ""

        normalized = decision.normalized_text or normalize_text(cleaned_text)
        topic_key = str(payload_metadata.get("topic_key") or canonical.topic_key or "").strip()
        if topic_key:
            retained = []
            replaced = 0
            for ep in self._episodes:
                ep_topic = str((ep.get("metadata") or {}).get("topic_key") or "").strip()
                if ep_topic == topic_key:
                    replaced += 1
                else:
                    retained.append(ep)
            if replaced:
                self._episodes = retained
                self._rewrite_jsonl(self._episodes_path, self._episodes)
                self._quality_stats["topic_replaced"] += replaced

        if self._quality.dedup_threshold > 0.0 and not bypass_dedup:
            for ep in reversed(self._episodes):
                if text_similarity(cleaned_text, str(ep.get("text", ""))) >= self._quality.dedup_threshold:
                    self._quality_stats["dedup_blocked"] += 1
                    return ""

        episode_id = f"ep_{uuid.uuid4().hex[:12]}"
        created_at = time.time()
        episode = {
            "id": episode_id,
            "text": cleaned_text[: self._quality.max_episode_chars],
            "metadata": {
                **payload_metadata,
                "normalized_text": normalized,
                "ingestion_reasons": list(
                    payload_metadata.get("ingestion_reasons") or decision.reasons
                ),
            },
            "importance": max(float(importance), float(decision.importance)),
            "created_at": created_at,
            "access_count": 0,
            "normalized_text": normalized,
        }
        self._episodes.append(episode)
        self._append_jsonl(self._episodes_path, episode)
        self._quality_stats["stored"] += 1

        # Index in ChromaDB
        if self.embedder and self.chromadb:
            try:
                emb = self.embedder.embed(cleaned_text).embedding
                self.chromadb.add(
                    episode_id=episode_id,
                    text=cleaned_text,
                    embedding=emb,
                    metadata={
                        **payload_metadata,
                        "importance": importance,
                        "created_at": created_at,
                    },
                )
            except Exception as e:
                logger.debug(f"ChromaDB indexing failed (JSONL is source of truth): {e}")

        self.telemetry.emit("episode_stored", {
            "episode_id": episode_id,
            "importance": importance,
            "has_embedding": self.embedder is not None,
        })

        return episode_id

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def search_episodes(
        self,
        query: str,
        n: int = 5,
        min_importance: float = 0.0,
        days_back: int | None = None,
        min_relevance: Optional[float] = None,
        vector_similarity_threshold: Optional[float] = None,
    ) -> list[Any]:
        """Search episodes with hybrid retrieval and relevance thresholding.

        Args:
            query: Search query text.
            n: Maximum results to return.
            min_importance: Minimum episode importance score.
            days_back: Only include episodes from last N days.
            min_relevance: Override final fused-score threshold for this call.
            vector_similarity_threshold: Override cosine similarity threshold
                for vector results (range 0.0-1.0; higher = stricter).
        """
        import time as _time

        start = _time.time()

        # Resolve thresholds (per-call override or instance default)
        sim_threshold = (
            vector_similarity_threshold
            if vector_similarity_threshold is not None
            else self._vector_similarity_threshold
        )
        relevance_threshold = (
            min_relevance
            if min_relevance is not None
            else self._min_relevance_score
        )

        text_results = self._search_episodes_text(
            query=query, n=n * 2,
            min_importance=min_importance, days_back=days_back,
        )

        vector_results = None
        query_embedding = None
        vector_filtered_count = 0

        if self.embedder is not None and self.chromadb is not None:
            try:
                query_embedding = self.embedder.embed(query).embedding
                chroma_results = self.chromadb.query(query_embedding=query_embedding, n=n * 2)
                if chroma_results.get("ids") and chroma_results["ids"][0]:
                    raw_results = []
                    distances = chroma_results.get("distances", [[]])[0]
                    for i in range(len(chroma_results["ids"][0])):
                        # Cosine distance from ChromaDB: 0=identical, 2=opposite.
                        # similarity = 1 - distance. Drop if below threshold.
                        distance = float(distances[i]) if i < len(distances) else 1.0
                        similarity = 1.0 - distance
                        if similarity < sim_threshold:
                            vector_filtered_count += 1
                            continue
                        meta = chroma_results["metadatas"][0][i]
                        raw_results.append({
                            "id": chroma_results["ids"][0][i],
                            "text": chroma_results["documents"][0][i],
                            "metadata": meta,
                            "importance": meta.get("importance", 0.0),
                            "created_at": meta.get("created_at"),
                            "vector_similarity": similarity,
                        })
                    vector_results = raw_results if raw_results else None
            except Exception as e:
                logger.warning(f"Vector search failed, falling back to text-only: {e}")
                self.telemetry.emit("vector_search_failed", {"error": str(e), "query": query})
                vector_results = None

        if vector_results:
            from .retrieval.hybrid import hybrid_episode_search
            fused = hybrid_episode_search(
                query=query,
                query_embedding=query_embedding,
                vector_results=vector_results,
                text_results=text_results,
            )
        else:
            for r in text_results:
                r["final_score"] = r.get("score", 0.0)
            fused = text_results

        # Final relevance threshold on fused score
        before_relevance_filter = len(fused)
        if relevance_threshold > 0.0:
            fused = [r for r in fused if r.get("final_score", 0.0) >= relevance_threshold]

        self.telemetry.emit("search_completed", {
            "query": query,
            "results_count": len(fused[:n]),
            "latency_ms": (_time.time() - start) * 1000,
            "used_vector_search": vector_results is not None,
            "vector_filtered_count": vector_filtered_count,
            "relevance_filtered_count": before_relevance_filter - len(fused),
            "vector_similarity_threshold": sim_threshold,
            "min_relevance": relevance_threshold,
        })

        return self._to_episode_results(fused[:n])

    def _search_episodes_text(
        self,
        query: str,
        n: int,
        min_importance: float,
        days_back: int | None,
    ) -> list[dict]:
        now = time.time()
        cutoff = None if days_back is None else now - (max(0, int(days_back)) * 86400)
        ranked = []

        for episode in reversed(self._episodes):
            importance = float(episode.get("importance", 0.0))
            if importance < float(min_importance):
                continue
            created_at = episode.get("created_at")
            if cutoff is not None and created_at is not None and float(created_at) < cutoff:
                continue
            text = str(episode.get("text", ""))
            score = score_episode_match(
                query=query,
                text=text,
                importance=importance,
                created_at=created_at,
                metadata=dict(episode.get("metadata") or {}),
            )
            if (query or "").strip() and score < self._quality.retrieval_min_score:
                continue
            ranked.append({
                "id": episode.get("id", ""),
                "text": text,
                "metadata": dict(episode.get("metadata") or {}),
                "importance": importance,
                "score": score,
                "created_at": created_at,
            })

        ranked.sort(
            key=lambda row: (
                float(row.get("score", 0.0)),
                float(row.get("importance", 0.0)),
                float(row.get("created_at") or 0.0),
            ),
            reverse=True,
        )

        return dedupe_ranked_rows(ranked, limit=int(n), dedup_threshold=self._quality.dedup_threshold)

    def _to_episode_results(self, rows: list[dict]) -> list[Any]:
        results = []
        for row in rows:
            results.append(SimpleNamespace(
                text=row.get("text", ""),
                metadata=row.get("metadata") or {},
                importance=float(row.get("importance", 0.0)),
                score=float(row.get("final_score", row.get("score", 0.0))),
            ))
        return results

    # ------------------------------------------------------------------
    # Semantic API
    # ------------------------------------------------------------------

    def get_facts(
        self,
        query: Optional[str] = None,
        fact_type: Optional[str] = None,
        subject: Optional[str] = None,
        include_superseded: bool = False,
        limit: int = 10,
    ) -> List[dict]:
        if not self.semantic:
            return []

        if subject or (not query and not fact_type):
            return self.semantic.query_facts(
                subject=subject,
                fact_type=fact_type,
                include_superseded=include_superseded,
                limit=limit,
            )

        all_facts = self.semantic.query_facts(
            fact_type=fact_type,
            include_superseded=include_superseded,
            limit=100,
        )

        if query:
            query_lower = query.lower()
            scored = []
            for fact in all_facts:
                match = 0.0
                if query_lower in fact.get("subject", "").lower():
                    match += 0.5
                if query_lower in fact.get("value", "").lower():
                    match += 0.5
                if query_lower in fact.get("text", "").lower():
                    match += 0.3
                if match > 0:
                    fact["query_score"] = match * fact.get("score", 0.5)
                    scored.append(fact)
            scored.sort(key=lambda f: f["query_score"], reverse=True)
            return scored[:limit]

        return all_facts[:limit]

    def get_paired_exchanges(self, query: str, n: int = 5) -> List[Dict[str, Any]]:
        episodes = self.search_episodes(query=query, n=n)
        exchanges = []
        for ep in episodes:
            meta = getattr(ep, "metadata", {})
            if meta.get("type") == "exchange":
                exchanges.append({
                    "user": meta.get("user_text", ""),
                    "assistant": meta.get("assistant_text", ""),
                    "score": getattr(ep, "score", 0.0),
                    "importance": getattr(ep, "importance", 0.0),
                })
            else:
                text = getattr(ep, "text", "")
                if text.startswith("User: ") and "\nAssistant: " in text:
                    parts = text.split("\nAssistant: ", 1)
                    exchanges.append({
                        "user": parts[0].replace("User: ", "", 1),
                        "assistant": parts[1] if len(parts) > 1 else "",
                        "score": getattr(ep, "score", 0.0),
                        "importance": getattr(ep, "importance", 0.0),
                    })
        return exchanges

    def reconcile_chromadb(self) -> dict:
        """Verify ChromaDB matches JSONL, rebuild missing entries."""
        if not self.chromadb or not self.embedder:
            return {"error": "embedder not configured"}

        jsonl_ids = {ep["id"] for ep in self._episodes if ep.get("id")}
        chroma_data = self.chromadb.collection.get()
        chroma_ids = set(chroma_data["ids"])

        missing = jsonl_ids - chroma_ids
        orphaned = chroma_ids - jsonl_ids

        added = 0
        for ep in self._episodes:
            if ep.get("id") not in missing:
                continue
            try:
                emb = self.embedder.embed(ep["text"]).embedding
                self.chromadb.add(
                    episode_id=ep["id"],
                    text=ep["text"],
                    embedding=emb,
                    metadata=ep.get("metadata", {}),
                )
                added += 1
            except Exception as e:
                logger.warning(f"Reconcile add failed for {ep['id']}: {e}")

        removed = 0
        for oid in orphaned:
            try:
                self.chromadb.delete(oid)
                removed += 1
            except Exception:
                pass

        return {
            "jsonl_count": len(jsonl_ids),
            "chromadb_count": len(chroma_ids),
            "added": added,
            "removed": removed,
        }

    # ------------------------------------------------------------------
    # Prompt building (unchanged interface)
    # ------------------------------------------------------------------

    def _retrieve(self, query: str, *, include_cold_fallback: bool = True) -> Any:
        if self.retriever is None:
            return {"working": [], "episodic": [], "semantic": [], "cold": []}
        retrieve = getattr(self.retriever, "retrieve", None)
        if retrieve is None or not callable(retrieve):
            raise TypeError("retriever must expose a callable retrieve(...) method")
        try:
            return retrieve(query, include_cold_fallback=include_cold_fallback)
        except TypeError:
            return retrieve(query)

    def _recent_working_items(self, limit: int = 20) -> list[dict[str, str]]:
        if not self.session_id:
            return []
        turns = self.get_recent_turns(self.session_id, limit=limit)
        return [
            {"role": t.get("role", "unknown"), "text": f"{t.get('role', 'unknown')}: {t.get('text', '')}"}
            for t in turns if str(t.get("text", "")).strip()
        ]

    def _internal_episode_hits(self, query: str) -> list[Any]:
        return self.search_episodes(query, n=self._quality.internal_retrieval_limit, min_importance=0.05)

    def _merge_working_context(self, retrieval: Any, *, working_items: list, query: str) -> Any:
        internal_episodic = self._internal_episode_hits(query)
        if isinstance(retrieval, dict):
            merged = dict(retrieval)
            existing_working = merged.get("working") or []
            existing_episodic = merged.get("episodic") or []
            if not isinstance(existing_working, list):
                existing_working = [existing_working]
            if not isinstance(existing_episodic, list):
                existing_episodic = [existing_episodic]
            merged["working"] = working_items + existing_working
            merged["episodic"] = self._merge_unique_items(existing_episodic, internal_episodic)
            return merged
        return {
            "working": working_items + list(getattr(retrieval, "working", None) or []),
            "episodic": self._merge_unique_items(
                list(getattr(retrieval, "episodic", None) or []), internal_episodic
            ),
            "semantic": list(getattr(retrieval, "semantic", None) or []),
            "cold": list(getattr(retrieval, "cold", None) or []),
        }

    def build_prompt(
        self,
        user_message: str,
        *,
        query: str | None = None,
        max_prompt_tokens: int | None = None,
        reserve_output_tokens: int = 512,
        include_cold_fallback: bool = True,
        store_overflow_summary: bool = False,
        return_trace: bool = False,
    ) -> dict[str, Any]:
        resolved_query = query or user_message
        retrieval = self._retrieve(resolved_query, include_cold_fallback=include_cold_fallback)
        retrieval = self._merge_working_context(
            retrieval, working_items=self._recent_working_items(), query=resolved_query,
        )
        return build_prompt_from_context(
            user_message=user_message,
            retrieval=retrieval,
            system_prompt=self.system_prompt,
            query=resolved_query,
            total_prompt_tokens=max_prompt_tokens or getattr(self.budget, "total_prompt_tokens", 4096),
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
            return_trace=return_trace,
            token_counter=self._token_counter,
        )

    def build_prompt_trace(self, user_message: str, **kwargs):
        result = self.build_prompt(user_message=user_message, return_trace=True, **kwargs)
        return result["trace"]

    def build_interop_events(self, user_message: str, **kwargs):
        return self.build_prompt_trace(user_message=user_message, **kwargs).to_interop_events()

    def augment(self, request: AugmentRequest) -> AugmentResult:
        result = self.build_prompt(
            user_message=request.user_text,
            query=request.query or request.user_text,
            max_prompt_tokens=request.max_prompt_tokens,
            reserve_output_tokens=request.reserve_output_tokens,
            return_trace=True,
        )
        return AugmentResult(
            prompt=result["prompt"],
            trace=result.get("trace"),
            prompt_tokens=result.get("prompt_tokens"),
            memory_tokens=result.get("memory_tokens"),
            compressed=bool(result.get("compressed", False)),
            raw_context=result.get("context"),
            metadata={
                "project_id": self.project_id,
                "session_id": request.session_id,
                "query": request.query or request.user_text,
            },
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Deletion API
    # ------------------------------------------------------------------

    def delete_episode(self, episode_id: str) -> bool:
        """Delete one episode from JSONL and ChromaDB.

        Args:
            episode_id: Episode ID to delete (e.g. "ep_abc123")

        Returns:
            True if found and deleted, False if not found.
        """
        original_count = len(self._episodes)
        self._episodes = [ep for ep in self._episodes if ep.get("id") != episode_id]

        if len(self._episodes) == original_count:
            return False  # Not found

        # Rewrite JSONL
        self._rewrite_jsonl(self._episodes_path, self._episodes)

        # Remove from ChromaDB
        if self.chromadb:
            try:
                self.chromadb.delete(episode_id)
            except Exception as e:
                logger.debug(f"ChromaDB delete failed for {episode_id}: {e}")

        self._quality_stats["stored"] = max(0, self._quality_stats["stored"] - 1)
        self.telemetry.emit("episode_deleted", {"episode_id": episode_id})
        logger.debug(f"Deleted episode: {episode_id}")
        return True

    def forget_session(self, session_id: str) -> dict:
        """Remove all turns and auto-ingested episodes for a session.

        Args:
            session_id: Session to forget.

        Returns:
            {"turns_removed": N, "episodes_removed": M}
        """
        # Remove episodes that originated from this session
        episodes_before = len(self._episodes)
        self._episodes = [
            ep for ep in self._episodes
            if str((ep.get("metadata") or {}).get("session_id", "")) != session_id
        ]
        episodes_removed = episodes_before - len(self._episodes)
        if episodes_removed > 0:
            self._rewrite_jsonl(self._episodes_path, self._episodes)

        # Remove from ChromaDB — rebuild index from remaining JSONL
        if self.chromadb and self.embedder and episodes_removed > 0:
            try:
                self.chromadb.rebuild_from_episodes(self._episodes, self.embedder)
            except Exception as e:
                logger.warning(f"ChromaDB rebuild after forget_session failed: {e}")

        # Remove session file
        session_path = self._session_path(session_id)
        turns_removed = len(self._sessions.get(session_id, []))
        if session_path and session_path.exists():
            try:
                session_path.unlink()
            except OSError as e:
                logger.debug(f"Could not remove session file: {e}")

        # Clear in-memory session
        self._sessions.pop(session_id, None)
        self._loaded_sessions.discard(session_id)

        self.telemetry.emit("session_forgotten", {
            "session_id": session_id,
            "turns_removed": turns_removed,
            "episodes_removed": episodes_removed,
        })
        logger.info(f"Forgot session {session_id}: {turns_removed} turns, {episodes_removed} episodes")
        return {"turns_removed": turns_removed, "episodes_removed": episodes_removed}

    def forget_user_data(self) -> dict:
        """Remove all project data. Keeps schema version marker.

        Returns:
            Summary of what was removed.
        """
        import shutil

        stats = {
            "episodes_removed": len(self._episodes),
            "sessions_removed": len(self._sessions),
        }

        # Clear in-memory state
        self._episodes = []
        self._sessions = {}
        self._loaded_sessions = set()

        if self._storage_root is None:
            return stats

        # Remove episodes JSONL
        if self._episodes_path and self._episodes_path.exists():
            self._episodes_path.unlink()

        # Remove sessions directory
        if self._sessions_dir and self._sessions_dir.exists():
            shutil.rmtree(self._sessions_dir, ignore_errors=True)
            self._sessions_dir.mkdir(parents=True, exist_ok=True)

        # Remove ChromaDB collection
        if self.chromadb:
            try:
                self.chromadb.client.delete_collection(self.chromadb.collection.name)
                self.chromadb = None
            except Exception as e:
                logger.debug(f"ChromaDB collection delete failed: {e}")

        # Remove semantic graph
        if self.semantic and self.semantic.persist_path:
            try:
                self.semantic.persist_path.unlink(missing_ok=True)
                import networkx as nx
                self.semantic.graph = nx.DiGraph()
            except Exception as e:
                logger.debug(f"Semantic graph removal failed: {e}")

        # Remove embedding cache
        cache_path = self._storage_root / "embedding_cache.db"
        if cache_path.exists():
            cache_path.unlink()

        self.telemetry.emit("user_data_forgotten", stats)
        logger.info(f"Forgot all user data for project: {self.project_id}")
        return stats

    def index_text(self, text: str, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return SimpleNamespace(indexed_text=str(text), backend="engram")

    def run_lifecycle_maintenance(self) -> dict:
        stats: dict = {}
        if self.forgetting_policy and self.semantic:
            stats["forgetting"] = self.forgetting_policy.run_maintenance(self.semantic)
        self.telemetry.emit("lifecycle_maintenance", stats)
        return stats

    def get_stats(self) -> dict[str, Any]:
        turns = self._sessions.get(self.session_id or "", [])
        stats: dict[str, Any] = {
            "backend": "engram",
            "version": "0.2.0",
            "working": {
                "message_count": len(turns),
                "session_id": self.session_id,
            },
            "episodic": {
                "count": len(self._episodes),
                "quality": dict(self._quality_stats),
                "pairing": dict(self._pairing_stats),
            },
            "semantic": {
                "available": self.semantic is not None,
                "stats": self.semantic.get_stats() if self.semantic else {},
                "extraction": dict(self._semantic_stats),
            },
            "vector_search": {
                "available": self.embedder is not None and self.chromadb is not None,
                "embedder": getattr(self.embedder, "model_name", None),
            },
            "config": {
                "total_prompt_tokens": getattr(self.budget, "total_prompt_tokens", 4096),
                "project_id": self.project_id,
                "auto_pair_assistant": self._auto_pair_assistant,
                "episode_threshold": self._quality.episode_threshold,
                "dedup_threshold": self._quality.dedup_threshold,
            },
        }
        if self.embedder and hasattr(self.embedder, "hits"):
            stats["embedding_cache"] = {
                "hits": self.embedder.hits,
                "misses": self.embedder.misses,
            }
        return stats

    def close(self) -> None:
        if self.semantic:
            self.semantic.save()
        if self._writer_lock:
            self._writer_lock.release()
            self._writer_lock = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
