"""
Engram Memory Eval — Dual-Backend Probe

Supports two backends selected via BACKEND env var or --backend argument:
  - "engram"      : full engram (ProjectMemory with RTRL, ChromaDB, Kuzu)
  - "engram_lite" : engram_lite v0.2 (ProjectMemory with hybrid search, semantic graph)

Usage:
    BACKEND=engram       python run_eval.py ...
    BACKEND=engram_lite  python run_eval.py ...

Key differences between backends:
  - engram:      get_context() for retrieval, RTRL novelty scores available
  - engram_lite: search_episodes() for retrieval, novelty always None (no neural layer)
  - engram_lite: hybrid vector+text search (needs nomic-embed-text in Ollama)
  - engram_lite: semantic graph with fact extraction and forgetting
"""

import os
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

# ── CONFIGURE THESE ───────────────────────────────────────────────────────────
BACKEND = os.environ.get("BACKEND", "engram_lite")   # "engram" or "engram_lite"

# Full engram paths
ENGRAM_SYS_PATH = "/home/cybernaif/ai_tools/engram"
ENGRAM_BASE_DIR = "/home/cybernaif/ai_tools/engram/data/memory_eval_engram"
ENGINE_PROFILE  = "default_local"   # from llm_engines.yaml; None = no engine

# engram_lite paths
ENGRAM_LITE_SYS_PATH = "/home/cybernaif/ai_tools/engram_lite/src"
ENGRAM_LITE_BASE_DIR = "/home/cybernaif/ai_tools/engram/data/memory_eval_lite"
OLLAMA_EMBED_MODEL   = "nomic-embed-text"   # for hybrid search
OLLAMA_BASE_URL      = "http://localhost:11434"

EVAL_PROJECT_ID = "eval_harness"
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class InjectionResult:
    fact_id: str
    trial: int
    repetition: int
    elapsed_ms: float
    novelty_score: Optional[float]
    novelty_ema: Optional[float]
    novelty_ratio: Optional[float]
    episode_id: Optional[str]
    success: bool
    error: Optional[str] = None


@dataclass
class RetrievalResult:
    fact_id: str
    query: str
    query_type: str
    top_k: int
    retrieved_chunks: list
    elapsed_ms: float
    success: bool
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Backend initialisation
# ---------------------------------------------------------------------------

def _init_engram(config):
    """Initialise full engram ProjectMemory."""
    if ENGRAM_SYS_PATH not in sys.path:
        sys.path.insert(0, ENGRAM_SYS_PATH)

    from engram import ProjectMemory, ProjectType
    from engram.rtrl.neural_memory import NeuralMemoryConfig
    from engram.engine import create_failover_engine

    engine = None
    if ENGINE_PROFILE:
        try:
            engine = create_failover_engine(ENGINE_PROFILE)
        except Exception as e:
            print(f"[probe] Warning: engine init failed ({e}); running without neural layer")

    return ProjectMemory(
        project_id=EVAL_PROJECT_ID,
        project_type=ProjectType.GENERAL_ASSISTANT,
        base_dir=Path(ENGRAM_BASE_DIR),
        llm_engine=engine,
        session_id="eval_session_0",
        neural_config=NeuralMemoryConfig(enabled=True),
    )


def _init_engram_lite(config):
    """Initialise engram_lite v0.2 ProjectMemory with hybrid search."""
    if ENGRAM_LITE_SYS_PATH not in sys.path:
        sys.path.insert(0, ENGRAM_LITE_SYS_PATH)

    from engram_lite import ProjectMemory
    from engram_lite.embeddings.ollama import OllamaEmbedder
    from engram_lite.embeddings.cache import EmbeddingCache, CachedEmbedder
    from engram_lite.semantic.extractor import SemanticExtractor
    from engram_lite.semantic.forgetting import ForgettingConfig

    base_dir = Path(ENGRAM_LITE_BASE_DIR)
    base_dir.mkdir(parents=True, exist_ok=True)

    # Embedder with cache
    base_embedder = OllamaEmbedder(
        model=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )
    cache = EmbeddingCache(base_dir / "embedding_cache.db")
    embedder = CachedEmbedder(base_embedder, cache)

    # Pattern-only extractor (no LLM calls during eval)
    extractor = SemanticExtractor(pattern_only=True)

    return ProjectMemory(
        base_dir=base_dir,
        project_id=EVAL_PROJECT_ID,
        session_id="eval_session_0",
        embedder=embedder,
        extractor=extractor,
        auto_pair_assistant=True,
        enable_semantic_graph=True,
        forgetting_config=ForgettingConfig(),
        total_prompt_tokens=8192,
    )


# ---------------------------------------------------------------------------
# Retrieval adapters
# ---------------------------------------------------------------------------

def _retrieve_engram(memory, query: str, top_k: int) -> list[str]:
    """Full engram retrieval via get_context()."""
    context = memory.get_context(query=query, episodic_n=top_k)
    # Episode objects have .text; combine with cold/semantic fallback
    results = [ep.text for ep in (context.episodic or [])]
    # Include cold storage results if episodic came up short
    for row in (context.cold or []):
        text = row.get("text") or str(row)
        if text not in results:
            results.append(text)
    return results[:top_k]


def _retrieve_engram_lite(memory, query: str, top_k: int) -> list[str]:
    """engram_lite retrieval via search_episodes() (hybrid vector+text)."""
    results = memory.search_episodes(query=query, n=top_k)
    return [r.text for r in results]


# ---------------------------------------------------------------------------
# Novelty reader (engram only)
# ---------------------------------------------------------------------------

