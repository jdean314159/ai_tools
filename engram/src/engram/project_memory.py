"""
Project-Scoped Memory Facade

Binds all five memory layers with physical isolation per project.
Prevents cross-project context pollution.

Each project gets its own directory tree:

    base_dir/
    ├── programming_assistant/
    │   ├── working.db          (SQLite - session context)
    │   ├── episodic/           (ChromaDB - cross-session search)
    │   ├── semantic/           (Kuzu - structured knowledge)
    │   ├── cold.db             (Cold storage - stub)
    │   ├── neural_memory.json  (RTRL weights + hidden state)
    │   └── calibration.json    (surprise filter baseline)
    ├── language_tutor/
    │   └── ...
    └── ...

Usage:
    from engram import ProjectMemory, ProjectType, NeuralMemoryConfig

    memory = ProjectMemory(
        project_id="programming_assistant",
        project_type=ProjectType.PROGRAMMING_ASSISTANT,
        base_dir=Path("~/ai-projects/data/memory"),
        llm_engine=engine,
        neural_config=NeuralMemoryConfig(),  # Enable layer 5
    )

Author: Jeffrey Dean
"""

from __future__ import annotations

import inspect
import logging
import os
import re
import threading
import time
import weakref
import numpy as np
import sqlite3

from .utils.logging_setup import setup_logging_if_needed
from .telemetry import Telemetry, LoggingSink, JsonlFileSink
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING
from .memory.event_bus import EventBus, TurnEvent
from .memory.daemon import MemoryDaemon

if TYPE_CHECKING:
    from .memory.episodic_memory import Episode
    from .memory.semantic_memory import ProjectType
    from .filters.surprise_filter import SurpriseFilter
    from .rtrl.neural_memory import NeuralMemory, NeuralMemoryConfig

from .memory.working_memory import WorkingMemory, Message
from .memory.cold_storage import ColdStorage
from .memory.embedding_cache import EmbeddingCache
from .memory.embedding_service import EmbeddingService
from .memory.neural_coordinator import NeuralCoordinator, resolve_neural_fingerprint
from .memory.memory_context import MemoryContext
from .memory.forgetting import ForgettingPolicy, ForgettingConfig
from .memory.ingestion import MemoryIngestor, IngestionPolicy
from .memory.result_types import TokenBudget, SynthesisHookConfig, ContextResult
from .memory.audit import run_audit, run_remediation
from .memory.synthesis import run_synthesis, build_synthesis_block, load_engine_config
from .prompt.helpers import (
    wrap_memory_block, assemble_prompt, truncate_to_tokens,
    _prompt_friendly_episodic_text, _prompt_friendly_semantic_row,
    _MEMORY_WRAPPER_PREAMBLE, _MEMORY_WRAPPER_BEGIN, _MEMORY_WRAPPER_END,
    _CORRECTION_USE_INSTEAD_PROMPT, _SCHEDULE_UPDATE_PROMPT,
    _REGION_UPDATE_PROMPT, _KEEP_IN_NOT_PROMPT, _PREFIX_ONLY_PROMPT,
    _canonical_subject_for_prompt, _canonical_value_for_prompt,
    _canonical_sentence_for_prompt,
)
from .prompt.builder import (
    build_prompt_core, build_prompt_trace_core, hierarchical_compress_text,
)
from .memory.retrieval import UnifiedRetriever
from .memory.lifecycle import LifecycleConfig, MemoryLifecycleManager
from .memory.extraction import GraphExtractor, ExtractionConfig, ExtractionStats

# Shared token counter: tiktoken (cl100k_base) with len//4 fallback.
# Imported lazily from engine.base so the engines extra is not required
# for the core library to function.
try:
    from .engine.base import _count_tokens as _default_token_counter
