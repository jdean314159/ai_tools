from __future__ import annotations

from dataclasses import dataclass

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional
from uuid import uuid4

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



@dataclass
class PromptBudget:
    """Token budget settings for prompt assembly."""
    total_prompt_tokens: int = 4096


class ProjectMemory:
    """
    Minimal engram-lite prompt augmentation shell.

    This implementation intentionally stays smaller than ``engram``, but it now
    includes basic memory-quality controls:
    - lightweight turn ingestion / importance scoring
    - store-time near-duplicate blocking
    - internal episodic retrieval with scoring and diversity filtering
    - prompt building via the extracted pure builder
    - trace return for llm_inspector integration
    """

    augmenter_id = "engram_lite"

    def describe_component(self):
        return describe_memory(self)

    def __init__(
        self,
        *,
        retriever: Any = None,
        system_prompt: str = "",
        total_prompt_tokens: int = 4096,
        token_counter: Optional[Callable[[str], int]] = None,
        base_dir: str | Path | None = None,
        project_id: str = "default",
        session_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        self.retriever = retriever
        self.system_prompt = system_prompt or ""
        self.base_dir = Path(base_dir) if base_dir is not None else None
        self.project_id = project_id
        self.session_id = session_id
        self.extra_config = dict(kwargs)

        self.budget = PromptBudget(total_prompt_tokens=int(total_prompt_tokens))
        self.telemetry = None

        self._token_counter = token_counter or self._default_token_counter
        self._sessions: dict[str, list[dict[str, str]]] = {}
        self._loaded_sessions: set[str] = set()
        self._episodes: list[dict[str, Any]] = []
        self.helpers = None
        self.semantic = None
        self._quality = LightweightIngestionPolicy.from_config(kwargs)
        self._quality_stats = {
            "stored": 0,
            "filtered": 0,
            "dedup_blocked": 0,
            "topic_replaced": 0,
            "auto_ingested": 0,
            "assistant_auto_ingest_skipped": 0,
        }

        self._storage_root = self._compute_storage_root()
        self._episodes_path = self._storage_root / "episodes.jsonl" if self._storage_root is not None else None
        self._sessions_dir = self._storage_root / "sessions" if self._storage_root is not None else None
        self._ensure_storage_dirs()
        self._load_episodes()

        if session_id is not None:
            self.new_session(session_id)

    def _default_token_counter(self, text: str) -> int:
        text = text or ""
        if not text.strip():
            return 0
        return max(1, len(text.split()))

    def _compute_storage_root(self) -> Path | None:
        if self.base_dir is None:
            return None
        safe_project = str(self.project_id or "default").strip() or "default"
        return self.base_dir / safe_project

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
        safe_session = str(session_id).strip() or "default"
        return self._sessions_dir / f"{safe_session}.jsonl"

    def _load_session(self, session_id: str) -> None:
        if session_id in self._loaded_sessions:
            return
        rows = self._read_jsonl(self._session_path(session_id))
        self._sessions[session_id] = [
            {
                "role": str(row.get("role", "unknown")),
                "text": str(row.get("text", "")),
            }
            for row in rows
        ]
        self._loaded_sessions.add(session_id)

    def _load_episodes(self) -> None:
        rows = self._read_jsonl(self._episodes_path)
        self._episodes = []
        for row in rows:
            metadata = dict(row.get("metadata") or {})
            created_at = row.get("created_at", metadata.get("created_at"))
            access_count = int(row.get("access_count", metadata.get("access_count", 0)) or 0)
            episode = {
                "id": str(row.get("id") or f"ep_{uuid4().hex[:12]}"),
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
            }
            self._episodes.append(episode)

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
            if any(text_similarity(text, self._episode_text(existing)) >= self._quality.dedup_threshold for existing in merged):
                continue
            merged.append(item)
        return merged

    def new_session(self, session_id: str) -> None:
        self._load_session(session_id)
        self._sessions.setdefault(session_id, [])
        self.session_id = session_id

    def add_turn(self, role: str, text: str, session_id: str) -> None:
        self.new_session(session_id)
        entry = {
            "role": str(role),
            "text": str(text),
        }
        self._sessions[session_id].append(entry)
        self._append_jsonl(self._session_path(session_id), entry)

        normalized_role = str(role or "").strip().lower()
        auto_ingest_roles = {str(item).strip().lower() for item in self._quality.auto_ingest_roles}
        if self._quality.auto_ingest_turns and str(text or "").strip() and normalized_role in auto_ingest_roles:
            auto_metadata = {"session_id": session_id, "role": normalized_role, "source": "turn_auto_ingest"}
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
                    metadata={
                        **auto_metadata,
                        "ingestion_reasons": list(decision.reasons),
                    },
                    importance=decision.importance,
                    bypass_filter=True,
                )
                if episode_id:
                    self._quality_stats["auto_ingested"] += 1
        elif self._quality.auto_ingest_turns and str(text or "").strip() and normalized_role == "assistant":
            self._quality_stats["assistant_auto_ingest_skipped"] += 1

    def get_recent_turns(self, session_id: str, limit: int = 20) -> list[dict[str, str]]:
        self._load_session(session_id)
        turns = self._sessions.get(session_id, [])
        return turns[-limit:]

    def _retrieve(self, query: str, *, include_cold_fallback: bool = True) -> Any:
        if self.retriever is None:
            return {
                "working": [],
                "episodic": [],
                "semantic": [],
                "cold": [],
            }

        retrieve = getattr(self.retriever, "retrieve", None)
        if retrieve is None or not callable(retrieve):
            raise TypeError("retriever must expose a callable retrieve(...) method")

        try:
            return retrieve(
                query,
                include_cold_fallback=include_cold_fallback,
            )
        except TypeError:
            return retrieve(query)

    def _recent_working_items(self, limit: int = 20) -> list[dict[str, str]]:
        if not self.session_id:
            return []
        turns = self.get_recent_turns(self.session_id, limit=limit)
        items: list[dict[str, str]] = []
        for turn in turns:
            role = str(turn.get("role", "unknown"))
            text = str(turn.get("text", ""))
            if text.strip():
                items.append({"role": role, "text": f"{role}: {text}"})
        return items

    def _internal_episode_hits(self, query: str) -> list[Any]:
        return self.search_episodes(
            query,
            n=self._quality.internal_retrieval_limit,
            min_importance=0.05,
        )

    def _merge_working_context(self, retrieval: Any, *, working_items: list[dict[str, str]], query: str) -> Any:
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

        existing_working = getattr(retrieval, "working", None) or []
        existing_episodic = getattr(retrieval, "episodic", None) or []
        if not isinstance(existing_working, list):
            existing_working = [existing_working]
        if not isinstance(existing_episodic, list):
            existing_episodic = [existing_episodic]
        return {
            "working": working_items + existing_working,
            "episodic": self._merge_unique_items(existing_episodic, internal_episodic),
            "semantic": getattr(retrieval, "semantic", []) or [],
            "cold": getattr(retrieval, "cold", []) or [],
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
        retrieval = self._retrieve(
            resolved_query,
            include_cold_fallback=include_cold_fallback,
        )
        retrieval = self._merge_working_context(
            retrieval,
            working_items=self._recent_working_items(),
            query=resolved_query,
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

    def build_prompt_trace(
        self,
        user_message: str,
        *,
        query: str | None = None,
        max_prompt_tokens: int | None = None,
        reserve_output_tokens: int = 512,
        include_cold_fallback: bool = True,
        store_overflow_summary: bool = False,
    ):
        result = self.build_prompt(
            user_message=user_message,
            query=query,
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
            return_trace=True,
        )
        return result["trace"]

    def build_interop_events(
        self,
        user_message: str,
        *,
        query: str | None = None,
        max_prompt_tokens: int | None = None,
        reserve_output_tokens: int = 512,
        include_cold_fallback: bool = True,
        store_overflow_summary: bool = False,
    ):
        trace = self.build_prompt_trace(
            user_message=user_message,
            query=query,
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
        )
        return trace.to_interop_events()

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

    def search_episodes(
        self,
        query: str,
        n: int = 5,
        min_importance: float = 0.0,
        days_back: int | None = None,
    ) -> list[Any]:
        ranked: list[dict[str, Any]] = []
        now = time.time()
        cutoff = None if days_back is None else now - (max(0, int(days_back)) * 86400)
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
            ranked.append(
                {
                    "text": text,
                    "metadata": dict(episode.get("metadata") or {}),
                    "importance": importance,
                    "score": score,
                    "created_at": created_at,
                }
            )

        ranked.sort(
            key=lambda row: (
                float(row.get("score", 0.0)),
                float(row.get("importance", 0.0)),
                float(row.get("created_at") or 0.0),
            ),
            reverse=True,
        )
        selected = dedupe_ranked_rows(
            ranked,
            limit=int(n),
            dedup_threshold=self._quality.dedup_threshold,
        )
        results: list[Any] = []
        for row in selected:
            results.append(
                SimpleNamespace(
                    text=row["text"],
                    metadata=row.get("metadata") or {},
                    importance=float(row.get("importance", 0.0)),
                    score=float(row.get("score", 0.0)),
                )
            )
        return results

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
            retained: list[dict[str, Any]] = []
            replaced = 0
            for episode in self._episodes:
                episode_topic = str((episode.get("metadata") or {}).get("topic_key") or "").strip()
                if episode_topic == topic_key:
                    replaced += 1
                    continue
                retained.append(episode)
            if replaced:
                self._episodes = retained
                self._rewrite_jsonl(self._episodes_path, self._episodes)
                self._quality_stats["topic_replaced"] += replaced

        dedup_threshold = self._quality.dedup_threshold
        if dedup_threshold > 0.0 and not bypass_dedup:
            for episode in reversed(self._episodes):
                existing_text = str(episode.get("text", ""))
                if not existing_text.strip():
                    continue
                if text_similarity(cleaned_text, existing_text) >= dedup_threshold:
                    self._quality_stats["dedup_blocked"] += 1
                    return ""

        episode_id = f"ep_{uuid4().hex[:12]}"
        created_at = time.time()
        episode = {
            "id": episode_id,
            "text": cleaned_text[: self._quality.max_episode_chars],
            "metadata": {
                **payload_metadata,
                "normalized_text": normalized,
                "ingestion_reasons": list(payload_metadata.get("ingestion_reasons") or decision.reasons),
            },
            "importance": max(float(importance), float(decision.importance)),
            "created_at": created_at,
            "access_count": 0,
            "normalized_text": normalized,
        }
        self._episodes.append(episode)
        self._append_jsonl(self._episodes_path, episode)
        self._quality_stats["stored"] += 1
        return episode_id

    def index_text(self, text: str, *args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        return SimpleNamespace(indexed_text=str(text), backend="engram_lite")

    def run_lifecycle_maintenance(self) -> None:
        return None

    def get_stats(self) -> dict[str, Any]:
        turns = self._sessions.get(self.session_id or "", [])
        return {
            "backend": "engram_lite",
            "working": {
                "message_count": len(turns),
                "session_id": self.session_id,
            },
            "episodic": {
                "count": len(self._episodes),
                "quality": dict(self._quality_stats),
            },
            "semantic": {
                "available": False,
            },
            "config": {
                "total_prompt_tokens": getattr(self.budget, "total_prompt_tokens", 4096),
                "project_id": self.project_id,
                "episode_threshold": self._quality.episode_threshold,
                "dedup_threshold": self._quality.dedup_threshold,
                "auto_ingest_turns": self._quality.auto_ingest_turns,
                "auto_ingest_roles": list(self._quality.auto_ingest_roles),
                "assistant_memory_kinds": list(self._quality.assistant_memory_kinds),
            },
        }

    def close(self) -> None:
        return None