def _read_novelty_engram(memory) -> tuple:
    nc = getattr(memory, "neural_coord", None)
    if nc is None or not nc.is_warmed_up():
        return None, None, None
    try:
        raw = nc.get_last_surprise()
        ema = nc.get_surprise_ema()
        ratio = (raw / ema) if (ema and ema > 1e-8) else None
        return (
            float(raw) if raw is not None else None,
            float(ema) if ema is not None else None,
            float(ratio) if ratio is not None else None,
        )
    except Exception:
        return None, None, None


# ---------------------------------------------------------------------------
# Main probe class
# ---------------------------------------------------------------------------

class EngramProbe:
    """
    Dual-backend probe. BACKEND env var selects engram or engram_lite.

    API is identical to the original single-backend probe so trial_runner.py
    requires no changes.
    """

    def __init__(self, config):
        self.config = config
        self._memory = None
        self._session_counter = 0
        self._backend = BACKEND
        print(f"[probe] Backend: {self._backend}")

    async def start(self):
        if self._backend == "engram":
            self._memory = _init_engram(self.config)
            self._retrieve = _retrieve_engram
            self._read_novelty = lambda: _read_novelty_engram(self._memory)
        elif self._backend == "engram_lite":
            self._memory = _init_engram_lite(self.config)
            self._retrieve = _retrieve_engram_lite
            self._read_novelty = lambda: (None, None, None)
        else:
            raise ValueError(f"Unknown BACKEND: {self._backend!r}. Use 'engram' or 'engram_lite'.")
        print(f"[probe] Memory initialized: {type(self._memory).__name__}")

    async def stop(self):
        if self._memory:
            self._memory.close()
            self._memory = None

    # ── Injection ─────────────────────────────────────────────────────────────

    async def inject_fact(
        self,
        fact,
        use_contradiction: bool = False,
        trial: int = 0,
        repetition: int = 0,
    ) -> InjectionResult:
        text = fact.contradiction if use_contradiction else fact.canonical
        t0 = time.perf_counter()
        try:
            session_id = f"eval_session_{self._session_counter}"
            if self._backend == "engram":
                # engram: add_turn(role, content) — no session_id parameter
                self._memory.add_turn("user", text)
                self._memory.add_turn("assistant", f"Noted: {text}")
            else:
                self._memory.add_turn("user", text, session_id=session_id)
                self._memory.add_turn("assistant", f"Noted: {text}", session_id=session_id)

            novelty_score, novelty_ema, novelty_ratio = self._read_novelty()

            episode_id = self._memory.store_episode(
                text,
                metadata={
                    "eval_fact_id": fact.id,
                    "eval_trial": trial,
                    "eval_repetition": repetition,
                    "use_contradiction": use_contradiction,
                },
                importance=0.6,
                bypass_filter=True,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            return InjectionResult(
                fact_id=fact.id, trial=trial, repetition=repetition,
                elapsed_ms=elapsed,
                novelty_score=novelty_score, novelty_ema=novelty_ema,
                novelty_ratio=novelty_ratio,
                episode_id=episode_id, success=True,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return InjectionResult(
                fact_id=fact.id, trial=trial, repetition=repetition,
                elapsed_ms=elapsed,
                novelty_score=None, novelty_ema=None, novelty_ratio=None,
                episode_id=None, success=False, error=str(e),
            )

    async def inject_distractor(self, episode_index: int) -> InjectionResult:
        text = (
            f"Distractor {episode_index}: The quarterly budget review showed "
            f"a 3.2% variance in line item {episode_index % 50 + 1}. "
            f"The audit committee noted this for follow-up."
        )
        t0 = time.perf_counter()
        try:
            session_id = f"eval_session_{self._session_counter}"
            if self._backend == "engram":
                self._memory.add_turn("user", text)
                self._memory.add_turn("assistant", "Understood.")
            else:
                self._memory.add_turn("user", text, session_id=session_id)
                self._memory.add_turn("assistant", "Understood.", session_id=session_id)
            novelty_score, novelty_ema, novelty_ratio = self._read_novelty()
            episode_id = self._memory.store_episode(
                text,
                metadata={"eval_distractor": True, "distractor_index": episode_index},
                importance=0.3,
                bypass_filter=True,
            )
            elapsed = (time.perf_counter() - t0) * 1000
            return InjectionResult(
                fact_id=f"distractor_{episode_index}",
                trial=-1, repetition=0, elapsed_ms=elapsed,
                novelty_score=novelty_score, novelty_ema=novelty_ema,
                novelty_ratio=novelty_ratio,
                episode_id=episode_id, success=True,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return InjectionResult(
                fact_id=f"distractor_{episode_index}",
                trial=-1, repetition=0, elapsed_ms=elapsed,
                novelty_score=None, novelty_ema=None, novelty_ratio=None,
                episode_id=None, success=False, error=str(e),
            )

    # ── Retrieval ─────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        fact,
        query_type: str,
        top_k: int = 5,
    ) -> RetrievalResult:
        query = {
            "direct": fact.direct_query,
            "paraphrase": fact.paraphrase_query,
            "decoy": fact.decoy_query,
        }[query_type]

        t0 = time.perf_counter()
        try:
            chunks = self._retrieve(self._memory, query, top_k)
            elapsed = (time.perf_counter() - t0) * 1000
            return RetrievalResult(
                fact_id=fact.id, query=query, query_type=query_type,
                top_k=top_k, retrieved_chunks=chunks,
                elapsed_ms=elapsed, success=True,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            return RetrievalResult(
                fact_id=fact.id, query=query, query_type=query_type,
                top_k=top_k, retrieved_chunks=[],
                elapsed_ms=elapsed, success=False, error=str(e),
            )

    # ── Session management ────────────────────────────────────────────────────

    async def reset_working_memory(self):
        self._session_counter += 1
        new_session_id = f"eval_session_{self._session_counter}"
        self._memory.new_session(new_session_id)
        print(f"[probe] New session: {new_session_id}")