except Exception:
    def _default_token_counter(text: str) -> int:  # type: ignore[misc]
        return max(1, len(text) // 4)

logger = logging.getLogger(__name__)


def _build_layers(
    project_dir,
    project_id: str,
    project_type,
    session_id: str,
    budget: "TokenBudget",
    token_counter,
    neural_config,
    forgetting_config,
):
    """Construct all memory layer objects for a project.

    Extracted from ``ProjectMemory.__init__`` so the construction logic is
    independently readable and testable.  Returns a dict of named layer
    instances; ``ProjectMemory.__init__`` unpacks them onto ``self``.

    Optional layers (episodic, semantic, neural) are ``None`` when the
    required optional packages are not installed.
    """
    from pathlib import Path as _Path

    project_dir = _Path(project_dir).expanduser().resolve(strict=False)

    # --- Embedding Cache ---
    embedding_cache = EmbeddingCache(
        cache_dir=project_dir / "embedding_cache",
        enabled=True,
    )

    # --- Layer 1: Working Memory ---
    working = WorkingMemory(
        db_path=project_dir / "working.db",
        session_id=session_id,
        max_tokens=budget.working,
        token_counter=token_counter,
    )

    # --- Layer 2: Episodic Memory (requires chromadb + sentence-transformers) ---
    episodic = None
    try:
        from .memory.episodic_memory import EpisodicMemory
        episodic = EpisodicMemory(
            persist_dir=project_dir / "episodic",
            collection_name=f"{project_id}_episodes",
            embedding_cache=embedding_cache,
        )
    except ImportError:
        logger.info("Episodic memory disabled (pip install engram[episodic])")
    except Exception as e:
        logger.warning("Episodic memory failed to initialize: %s — disabled", e)

    # --- Layer 3: Semantic Memory (requires kuzu) ---
    semantic = None
    try:
        from .memory.semantic_memory import SemanticMemory
        from .memory.types import ProjectType as PT
        if isinstance(project_type, str):
            pt_raw = project_type.strip().lower()
            alias_map = {
                "general": PT.GENERAL_ASSISTANT,
                "default": PT.GENERAL_ASSISTANT,
                "general_assistant": PT.GENERAL_ASSISTANT,
                "programming": PT.PROGRAMMING_ASSISTANT,
                "programming_assistant": PT.PROGRAMMING_ASSISTANT,
                "file_organizer": PT.FILE_ORGANIZER,
                "language_tutor": PT.LANGUAGE_TUTOR,
                "voice_interface": PT.VOICE_INTERFACE,
            }
            if pt_raw in alias_map:
                project_type = alias_map[pt_raw]
            else:
                try:
                    project_type = PT(project_type)
                except ValueError:
                    logger.warning(
                        "Unknown project_type=%r; defaulting to PROGRAMMING_ASSISTANT",
                        project_type,
                    )
                    project_type = PT.PROGRAMMING_ASSISTANT
        semantic = SemanticMemory(
            db_path=project_dir / "semantic",
            project_type=project_type,
        )
    except ImportError:
        logger.info("Semantic memory disabled (pip install engram[semantic])")
    except Exception as e:
        logger.warning(
            "Semantic memory failed to initialize (%s: %s) — disabled. "
            "If you see 'Mmap failed', try: import kuzu; kuzu.Database.__init__?",
            type(e).__name__, e,
        )

    # --- Layer 4: Cold Storage ---
    cold = ColdStorage(db_path=project_dir / "cold.db")

    # --- Layer 6: Procedural Memory (skills — always available) ---
    from .memory.procedural import ProceduralMemory
    procedural = ProceduralMemory(db_path=project_dir / "procedural.db")

    # --- Embedding Service (shared model for neural + retrieval) ---
    device = getattr(neural_config, "device", "cpu") if neural_config else "cpu"
    embedding_service = EmbeddingService(
        episodic=episodic,
        cache=embedding_cache,
        device=device,
    )

    # --- Layer 5: Neural Memory (optional, requires torch) ---
    neural = None
    neural_coord = None
    fingerprint = None  # resolved later with llm_engine
    key_proj = None
    val_proj = None

    if neural_config is not None and getattr(neural_config, "enabled", False):
        try:
            from .rtrl.neural_memory import NeuralMemory, EmbeddingProjector
            # fingerprint resolved after llm_engine is known; set placeholder
            neural = NeuralMemory(project_dir=project_dir, config=neural_config)
            seed = getattr(neural_config, "projection_seed", 42)
            edim = getattr(neural_config, "embedding_dim", 384)
            key_proj = EmbeddingProjector(edim, neural_config.key_dim, seed=seed)
            val_proj = EmbeddingProjector(edim, neural_config.value_dim, seed=seed + 1)
        except ImportError:
            logger.info("Neural memory disabled (pip install engram[neural])")

    # --- Forgetting Policy ---
    forgetting = ForgettingPolicy(
        access_db_path=project_dir / "access_tracker.db",
        config=forgetting_config or ForgettingConfig(),
    )

    # --- Project-specific semantic helpers ---
    helpers = None
    if semantic is not None:
        try:
            helper_cls = _get_helper_map().get(project_type)
            helpers = helper_cls(semantic) if helper_cls else None
        except Exception:
            pass

    # --- Graph Extractor ---
    extractor = GraphExtractor(semantic) if semantic is not None else None

    # --- Experiment / Run Tracking ---
    try:
        from .memory.experiment_memory import ExperimentMemory
        experiments = ExperimentMemory(db_path=project_dir / "experiments.db")
    except Exception as e:
        logger.debug("ExperimentMemory unavailable: %s", e)
        experiments = None

    return {
        "embedding_cache": embedding_cache,
        "working": working,
        "episodic": episodic,
        "semantic": semantic,
        "cold": cold,
        "procedural": procedural,
        "embedding_service": embedding_service,
        "neural": neural,
        "neural_coord": neural_coord,  # completed in __init__ after llm_engine available
        "key_proj": key_proj,
        "val_proj": val_proj,
        "forgetting": forgetting,
        "helpers": helpers,
        "extractor": extractor,
        "experiments": experiments,
        "project_type_resolved": project_type,
    }




class ProjectMemory:

    """Facade that coordinates the five Engram memory layers for one project.

    Physical isolation: each project gets its own directory; no data leaks
    between projects.

    Architecture
    ------------
    Layer construction is handled by ``_build_layers()``.
    Neural coordination is handled by ``NeuralCoordinator``.
    Embedding is handled by ``EmbeddingService``.
    Retrieval, ingestion, and lifecycle are handled by their respective
    orchestrators, which receive a ``MemoryContext`` (narrow dependency
    bundle) instead of a full ``ProjectMemory`` reference.

    ``ProjectMemory`` itself owns:
    - session identity (project_id, session_id)
    - token budget and counter
    - LLM engine reference (for surprise filter and prompt building)
    - the mutable session cell shared with ``MemoryContext``
    - public facade methods (add_turn, store_episode, get_context, build_prompt, …)
    """

    _live_instances = weakref.WeakSet()

    def __init__(
        self,
        project_id: str,
        project_type: ProjectType,
        base_dir: Path,
        llm_engine=None,
        session_id: str = "default",
        token_budget: Optional[TokenBudget] = None,
        token_counter: Optional[Callable[[str], int]] = None,
        surprise_threshold: Optional[float] = None,
        calibration_required: bool = False,
        neural_config: Optional[NeuralMemoryConfig] = None,
        telemetry: Optional[Telemetry] = None,
        forgetting_config: Optional[ForgettingConfig] = None,
        lifecycle_config: Optional[LifecycleConfig] = None,
        ingestion_policy: Optional[IngestionPolicy] = None,
        dedup_threshold: float = 0.92,
        vector_similarity_threshold: float = 0.4,
    ):
        """Initialize isolated project memory.

        Args:
            project_id: Unique project identifier (used as directory name).
            project_type: Schema type for semantic memory.
            base_dir: Root directory for all project memory storage.
            llm_engine: LLM engine for surprise filter and fingerprinting.
                        None = surprise filter disabled.
            session_id: Working memory session ID.
            token_budget: Token allocation per layer. None = defaults.
            token_counter: Custom token counter fn. None = tiktoken cl100k_base
                           with len(text)//4 fallback if tiktoken not installed.
            surprise_threshold: Override default surprise filter threshold.
            calibration_required: Require calibration before filter use.
            neural_config: Neural memory config. None = disabled.
        """
        setup_logging_if_needed()

        # Vector similarity threshold for episodic retrieval.
        # Cosine similarity 0.0-1.0; results below threshold are dropped.
        # Improves decoy resistance significantly. Set to 0.0 to disable.
        self._vector_similarity_threshold = float(vector_similarity_threshold)

        # --- Telemetry (opt-in via env or explicit arg) ---
        if telemetry is None:
            enable = str(os.getenv("ENGRAM_TELEMETRY", "0")).lower() in ("1", "true", "yes")
            sink_name = str(os.getenv("ENGRAM_TELEMETRY_SINK", "log")).lower()
            telemetry = Telemetry()
            if enable:
                if sink_name == "jsonl":
                    raw_path = os.getenv(
                        "ENGRAM_TELEMETRY_PATH",
                        str(Path.home() / ".engram" / "telemetry.jsonl"),
                    )
                    path = Path(raw_path).expanduser().resolve(strict=False)
                    telemetry.add_sink(JsonlFileSink(path))
                else:
                    telemetry.add_sink(LoggingSink())

        self.telemetry = telemetry
        self.project_id = project_id
        self.project_type = project_type
        self.session_id = session_id
        self.llm_engine = llm_engine
        self.budget = token_budget or TokenBudget()
        self._token_counter = token_counter or _default_token_counter

        base_dir = Path(base_dir).expanduser().resolve(strict=False)
        self._project_dir = base_dir / project_id
        self._project_dir.mkdir(parents=True, exist_ok=True)

        self._dedup_threshold = dedup_threshold  # 0.0 = disabled, 0.92 = conservative dedup
        logger.info("Initializing project memory: %s at %s", project_id, self._project_dir)

        # --- Build all memory layers ---
        layers = _build_layers(
            project_dir=self._project_dir,
            project_id=project_id,
            project_type=project_type,
            session_id=session_id,
            budget=self.budget,
            token_counter=self._token_counter,
            neural_config=neural_config,
            forgetting_config=forgetting_config,
        )
        self.embedding_cache = layers["embedding_cache"]
        self.working = layers["working"]
        self.episodic = layers["episodic"]
        self.semantic = layers["semantic"]
        self.cold = layers["cold"]
        self.procedural = layers["procedural"]
        self.embedding_service = layers["embedding_service"]
        self.neural = layers["neural"]
        self.forgetting = layers["forgetting"]
        self.helpers = layers["helpers"]
        self.extractor = layers["extractor"]
        self.experiments = layers["experiments"]
        from .strategies import (
            DirectAnswerStrategy,
            MultiCandidateStrategy,
            ProposeThenVerifyStrategy,
            StrategyRunner,
        )
        self._strategy_runner = StrategyRunner()
        self._strategy_runner.register(DirectAnswerStrategy())
        self._strategy_runner.register(MultiCandidateStrategy())
        self._strategy_runner.register(ProposeThenVerifyStrategy())
        # project_type may have been normalised in _build_layers
        self.project_type = layers["project_type_resolved"]

        # --- Complete neural coordinator (needs llm_engine fingerprint) ---
        self.neural_coord: Optional[NeuralCoordinator] = None
        _fingerprint = resolve_neural_fingerprint(llm_engine)

        if self.neural is not None and layers["key_proj"] is not None:
            if neural_config is not None:
                neural_config.model_fingerprint = _fingerprint
            self.neural.ensure_compatible(_fingerprint)
            self.neural_coord = NeuralCoordinator(
                neural=self.neural,
                key_projector=layers["key_proj"],
                value_projector=layers["val_proj"],
                embedding_service=self.embedding_service,
            )

            # Pre-warm from episodic history so the EMA baseline is meaningful
            # from the first live turn rather than needing 50+ turns to stabilize.
            # Only runs when episodic is available and the network is freshly
            # loaded (total_steps < warmup threshold means it hasn't seen enough).
            if (self.episodic is not None
                    and not self.neural_coord.is_warmed_up()):
                try:
                    recent = self.episodic.get_recent_episodes(
                        n=60, days_back=90, project_id=project_id
                    )
                    if recent:
                        n_warmed = self.neural_coord.warm_up_from_history(recent)
                        if n_warmed > 0:
                            logger.info(
                                "Neural warmup: replayed %d episodes from history",
                                n_warmed,
                            )
                except Exception as e:
                    logger.debug("Neural warmup from history failed: %s", e)

        # --- Surprise Filter (optional, requires LLM engine) ---
        self.surprise = None
        if llm_engine is not None:
            from .filters.surprise_filter import SurpriseFilter
            self.surprise = SurpriseFilter(
                llm_engine=llm_engine,
                project_id=project_id,
                base_threshold=surprise_threshold or 20.0,
                calibration_required=calibration_required,
            )
            cal_path = self._project_dir / "calibration.json"
            if cal_path.exists():
                try:
                    self.surprise.load_calibration(cal_path)
                    logger.info("Loaded surprise calibration from %s", cal_path)
                except Exception as e:
                    logger.warning("Failed to load calibration: %s", e)

        # --- Mutable session cell (shared with MemoryContext) ---
        self._session_cell = [session_id]

        # --- MemoryContext for orchestrators ---
        ctx = MemoryContext(
            working=self.working,
            episodic=self.episodic,
            semantic=self.semantic,
            cold=self.cold,
            procedural=self.procedural,
            neural_coord=self.neural_coord,
            embedding_service=self.embedding_service,
            budget=self.budget,
            token_counter=self._token_counter,
            project_id=project_id,
            project_type=self.project_type,
            telemetry=telemetry,
            search_episodes=self.search_episodes,
            store_episode=self.store_episode,
            _session_cell=self._session_cell,
        )
        self._ctx = ctx

        # --- Orchestration surfaces ---
        self.ingestor = MemoryIngestor(ctx, policy=ingestion_policy)
        self.retriever = UnifiedRetriever(ctx)
        self.lifecycle = MemoryLifecycleManager(ctx, config=lifecycle_config)
        # --- Async ingestion pipeline (must start after ingestor is ready) ---
        self._event_bus = EventBus()
        self._daemon = MemoryDaemon(self, self._event_bus)
        self._daemon.start()
        # Validate all layers at startup
        try:
            self.health_check()
        except RuntimeError as exc:
            logger.error("ProjectMemory init failed health check: %s", exc)
            raise

        # --- Synthesis hook state ---
        self._synthesis_hook: Optional[SynthesisHookConfig] = None
        self._session_episode_count: int = 0   # episodes stored this session
        self._synthesis_background_thread: Optional[threading.Thread] = None
        self._closed = False
        type(self)._live_instances.add(self)
    def _store_experiment_episode_summary(
        self,
        run_id: str,
        user_message: str,
        reply: str,
        strategy: Optional[str] = None,
        task_type: str = "chat",
        problem_family: Optional[str] = None,
        backend_label: Optional[str] = None,
        model_name: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Store a compact episode summarising a completed experiment run.

        Called by multi-candidate and propose-then-verify strategies after
        finish_run().  The episode text captures the exchange in a form
        that future retrieval can surface — "when asked X, the strategy Y
        answered Z" — so the system can learn from past reasoning attempts.

        Args:
            run_id:         Experiment run ID (for cross-reference).
            user_message:   The original user query.
            reply:          The selected/final assistant response.
            strategy:       Strategy name that produced the reply.
            task_type:      Task classification (e.g. "chat", "qa").
            problem_family: Optional domain label (e.g. "math", "code").
            backend_label:  Engine backend identifier.
            model_name:     Model used.
            metrics:        Dict of run metrics (duration, tokens, etc.).
        """
        if not reply:
            return

        summary_parts = [
            f"[Strategy: {strategy or 'unknown'}]",
            f"Q: {user_message[:300]}",
            f"A: {reply[:300]}",
        ]
        if problem_family:
            summary_parts.insert(1, f"[Domain: {problem_family}]")
        episode_text = "  ".join(summary_parts)

        meta: Dict[str, Any] = {
            "run_id": run_id,
            "strategy": strategy,
            "task_type": task_type,
            "problem_family": problem_family,
            "backend_label": backend_label,
            "model_name": model_name,
        }
        if metrics:
            meta["duration_ms"] = metrics.get("duration_ms")
            meta["selected_passed"] = metrics.get("selected_passed")

        # Importance reflects how "useful" this episode is for future recall:
        # passed-verification replies are more worth keeping than failed ones.
        passed = bool(metrics.get("selected_passed", True)) if metrics else True
        importance = 0.65 if passed else 0.35

        self.store_episode(
            episode_text,
            metadata=meta,
            importance=importance,
            bypass_filter=True,
        )

    # ------------------------------------------------------------------
    # Embedding infrastructure (delegates to EmbeddingService)
    # ------------------------------------------------------------------

    def _embed_text(self, text: str) -> Optional[np.ndarray]:
        """Embed text via the shared EmbeddingService."""
        return self.embedding_service.embed(text)

    def run_lifecycle_maintenance(self):
        """Run conservative cross-layer promotion + archival policies.

        Includes neural consolidation: episodes repeatedly retrieved with high
        neural affinity are promoted to semantic memory independently of their
        importance score.
        """
        started = time.perf_counter()
        report = self.lifecycle.run_maintenance()

        # Neural consolidation: promote high-affinity episodes to semantic.
        if self.neural_coord is not None and self.episodic is not None:
            neural_report = self.lifecycle.run_neural_consolidation(
                self.neural_coord, self.episodic)
            report.promoted_events += neural_report.promoted_events
            report.promoted_facts += neural_report.promoted_facts
            report.details.extend(neural_report.details)

        self.telemetry.emit("perf_span", {
            "message": "lifecycle maintenance completed",
            "project_id": self.project_id,
            "session_id": self.session_id,
            "operation": "run_lifecycle_maintenance",
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        })
        return report

    # ------------------------------------------------------------------
    # Conversation turns (working memory + neural memory)
    # ------------------------------------------------------------------

    def add_turn(
        self,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Message:
        """Add a conversation turn to working memory.

        Automatically evicts oldest messages when token budget is exceeded.

        If neural memory is enabled and an embedder is available, also feeds
        the turn into RTRL:
          - User turns: project embedding → buffer as pending key
          - Assistant turns: if pending user key exists, step neural memory
            with key=user_embedding, value=assistant_embedding.  This teaches
            the network "for this user pattern, expect this response pattern."

        The neural surprise score is attached to the Message metadata.
        """
        started = time.perf_counter()
        logger.info("add_turn: role=%s chars=%d", role, len(content))
        msg = self.working.add(role, content, metadata)

        # Feed neural memory if active
        if self.neural_coord is not None:
            self._feed_neural(role, content, msg)

        # Centralized memory formation pipeline. Prefer to store assistant turns
        # as a paired exchange with the immediately preceding user turn.
        # Async ingestion: push to event bus, daemon processes in background.
        # Working memory write above is synchronous; ingestion is decoupled.
        try:
            importance = 0.5
            if msg.metadata and "importance" in msg.metadata:
                importance = float(msg.metadata["importance"])
            paired_text = None
            if role == "assistant":
                recent = self.working.get_recent(2)
                if len(recent) >= 2 and recent[1].role == "user":
                    paired_text = f"User: {recent[1].content}\nAssistant: {recent[0].content}"
            event = TurnEvent(
                role=role,
                text=content,
                importance=importance,
                session_id=self.session_id,
                metadata=metadata or {},
                paired_text=paired_text,
            )
            result = self._event_bus.put(event)
            if msg.metadata is None:
                msg.metadata = {}
            msg.metadata["event_bus"] = result
            self.telemetry.emit("memory_ingest", {
                "message": "turn event queued",
                "project_id": self.project_id,
                "session_id": self.session_id,
                "role": role,
                "event_bus_result": result,
            })
        except Exception as e:
            logger.debug("Event bus enqueue failed: %s", e)

        self.telemetry.emit("perf_span", {
            "message": "conversation turn processed",
            "project_id": self.project_id,
            "session_id": self.session_id,
            "operation": "add_turn",
            "role": role,
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        })
        return msg

    def _feed_neural(self, role: str, content: str, msg: Message):
        """Delegate to NeuralCoordinator."""
        if self.neural_coord is not None:
            self.neural_coord.feed(role, content, msg)

    def _build_neural_hint(self, context: ContextResult) -> str:
        """Delegate to NeuralCoordinator."""
        if self.neural_coord is None:
            return ""
        return self.neural_coord.build_hint(context.neural_meta)

    def get_recent_turns(self, n: int = 10) -> List[Message]:
        """Get N most recent conversation turns."""
        return self.working.get_recent(n)

    def respond(
        self,
        user_message: str,
        *,
        query: Optional[str] = None,
        semantic_query: Optional[str] = None,
        max_prompt_tokens: Optional[int] = None,
        reserve_output_tokens: int = 512,
        include_cold_fallback: bool = True,
        store_overflow_summary: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        strategy: Optional[str] = None,
        **engine_kwargs,
    ) -> Dict[str, Any]:
        """Single-call conversational interface.

        Records the user turn, retrieves memory context, calls the LLM engine,
        records the assistant turn, and returns a result dict.

        Args:
            user_message: The user's input.
            query: Retrieval query override (defaults to user_message).
            semantic_query: Optional separate query for semantic layer.
            max_prompt_tokens: Hard token cap for the assembled prompt.
            reserve_output_tokens: Tokens reserved for the model's reply.
            include_cold_fallback: Allow cold storage in retrieval.
            store_overflow_summary: Store compressed memory as episode on overflow.
            temperature: LLM sampling temperature.
            max_tokens: Max tokens for the LLM to generate.
            strategy: Optional strategy label for telemetry/reporting.
            **engine_kwargs: Extra kwargs forwarded to engine.generate().

        Returns:
            dict with keys:
              - answer:         str — the assistant's response
              - prompt:         str — the assembled prompt sent to the LLM
              - prompt_tokens:  int — estimated token count of prompt
              - memory_tokens:  int — tokens used by retrieved memory
              - compressed:     bool — whether the memory block was compressed
              - strategy:       str | None
        """
        if self.llm_engine is None:
            raise RuntimeError(
                "respond() requires an llm_engine. "
                "Pass llm_engine= to ProjectMemory.__init__()."
            )

        started = time.perf_counter()

        # 1. Open an experiment run if tracking is available
        run_id = None
        if self.experiments is not None:
            try:
                run_id = self.experiments.start_run(
                    project_id=self.project_id,
                    session_id=self.session_id,
                    goal=user_message,
                    task_type="chat",
                    strategy=strategy,
                )
            except Exception as e:
                logger.debug("ExperimentMemory.start_run failed: %s", e)

        # 2. Record user turn (feeds working memory + ingestion pipeline)
        self.add_turn("user", user_message)

        # 3. Assemble prompt with full memory context
        prompt_result = self.build_prompt(
            user_message,
            query=query,
            semantic_query=semantic_query,
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
        )
        prompt = prompt_result["prompt"]

        # 4. Call the LLM
        generate_kwargs = {"temperature": temperature, "max_tokens": max_tokens, **engine_kwargs}
        try:
            signature = inspect.signature(self.llm_engine.generate)
            accepts_var_kwargs = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in signature.parameters.values()
            )
            if not accepts_var_kwargs:
                allowed = {
                    name for name, param in signature.parameters.items()
                    if name != "prompt"
                    and param.kind in (
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        inspect.Parameter.KEYWORD_ONLY,
                    )
                }
                generate_kwargs = {k: v for k, v in generate_kwargs.items() if k in allowed}
        except (TypeError, ValueError):
            pass

        answer = self.llm_engine.generate(prompt, **generate_kwargs)

        # 5. Record assistant turn (feeds working memory + ingestion pipeline)
        self.add_turn("assistant", answer)

        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)

        # 6. Close the experiment run
        if self.experiments is not None and run_id is not None:
            try:
                self.experiments.finish_run(
                    run_id,
                    status="succeeded",
                    backend_label=getattr(self.llm_engine, "backend_label", None),
                    model_name=getattr(self.llm_engine, "model_name", None),
                    metrics={
                        "duration_ms": elapsed_ms,
                        "prompt_tokens": prompt_result.get("prompt_tokens", 0),
                        "memory_tokens": prompt_result.get("memory_tokens", 0),
                        "compressed": prompt_result.get("compressed", False),
                    },
                    outcome_summary=answer[:400] if answer else None,
                )
            except Exception as e:
                logger.debug("ExperimentMemory.finish_run failed: %s", e)

        self.telemetry.emit("respond", {
            "message": "respond() completed",
            "project_id": self.project_id,
            "session_id": self.session_id,
            "strategy": strategy,
            "elapsed_ms": elapsed_ms,
            "prompt_tokens": prompt_result.get("prompt_tokens", 0),
            "compressed": prompt_result.get("compressed", False),
        })

        return {
            "answer": answer,
            "reply": answer,
            "prompt": prompt,
            "prompt_tokens": prompt_result.get("prompt_tokens", 0),
            "memory_tokens": prompt_result.get("memory_tokens", 0),
            "compressed": prompt_result.get("compressed", False),
            "strategy": strategy,
            "run_id": run_id,
        }

    def build_prompt_interop(
        self,
        user_message: str,
        *,
        query: Optional[str] = None,
        semantic_query: Optional[str] = None,
        max_prompt_tokens: Optional[int] = None,
        reserve_output_tokens: int = 512,
        include_cold_fallback: bool = True,
        store_overflow_summary: bool = False,
    ):
        """Build a prompt and return a shared ``OperationResult`` wrapper."""
        from .interop import prompt_result_to_interop_result

        result = self.build_prompt(
            user_message=user_message,
            query=query,
            semantic_query=semantic_query,
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
            return_trace=False,
        )
        trace = self.build_prompt_trace(
            user_message=user_message,
            query=query,
            semantic_query=semantic_query,
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
            _result=result,
        )
        return prompt_result_to_interop_result(result, trace)

    def respond_interop(
        self,
        user_message: str,
        *,
        query: Optional[str] = None,
        semantic_query: Optional[str] = None,
        max_prompt_tokens: Optional[int] = None,
        reserve_output_tokens: int = 512,
        include_cold_fallback: bool = True,
        store_overflow_summary: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        strategy: Optional[str] = None,
        **engine_kwargs,
    ):
        """Respond and return a shared ``OperationResult`` wrapper."""
        from .interop import response_to_interop_result

        response = self.respond(
            user_message=user_message,
            query=query,
            semantic_query=semantic_query,
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
            temperature=temperature,
            max_tokens=max_tokens,
            strategy=strategy,
            **engine_kwargs,
        )
        trace = self.build_prompt_trace(
            user_message=user_message,
            query=query,
            semantic_query=semantic_query,
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
        )
        return response_to_interop_result(response, trace)

    def get_capability_descriptor(self):
        """Describe this memory runtime using the shared interop schema."""
        from .interop import describe_memory

        return describe_memory(self)

    def get_run(self, run_id: str):
        if self.experiments is None:
            return None
        return self.experiments.get_run(run_id)

    def recent_run_summaries(self, limit: int = 20) -> List[Dict[str, Any]]:
        if self.experiments is None:
            return []
        from .reporting.run_reporter import RunReporter
        return RunReporter(self.experiments).recent_run_summaries(limit=limit)

    def recent_failure_summaries(self, limit: int = 10) -> List[Dict[str, Any]]:
        if self.experiments is None:
            return []
        from .reporting.run_reporter import RunReporter
        return RunReporter(self.experiments).recent_failure_summaries(limit=limit)

    def strategy_summary(self, limit: int = 200) -> List[Dict[str, Any]]:
        if self.experiments is None:
            return []
        from .reporting.run_reporter import RunReporter
        return RunReporter(self.experiments).strategy_summary(limit=limit)

    def available_strategies(self) -> List[str]:
        return self._strategy_runner.available_strategies()

    def run_strategy(self, strategy_name: str, user_message: str, **kwargs) -> Dict[str, Any]:
        return self._strategy_runner.run(self, strategy_name, user_message, **kwargs)

    def new_session(self, session_id: str):
        """Start a new working memory session.

        Previous session data remains in the database but is no longer
        active. Useful for voice interface session boundaries.

        Neural memory resets hidden state (but keeps learned weights)
        since the conversational context has changed.
        """
        self.session_id = session_id
        self._session_cell[0] = session_id  # propagates to MemoryContext.session_id
        self.working.close()
        self.working = WorkingMemory(
            db_path=self._project_dir / "working.db",
            session_id=session_id,
            max_tokens=self.budget.working,
            token_counter=self._token_counter,
        )
        # Keep MemoryContext's working reference in sync
        if hasattr(self, "_ctx"):
            self._ctx.working = self.working
        if self.neural_coord is not None:
            self.neural_coord.reset()
        elif self.neural is not None:
            self.neural.reset()

    # ------------------------------------------------------------------
    # Episode storage (episodic memory, surprise-gated)
    # ------------------------------------------------------------------

    def store_episode(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
        bypass_filter: bool = False,
        bypass_dedup: bool = False,
    ) -> Optional[str]:
        """Store an episode if it passes the surprise filter.

        When the neural coordinator is warmed up, the importance score is
        set dynamically from the RTRL surprise EMA rather than using the
        caller-supplied default.  High-surprise turns produce higher-importance
        episodes; familiar turns produce lower-importance ones.  The caller's
        importance is used as a floor so explicitly important episodes are
        never downgraded.

        Args:
            text: Episode content
            metadata: Optional metadata
            importance: 0.0-1.0 importance score (used as floor when neural active)
            bypass_filter: Skip surprise filter (force store)

        Returns:
            Episode ID if stored, None if filtered out.
        """
        if getattr(self, "_closed", False):
            logger.debug("Skipping store_episode because ProjectMemory is closed")
            return ""

        started = time.perf_counter()
        if not bypass_filter and self.surprise is not None:
            if not self.surprise.should_store(text):
                logger.debug("Episode filtered (not surprising): %.50s...", text)
                return None

        if self.episodic is None:
            logger.warning("Episodic memory not available — episode not stored")
            return None

        # Dynamic importance from neural surprise (when warmed up)
        neural_importance = None
        neural_surprise_ratio = None
        if self.neural_coord is not None and self.neural_coord.is_warmed_up():
            raw = self.neural_coord.get_last_surprise()
            if raw is not None:
                ema = self.neural_coord.get_surprise_ema()
                if ema > 1e-8:
                    # Surprise ratio: how many times above the EMA baseline.
                    # Capped at 3.0 to bound the effect of extreme outliers.
                    ratio = raw / ema
                    neural_surprise_ratio = float(min(ratio, 3.0) / 3.0)  # normalised 0→1

                    # Importance: maps ratio to 0.1–0.95 range
                    # ratio=0.5 → 0.37, ratio=1.5 → 0.50, ratio=3.0 → 0.70
                    neural_importance = float(
                        min(0.95, max(0.1, 0.3 + 0.4 * min(ratio, 3.0) / 3.0))
                    )
                    logger.debug(
                        "Neural importance: raw=%.4f ema=%.4f ratio=%.2f "
                        "→ importance=%.3f surprise_ratio=%.3f",
                        raw, ema, ratio, neural_importance, neural_surprise_ratio,
                    )

        # Use neural score when available; never drop below caller's floor
        effective_importance = max(
            importance,
            neural_importance if neural_importance is not None else 0.0,
        )

        # Deduplication: tombstone near-duplicate episodes before storing.
        # Threshold 0.92 catches paraphrases of the same fact while leaving
        # distinct-but-related episodes intact.
        dedup_threshold = getattr(self, "_dedup_threshold", 0.92)
        if dedup_threshold > 0.0 and not bypass_dedup:
            try:
                similar = self.episodic.find_similar_episodes(
                    text=text,
                    project_id=self.project_id,
                    n=5,
                    similarity_threshold=dedup_threshold,
                )
                if similar:
                    ids_to_tombstone = [eid for eid, _ in similar]
                    n_tombstoned = self.episodic.tombstone_episodes(ids_to_tombstone)
                    logger.debug(
                        "Dedup: tombstoned %d episode(s) before storing new episode",
                        n_tombstoned,
                    )
            except Exception as e:
                logger.warning("Deduplication check failed: %s", e)

        episode_id = self.episodic.add_episode(
            text=text,
            metadata={
                **(metadata or {}),
                # neural_surprise_ratio: raw surprise relative to EMA, normalised 0→1.
                # Used by ForgettingPolicy.score_episode() weight_surprise term.
                # Higher = more surprising at storage time = worth retaining longer.
                "neural_surprise": neural_surprise_ratio,
                # neural_importance: the 0.1–0.95 score that was added to episode importance.
                # Stored for diagnostics — not used by forgetting policy directly.
                "neural_importance": neural_importance,
                "caller_importance": importance,
            },
            session_id=self.session_id,
            project_id=self.project_id,
            importance=effective_importance,
        )
        logger.debug("Stored episode %s (importance=%.3f)", episode_id, effective_importance)

        # Track for forgetting policy auto-trigger.
        # Run maintenance on a daemon thread so it never blocks the chat path.
        self.forgetting.record_new_episode()
        if self.forgetting.should_auto_run():
            self._run_maintenance_background()

        # Track episode count for synthesis hook
        self._session_episode_count += 1

        self.telemetry.emit("perf_span", {
            "message": "episode stored",
            "project_id": self.project_id,
            "session_id": self.session_id,
            "operation": "store_episode",
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        })
        return episode_id

    def search_episodes(
        self,
        query: str,
        n: int = 5,
        min_importance: float = 0.0,
        days_back: Optional[int] = None,
        vector_similarity_threshold: Optional[float] = None,
    ) -> List[Episode]:
        """Semantic search within this project's episodes only.

        project_id filtering is enforced automatically. Access is tracked
        for the forgetting policy.

        Args:
            vector_similarity_threshold: Override instance-level threshold
                (cosine similarity 0.0-1.0). Higher = stricter filter.
                None uses self._vector_similarity_threshold.
        """
        if self.episodic is None:
            return []
        threshold = (
            vector_similarity_threshold
            if vector_similarity_threshold is not None
            else getattr(self, "_vector_similarity_threshold", 0.0)
        )
        episodes = self.episodic.search(
            query=query,
            n=n,
            project_id=self.project_id,
            min_importance=min_importance,
            days_back=days_back,
            vector_similarity_threshold=threshold,
        )
        # Record access for forgetting policy retention scoring
        if episodes:
            self.forgetting.record_access([ep.id for ep in episodes if ep.id])
        return episodes

    # ------------------------------------------------------------------
    # Unified context retrieval
    # ------------------------------------------------------------------

    def get_context(
        self,
        query: Optional[str] = None,
        max_tokens: Optional[int] = None,
        semantic_query: Optional[str] = None,
        episodic_n: int = 5,
        semantic_n: int = 5,
        cold_n: int = 5,
        cold_fallback: bool = True,
        cold_min_fill_ratio: float = 0.2,
    ) -> ContextResult:
        """Assemble context from all memory layers within token budget.

        Retrieves from each layer up to its allocated budget. If a layer
        underuses its budget, the surplus is NOT redistributed (keeps
        retrieval predictable and fast).

        Args:
            query: Search query for episodic retrieval. If None, episodic
                   results are skipped.
            max_tokens: Total token cap. None = use budget.total.
            semantic_query: Cypher query for semantic layer. If None,
                           semantic results are skipped.
            episodic_n: Max episodic episodes to retrieve.
            semantic_n: Max semantic results to retrieve.

        Returns:
            ContextResult with content from each layer and token counts.
        """
        started = time.perf_counter()
        budget = max_tokens or self.budget.total

        # Unified retrieval path: fetch from all layers, deduplicate globally,
        # then populate ContextResult with per-layer budgets preserved.
        result = self.retriever.retrieve(
            query=query,
            max_tokens=budget,
            episodic_n=episodic_n,
            semantic_n=semantic_n,
            cold_n=cold_n,
            cold_fallback=cold_fallback,
            cold_min_fill_ratio=cold_min_fill_ratio,
        )

        # Optional explicit semantic query remains available for callers that
        # know the schema and want deterministic graph retrieval. Merge only
        # rows that do not duplicate the fused results.
        if semantic_query and self.semantic is not None:
            try:
                rows = self.semantic.query(semantic_query)
                seen = {str(item) for item in result.semantic}
                semantic_budget = min(
                    self.budget.semantic,
                    budget - result.working_tokens - result.episodic_tokens - result.semantic_tokens - result.cold_tokens,
                )
                tokens_used = 0
                for row in rows[:semantic_n]:
                    row_text = str(row)
                    if row_text in seen:
                        continue
                    row_tokens = self._token_counter(row_text)
                    if tokens_used + row_tokens > semantic_budget:
                        break
                    result.semantic.append(row)
                    tokens_used += row_tokens
                    seen.add(row_text)
                result.semantic_tokens += tokens_used
            except Exception as e:
                logger.warning("Semantic query failed: %s", e)

        self.telemetry.emit("perf_span", {
            "message": "context retrieved",
            "project_id": self.project_id,
            "session_id": self.session_id,
            "operation": "get_context",
            "query": query,
            "elapsed_ms": round((time.perf_counter() - started) * 1000.0, 3),
        })
        return result

    def get_diagnostics_snapshot(self) -> Dict[str, Any]:
        """Return a lightweight diagnostics snapshot for evaluation and profiling."""
        semantic_stats = self.semantic.get_stats() if self.semantic is not None else {}
        cold_stats = self.cold.get_stats() if self.cold is not None else {}
        neural_stats = (
            self.neural_coord.get_stats() if self.neural_coord is not None
            else self.neural.get_stats() if self.neural is not None
            else {}
        )
        return {
            "project_id": self.project_id,
            "session_id": self.session_id,
            "budget": {
                "working": self.budget.working,
                "episodic": self.budget.episodic,
                "semantic": self.budget.semantic,
                "cold": self.budget.cold,
                "total": self.budget.total,
            },
            "semantic": semantic_stats,
            "cold": cold_stats,
            "neural": neural_stats,
        }


    def _hierarchical_compress(self, sections, neural_hint, available_tokens, count_fn) -> str:
        """Thin wrapper — delegates to prompt.builder.hierarchical_compress_text."""
        return hierarchical_compress_text(sections, neural_hint, available_tokens, count_fn)


    def build_prompt(
            self,
            user_message: str,
            *,
            query: str | None = None,
            semantic_query: str | None = None,
            max_prompt_tokens: int | None = None,
            reserve_output_tokens: int = 512,
            include_cold_fallback: bool = True,
            store_overflow_summary: bool = False,
            return_trace: bool = False,
    ) -> Dict[str, Any]:
        """Build an LLM prompt from memory context — delegates to prompt.builder."""
        return build_prompt_core(
            self,
            user_message=user_message,
            query=query,
            semantic_query=semantic_query,
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
            return_trace=return_trace,
        )


    def index_text(
        self,
        text: str,
        document_index: int = 0,
        config: Optional[ExtractionConfig] = None,
    ) -> ExtractionStats:
        """Extract entities and co-occurrence relations from text into the semantic graph.

        Uses TF-IDF by default (zero dependencies beyond scikit-learn).
        Pass config=ExtractionConfig(method="spacy") for typed NER.

        Returns ExtractionStats with entity/sentence/relation counts.
        Returns a zero-count ExtractionStats (no-op) if semantic memory is
        not enabled — does not raise, so callers need not check first.
        """
        if self.extractor is None:
            logger.debug(
                "index_text() called but semantic memory is not enabled "
                "(install engram[semantic] and pass a SemanticMemory instance). "
                "Returning empty ExtractionStats."
            )
            return ExtractionStats(method="disabled")
        if config is not None:
            self.extractor.config = config
        return self.extractor.index_text(text, document_index=document_index)

    def index_documents(
        self,
        documents: List[str],
        config: Optional[ExtractionConfig] = None,
    ) -> ExtractionStats:
        """Extract entities and relations from multiple documents into the semantic graph.

        Returns aggregate ExtractionStats.
        Returns a zero-count ExtractionStats (no-op) if semantic memory is
        not enabled — does not raise, so callers need not check first.
        """
        if self.extractor is None:
            logger.debug(
                "index_documents() called but semantic memory is not enabled. "
                "Returning empty ExtractionStats."
            )
            return ExtractionStats(method="disabled", documents=len(documents))
        if config is not None:
            self.extractor.config = config
        return self.extractor.index_documents(documents)

    # ------------------------------------------------------------------
    # Fine-tuning data export
    # ------------------------------------------------------------------

    def export_dataset(
        self,
        path,
        format: str = "openai",
        config=None,
    ) -> int:
        """Export conversation history as fine-tuning data.

        Pulls from episodic memory, cold storage, and working.db.
        Reconstructs user/assistant pairs grouped by session.

        Args:
            path: Output file path (str or Path). Created/overwritten.
            format: "openai" | "alpaca" | "raw"
            config: engram.ExportConfig instance. None = defaults.

        Returns:
            Number of records written.
        """
        from pathlib import Path as _Path
        from .finetune.export import ExportConfig as _EC, export_to_file as _etf
        cfg = config or _EC()
        return _etf(self, _Path(path).expanduser().resolve(strict=False), format=format, config=cfg)

    def export_dataset_stats(self, config=None) -> Dict[str, Any]:
        """Dry-run export: return counts without writing any file.

        Returns dict with total_turns, sessions, complete_pairs, etc.
        """
        from .finetune.export import ExportConfig as _EC, export_stats as _es
        cfg = config or _EC()
        return _es(self, cfg)

    # ------------------------------------------------------------------
    # Memory maintenance (forgetting policy)
    # ------------------------------------------------------------------

    def _run_maintenance_background(self) -> None:
        """Spawn a daemon thread to run the forgetting policy.

        Called automatically from ``store_episode`` when the auto-trigger
        threshold is met.  Using a thread prevents the maintenance scan
        (which iterates all episode metadata in ChromaDB) from blocking the
        chat response path.

        The thread is daemonised so it will not prevent process exit.  If
        maintenance is already running (a previous trigger that hasn't
        finished), the new request is silently dropped — the counter will
        trip again after the next batch of episodes anyway.
        """
        # Guard: don't stack multiple maintenance threads
        if getattr(self, "_maintenance_running", False):
            logger.debug("Maintenance already in progress; skipping new trigger.")
            return

        def _worker():
            self._maintenance_running = True
            try:
                result = self.run_maintenance(dry_run=False)
                archived = result.get("archived", 0)
                if archived:
                    logger.info(
                        "Background maintenance: archived %d episodes for %s",
                        archived, self.project_id,
                    )
                else:
                    logger.debug(
                        "Background maintenance: nothing to archive for %s (%s)",
                        self.project_id, result.get("status", ""),
                    )
            except Exception as exc:
                logger.warning("Background maintenance failed: %s", exc)
            finally:
                self._maintenance_running = False

        self._maintenance_running = False  # ensure attr exists before thread starts
        t = threading.Thread(target=_worker, name=f"engram-maintenance-{self.project_id}",
                             daemon=True)
        t.start()

    def run_maintenance(self, dry_run: bool = False) -> Dict[str, Any]:
        """Run the forgetting policy: archive low-retention episodes to cold storage.

        Scores all episodes by retention value (recency × importance × access
        frequency × surprise), archives those below threshold to cold storage,
        and deletes them from episodic memory.

        Args:
            dry_run: If True, score and report without archiving.

        Returns dict with stats about the run.
        """
        if self.episodic is None:
            return {"status": "skipped", "reason": "episodic memory not available"}

        result = self.forgetting.run(
            episodic_memory=self.episodic,
            cold_storage=self.cold,
            project_id=self.project_id,
            dry_run=dry_run,
        )

        if not dry_run and result.get("archived", 0) > 0:
            self.telemetry.emit("forgetting_run", {
                "message": f"Archived {result['archived']} episodes to cold storage",
                "project_id": self.project_id,
                "archived": result["archived"],
                "total_scored": result.get("total_scored", 0),
            })

        return result

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------

    def calibrate_surprise_filter(
        self,
        human_texts: List[str],
        force: bool = False,
    ):
        """Calibrate surprise filter on human data and save to disk.

        Args:
            human_texts: List of human-written texts (>100 recommended)
            force: Recalibrate even if already calibrated
        """
        if self.surprise is None:
            raise ValueError("No LLM engine provided — surprise filter disabled")

        self.surprise.calibrate(human_texts, force=force)
        cal_path = self._project_dir / "calibration.json"
        self.surprise.save_calibration(cal_path)

    # ------------------------------------------------------------------
    # Stats & lifecycle
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate statistics from all layers."""
        stats = {
            "project_id": self.project_id,
            "project_type": self.project_type.value if hasattr(self.project_type, 'value') else str(self.project_type),
            "session_id": self.session_id,
            "project_dir": str(self._project_dir),
            "token_budget": {
                "working": self.budget.working,
                "episodic": self.budget.episodic,
                "semantic": self.budget.semantic,
                "total": self.budget.total,
            },
            "working": self.working.get_stats(),
            "episodic": self.episodic.get_stats() if self.episodic else {"enabled": False},
            "semantic": self.semantic.get_stats() if self.semantic else {"enabled": False},
            "cold": self.cold.get_stats(),
            "forgetting": self.forgetting.get_stats(),
            "embedding_cache": self.embedding_cache.get_stats(),
        }
        if self.neural_coord is not None:
            stats["neural"] = self.neural_coord.get_stats()
        elif self.neural:
            stats["neural"] = self.neural.get_stats()
        if self.surprise:
            stats["surprise_filter"] = self.surprise.get_stats()
        if self.extractor is not None:
            stats["graph_extractor"] = self.extractor.get_stats()
        if hasattr(self, "_daemon"):
            stats["daemon"] = self._daemon.get_stats()
        return stats

    def clear_session(self):
        """Clear current working memory session only."""
        self.working.clear_session()

    def clear_all(self):
        """Clear all memory for this project. Destructive."""
        logger.warning("Clearing all memory for project: %s", self.project_id)
        self.working.clear_session()
        if self.episodic:
            self.episodic.clear_collection()
        # Semantic: no bulk clear method, would need to drop/recreate

    def configure_synthesis_hook(self, config: "SynthesisHookConfig") -> None:
        """Enable or update the session-end synthesis approval hook.

        Call once after init to opt in:

            pm.configure_synthesis_hook(SynthesisHookConfig(
                enabled=True,
                episode_threshold=20,
            ))

        The hook fires when end_session() is called and the session produced
        enough new episodes. The approval_callback receives a prompt string
        and returns True (run now) or False (defer).
        """
        self._synthesis_hook = config

    def end_session(self) -> Dict[str, Any]:
        """Signal explicit session end and fire the synthesis hook if configured.

        Should be called by the application when a session naturally ends
        (e.g. user closes the chat, voice session ends, script exits cleanly).
        Resets the per-session episode counter regardless of hook state.

        Returns a dict describing what happened:
            {
                "episodes_this_session": int,
                "synthesis_triggered": bool,
                "synthesis_approved": bool,
                "synthesis_deferred": bool,
                "synthesis_result": dict | None,
            }
        """
        outcome: Dict[str, Any] = {
            "episodes_this_session": self._session_episode_count,
            "synthesis_triggered": False,
            "synthesis_approved": False,
            "synthesis_deferred": False,
            "synthesis_result": None,
        }

        cfg = self._synthesis_hook
        if cfg is None or not cfg.enabled:
            self._session_episode_count = 0
            return outcome

        if self._session_episode_count < cfg.episode_threshold:
            logger.debug(
                "end_session: %d episodes < threshold %d — skip synthesis prompt",
                self._session_episode_count, cfg.episode_threshold,
            )
            self._session_episode_count = 0
            return outcome

        # Threshold reached — ask for approval
        outcome["synthesis_triggered"] = True
        prompt_text = (
            f"\n[Engram] This session produced {self._session_episode_count} episodes "
            f"(threshold: {cfg.episode_threshold}).\n"
            f"Run synthesis now to extract procedural rules? [y/N] "
        )

        try:
            if cfg.approval_callback is not None:
                approved = bool(cfg.approval_callback(prompt_text))
            else:
                # Default: stdout/stdin prompt
                response = input(prompt_text).strip().lower()
                approved = response in ("y", "yes")
        except Exception as exc:
            logger.warning("end_session: approval callback failed: %s — deferring", exc)
            approved = False

        self._session_episode_count = 0  # reset regardless of decision

        if not approved:
            outcome["synthesis_deferred"] = True
            logger.info(
                "end_session: synthesis deferred by user (project=%s)",
                self.project_id,
            )
            return outcome

        # Approved — run in background thread so session teardown isn't blocked
        outcome["synthesis_approved"] = True

        def _run():
            try:
                result = self.synthesize_now(
                    window_size=cfg.window_size,
                    days_back=cfg.days_back,
                    min_support=cfg.min_support,
                    min_confidence=cfg.min_confidence,
                )
                logger.info(
                    "end_session synthesis complete: rules_written=%d "
                    "relations_written=%d elapsed=%.1fs (project=%s)",
                    result.get("rules_written", 0),
                    result.get("relations_written", 0),
                    result.get("extraction_seconds", 0.0),
                    self.project_id,
                )
                # Store result for later inspection if thread completes
                # before the caller checks outcome (best-effort)
                outcome["synthesis_result"] = result
            except Exception as exc:
                logger.warning("end_session: background synthesis failed: %s", exc)

        t = threading.Thread(target=_run, daemon=True, name="engram-synthesis")
        self._synthesis_background_thread = t
        t.start()
        logger.info(
            "end_session: synthesis started in background (project=%s)",
            self.project_id,
        )
        return outcome

    @classmethod
    def close_live_instances_under(cls, base_dir: Path) -> None:
        """Close live ProjectMemory instances whose project dirs are under base_dir.

        This is primarily useful for test cleanup: ProjectMemory starts a
        background ingestion daemon, so tests that use temporary directories
        must stop the daemon before deleting the directory tree.
        """
        base = Path(base_dir).expanduser().resolve(strict=False)
        for instance in list(cls._live_instances):
            project_dir = getattr(instance, "_project_dir", None)
            if project_dir is None:
                continue
            try:
                resolved_project_dir = Path(project_dir).expanduser().resolve(strict=False)
                if not resolved_project_dir.is_relative_to(base):
                    continue
                instance.close()
            except Exception as exc:
                logger.debug("close_live_instances_under failed: %s", exc)

    @classmethod
    def close_all_live_instances(cls) -> None:
        """Best-effort cleanup for any live ProjectMemory instances."""
        for instance in list(cls._live_instances):
            try:
                instance.close()
            except Exception as exc:
                logger.debug("close_all_live_instances failed: %s", exc)

    def close(self):
        """Release all resources."""
        if getattr(self, "_closed", False):
            return
        self._closed = True

        try:
            type(self)._live_instances.discard(self)
        except Exception:
            pass

        # Wait for background synthesis if running (up to 90s)
        t = getattr(self, "_synthesis_background_thread", None)
        if t is not None and t.is_alive():
            logger.info("close: waiting for background synthesis to finish...")
            t.join(timeout=90.0)
            if t.is_alive():
                logger.warning("close: synthesis thread still running after 90s — continuing teardown")
        if hasattr(self, "_daemon"):
            self._daemon.stop(timeout=5.0)
        if hasattr(self, "working"):
            self.working.close()
        if getattr(self, "semantic", None):
            self.semantic.close()
        if hasattr(self, "cold"):
            self.cold.close()
        if hasattr(self, "procedural") and self.procedural is not None:
            self.procedural.close()
        if getattr(self, "neural_coord", None) is not None:
            self.neural_coord.close()  # Saves NeuralMemory state
        elif getattr(self, "neural", None):
            self.neural.close()
        if hasattr(self, "forgetting"):
            self.forgetting.close()
        if hasattr(self, "embedding_cache"):
            self.embedding_cache.close()

    def __del__(self):
        """Best-effort resource cleanup on garbage collection."""
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __repr__(self) -> str:
        return (
            f"ProjectMemory(project_id={self.project_id!r}, "
            f"type={self.project_type.value if hasattr(self.project_type, 'value') else self.project_type}, "
            f"session={self.session_id!r})"
        )

    def health_check(self) -> Dict[str, Any]:
        """Validate all memory layers are functional.

        Runs a lightweight read/write probe on each layer.
        Raises RuntimeError if any critical layer fails.
        Logs WARNING for non-critical failures.

        Returns a report dict suitable for display in the UI or logs.
        Can be called at any time, not just at init.
        """
        report = {
            "project_id": self.project_id,
            "timestamp": time.time(),
            "layers": {},
            "warnings": [],
            "critical": [],
        }

        # --- Working memory (critical) ---
        try:
            db_path = self._project_dir / "working.db"
            conn = sqlite3.connect(str(db_path))
            conn.execute("SELECT COUNT(*) FROM messages")
            conn.close()
            report["layers"]["working"] = "ok"
        except Exception as exc:
            report["layers"]["working"] = f"FAILED: {exc}"
            report["critical"].append(f"Working memory: {exc}")

        # --- Episodic memory (warning) ---
        if self.episodic is None:
            report["layers"]["episodic"] = "disabled"
        else:
            try:
                self.episodic.get_recent_episodes(n=1, project_id=self.project_id)
                report["layers"]["episodic"] = "ok"
            except Exception as exc:
                report["layers"]["episodic"] = f"FAILED: {exc}"
                report["warnings"].append(f"Episodic memory: {exc}")
                logger.warning("HEALTH CHECK: Episodic memory failed: %s", exc)

        # --- Semantic memory (loud warning) ---
        if self.semantic is None:
            report["layers"]["semantic"] = "disabled"
            report["warnings"].append("Semantic memory is disabled — check initialization logs")
            logger.warning("HEALTH CHECK: Semantic memory is disabled")
        else:
            try:
                probe_id = f"__health_probe_{int(time.time())}"
                self.semantic.add_fact(
                    "__health_probe__",
                    confidence=0.0,
                    source="health_check",
                    fact_id=probe_id,
                )
                facts = self.semantic.list_facts(limit=1)
                self.semantic.delete_node("Fact", probe_id)
                report["layers"]["semantic"] = "ok"
                report["layers"]["semantic_backend"] = getattr(self.semantic, "_db_file", "unknown")
            except Exception as exc:
                report["layers"]["semantic"] = f"FAILED: {exc}"
                report["warnings"].append(f"Semantic memory: {exc}")
                logger.warning("HEALTH CHECK: Semantic memory failed probe: %s", exc)

        # --- Daemon (critical) ---
        if not hasattr(self, "_daemon"):
            report["layers"]["daemon"] = "not started"
            report["critical"].append("MemoryDaemon not started")
        elif not self._daemon._thread.is_alive():
            report["layers"]["daemon"] = "DEAD"
            report["critical"].append("MemoryDaemon thread is not alive")
        else:
            report["layers"]["daemon"] = "ok"
            report["layers"]["daemon_stats"] = self._daemon.get_stats()

        # --- Path validation (warning) ---
        for name, path in [
            ("project_dir", self._project_dir),
            ("working_db", self._project_dir / "working.db"),
        ]:
            if not Path(str(path)).is_absolute():
                msg = f"Path not absolute: {name}={path}"
                report["warnings"].append(msg)
                logger.warning("HEALTH CHECK: %s", msg)

        # --- Cognitive layer (warning) ---
        if hasattr(self, "_daemon"):
            cog_stats = self._daemon._cognitive.get_stats()
            if not cog_stats.get("enabled"):
                report["layers"]["cognitive"] = "disabled"
            else:
                report["layers"]["cognitive"] = "ok"

        # --- Raise on critical failures ---
        if report["critical"]:
            raise RuntimeError(
                f"ProjectMemory health check failed for {self.project_id}: "
                + "; ".join(report["critical"])
            )

        # Log summary
        warning_count = len(report["warnings"])
        if warning_count:
            logger.warning(
                "HEALTH CHECK: project=%s passed with %d warning(s): %s",
                self.project_id, warning_count, "; ".join(report["warnings"])
            )
        else:
            logger.info("HEALTH CHECK: project=%s all layers ok", self.project_id)

        return report

    def _build_synthesis_block(
        self,
        query: str,
        max_rules: int = 3,
        max_tokens: int = 300,
        min_match_score: float = -5.0,
    ) -> str:
        """Thin wrapper — delegates to memory.synthesis.build_synthesis_block."""
        return build_synthesis_block(
            self.semantic, self.project_id, query, self._token_counter,
            max_rules=max_rules, max_tokens=max_tokens, min_match_score=min_match_score,
        )


    def synthesize_now(
        self,
        window_size: int = 50,
        days_back: int = 30,
        min_support: int = 3,
        min_confidence: float = 0.60,
    ) -> Dict[str, Any]:
        """Run a synthesis pass — delegates to memory.synthesis.run_synthesis."""
        return run_synthesis(
            self,
            window_size=window_size,
            days_back=days_back,
            min_support=min_support,
            min_confidence=min_confidence,
        )


    def audit_memory(
        self,
        checks: Optional[List[str]] = None,
        stale_days: int = 180,
        confidence_threshold: float = 0.65,
        contradiction_overlap: float = 0.7,
        duplicate_overlap: float = 0.85,
    ):
        """Run a read-only audit pass over memory layers and return a report.

        Six checks: orphan_synthesis, contradicting_facts, stale_facts,
        low_confidence_rules, dangling_relations, near_duplicate_rules.

        Args:
            checks: List of check names to run; None runs all six.
            stale_days: Facts older than this are flagged as stale.
            confidence_threshold: Rules below this confidence are flagged.
            contradiction_overlap: Jaccard threshold for contradiction detection.
            duplicate_overlap: Jaccard threshold for near-duplicate detection.

        Returns:
            AuditReport with findings, summary, and to_markdown() method.
        """
        from .memory.audit import run_audit
        return run_audit(
            semantic=self.semantic,
            episodic=self.episodic,
            project_id=self.project_id,
            checks=checks,
            stale_days=stale_days,
            confidence_threshold=confidence_threshold,
            contradiction_overlap=contradiction_overlap,
            duplicate_overlap=duplicate_overlap,
        )

    def audit_remediate(
        self,
        report,
        actions: Optional[List[tuple]] = None,
        dry_run: bool = True,
    ) -> Dict[str, Any]:
        """Apply approved remediation actions — delegates to memory.audit.run_remediation."""
        return run_remediation(
            self.semantic, self.episodic, self.project_id,
            report=report, actions=actions, dry_run=dry_run,
        )


    def build_prompt_trace(
            self,
            user_message: str,
            *,
            query: str | None = None,
            semantic_query: str | None = None,
            max_prompt_tokens: int | None = None,
            reserve_output_tokens: int = 512,
            include_cold_fallback: bool = True,
            store_overflow_summary: bool = False,
            _result=None,
            _context=None,
            _final_parts=None,
            _available_for_prompt: int | None = None,
            _total_budget: int | None = None,
            _resolved_query: str | None = None,
    ) -> "PromptBuildTrace":
        """Build a prompt trace — delegates to prompt.builder."""
        return build_prompt_trace_core(
            self,
            user_message=user_message,
            query=query,
            semantic_query=semantic_query,
            max_prompt_tokens=max_prompt_tokens,
            reserve_output_tokens=reserve_output_tokens,
            include_cold_fallback=include_cold_fallback,
            store_overflow_summary=store_overflow_summary,
            _result=_result,
            _context=_context,
            _final_parts=_final_parts,
            _available_for_prompt=_available_for_prompt,
            _total_budget=_total_budget,
            _resolved_query=_resolved_query,
        )
