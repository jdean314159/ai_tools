"""Current-Engram probe for baseline versus neural-on evaluation."""

from __future__ import annotations

import shutil
import time
import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import aiohttp

from engram import ProjectMemory, ProjectType, RecallQuery
from engram.embeddings.ollama import OllamaEmbedder

try:
    from .corpus import Fact
    from .eval_config import EvalConfig
except ImportError:  # Direct execution through run_eval.py.
    from corpus import Fact
    from eval_config import EvalConfig


@dataclass
class InjectionResult:
    fact_id: str
    trial: int
    repetition: int
    elapsed_ms: float
    novelty_score: float | None
    novelty_ema: float | None
    novelty_ratio: float | None
    episode_id: str | None
    success: bool
    neural_written: bool | None = None
    error: str | None = None


@dataclass
class RetrievalResult:
    fact_id: str
    query: str
    query_type: str
    top_k: int
    retrieved_chunks: list[str]
    elapsed_ms: float
    success: bool
    error: str | None = None


@dataclass
class GenerationResult:
    fact_id: str
    query: str
    query_type: str
    top_k: int
    answer: str
    elapsed_ms: float
    success: bool
    neural_hint_present: bool
    neural_hint_text: str | None = None
    neural_hint_episodes: list[dict] | None = None
    neural_hint_expected_present: bool | None = None
    neural_hint_stale_present: bool | None = None
    error: str | None = None


class EngramProbe:
    def __init__(
        self,
        config: EvalConfig,
        backend: str,
        storage_dir: str | Path,
    ) -> None:
        config.validate_backend(backend)
        self.config = config
        self.backend = backend
        self.storage_dir = Path(storage_dir)
        self._memory: ProjectMemory | None = None
        self._session_counter = 0
        self._session: aiohttp.ClientSession | None = None
        self._generation_semaphore = asyncio.Semaphore(max(1, int(self.config.judge_concurrency)))
        self._generation_cache: dict[str, str] = {}
        self._generation_cache_path = self.storage_dir.parent / "generation_cache.json"

    async def start(self) -> None:
        # Wipe the persistent memory store so each run starts from empty.
        # This must happen before ProjectMemory is constructed — otherwise
        # accumulated state from previous runs (embeddings, neural weights,
        # episodic store) contaminates the A/B comparison.
        if self.storage_dir.exists():
            shutil.rmtree(self.storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        embedder = OllamaEmbedder(
            model=self.config.embed_model,
            base_url=self.config.embed_base_url,
            timeout=int(self.config.judge_timeout_sec),
        )
        neural_config = None
        if self.backend == "neural_on":
            from engram.neural import NeuralMemoryConfig

            neural_config = NeuralMemoryConfig(
                affinity_weight=self.config.affinity_weight,
                min_warmup_steps=self.config.neural_min_warmup_steps,
                surprise_threshold=self.config.surprise_threshold,
                initialization_seed=self.config.neural_initialization_seed,
                prompt_advisory_enabled=(self.config.neural_prompt_advisory_enabled),
                importance_advisory_enabled=(self.config.neural_importance_advisory_enabled),
            )
            print(
                "[probe] neural affinity weight="
                f"{neural_config.affinity_weight:.3f}; "
                "min warmup steps="
                f"{neural_config.min_warmup_steps}"
            )

        self._memory = ProjectMemory(
            base_dir=self.storage_dir,
            project_id=self.config.project_id,
            project_type=ProjectType.GENERAL_ASSISTANT,
            session_id="eval_session_0",
            embedder=embedder,
            enable_neural=self.backend == "neural_on",
            neural_config=neural_config,
            auto_pair_assistant=False,
            enable_semantic_graph=True,
            total_prompt_tokens=8192,
        )
        if self.config.mode == "generation":
            if self._generation_cache_path.exists():
                self._generation_cache = json.loads(
                    self._generation_cache_path.read_text(encoding="utf-8")
                )
            self._session = aiohttp.ClientSession()

    async def stop(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
        if self._memory is not None:
            self._memory.close()
            self._memory = None

    def warm_layers_from_history(self, replays: int) -> None:
        memory = self._require_memory()
        for _ in range(max(0, int(replays))):
            memory.warm_layers_from_history()
        if memory.neural_layer is not None:
            stats = memory.neural_layer.get_stats()
            print(f"[probe] neural steps after warmup={stats.get('total_steps', 0)}")

    def _require_memory(self) -> ProjectMemory:
        if self._memory is None:
            raise RuntimeError("EngramProbe.start() must be called first")
        return self._memory

    def _read_novelty(self) -> tuple[float | None, float | None, float | None]:
        memory = self._require_memory()
        layer = memory.neural_layer
        if layer is None:
            return None, None, None
        stats = layer.get_stats()
        surprise = stats.get("last_surprise")
        surprise_ema = stats.get("surprise_ema")
        write_ratio = stats.get("write_ratio")
        return (
            float(surprise) if surprise is not None else None,
            float(surprise_ema) if surprise_ema is not None else None,
            float(write_ratio) if write_ratio is not None else None,
        )

    async def inject_fact(
        self,
        fact: Fact,
        use_contradiction: bool = False,
        trial: int = 0,
        repetition: int = 0,
    ) -> InjectionResult:
        text = fact.contradiction if use_contradiction else fact.canonical
        return await self._inject_text(
            fact_id=fact.id,
            text=text,
            metadata={
                "eval_fact_id": fact.id,
                "eval_trial": trial,
                "eval_repetition": repetition,
                "use_contradiction": use_contradiction,
            },
            importance=0.6,
            trial=trial,
            repetition=repetition,
        )

    async def inject_distractor(self, episode_index: int) -> InjectionResult:
        text = (
            f"Distractor {episode_index}: The quarterly budget review showed "
            f"a 3.2% variance in line item {episode_index % 50 + 1}. "
            "The audit committee noted this for follow-up."
        )
        return await self._inject_text(
            fact_id=f"distractor_{episode_index}",
            text=text,
            metadata={
                "eval_distractor": True,
                "distractor_index": episode_index,
            },
            importance=0.3,
            trial=-1,
            repetition=0,
        )

    async def _inject_text(
        self,
        *,
        fact_id: str,
        text: str,
        metadata: dict,
        importance: float,
        trial: int,
        repetition: int,
    ) -> InjectionResult:
        memory = self._require_memory()
        started = time.perf_counter()
        try:
            before_writes = None
            if memory.neural_layer is not None:
                before_writes = int(memory.neural_layer.get_stats().get("total_writes", 0))
            session_id = f"eval_session_{self._session_counter}"
            memory.add_turn("user", text, session_id=session_id)
            memory.add_turn(
                "assistant",
                f"Noted: {text}",
                session_id=session_id,
            )
            novelty_score, novelty_ema, novelty_ratio = self._read_novelty()
            neural_written = None
            if memory.neural_layer is not None and before_writes is not None:
                after_writes = int(memory.neural_layer.get_stats().get("total_writes", 0))
                neural_written = after_writes > before_writes
            episode_id = memory.store_episode(
                text,
                metadata=metadata,
                importance=importance,
                bypass_filter=True,
                bypass_dedup=True,
            )
            return InjectionResult(
                fact_id=fact_id,
                trial=trial,
                repetition=repetition,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                novelty_score=novelty_score,
                novelty_ema=novelty_ema,
                novelty_ratio=novelty_ratio,
                episode_id=episode_id,
                success=bool(episode_id),
                neural_written=neural_written,
            )
        except Exception as exc:
            return InjectionResult(
                fact_id=fact_id,
                trial=trial,
                repetition=repetition,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                novelty_score=None,
                novelty_ema=None,
                novelty_ratio=None,
                episode_id=None,
                success=False,
                neural_written=None,
                error=str(exc),
            )

    async def retrieve(
        self,
        fact: Fact,
        query_type: str,
        top_k: int | None = None,
    ) -> RetrievalResult:
        query = {
            "direct": fact.direct_query,
            "paraphrase": fact.paraphrase_query,
            "decoy": fact.decoy_query,
        }[query_type]
        resolved_top_k = top_k or self.config.retrieve_top_k
        started = time.perf_counter()
        try:
            results = self._require_memory().search_episodes(
                query,
                n=resolved_top_k,
            )
            return RetrievalResult(
                fact_id=fact.id,
                query=query,
                query_type=query_type,
                top_k=resolved_top_k,
                retrieved_chunks=[result.text for result in results],
                elapsed_ms=(time.perf_counter() - started) * 1000,
                success=True,
            )
        except Exception as exc:
            return RetrievalResult(
                fact_id=fact.id,
                query=query,
                query_type=query_type,
                top_k=resolved_top_k,
                retrieved_chunks=[],
                elapsed_ms=(time.perf_counter() - started) * 1000,
                success=False,
                error=str(exc),
            )

    async def answer_query(
        self,
        fact: Fact,
        query_type: str,
        top_k: int | None = None,
        expect_contradiction: bool = False,
    ) -> GenerationResult:
        query = {
            "direct": fact.direct_query,
            "paraphrase": fact.paraphrase_query,
            "decoy": fact.decoy_query,
        }[query_type]
        resolved_top_k = top_k or self.config.retrieve_top_k
        started = time.perf_counter()
        try:
            memory = self._require_memory()
            hint_text = None
            hint_episodes: list[dict] = []
            if memory.neural_layer is not None:
                hint = memory.neural_layer.contribute_to_prompt(
                    RecallQuery(query=query, session_id=memory.session_id)
                )
                if hint is not None:
                    hint_text = hint.text
                    hint_episodes = list(hint.metadata.get("aligned_episodes", []))
            expected_text = fact.contradiction if expect_contradiction else fact.canonical
            stale_text = fact.canonical if expect_contradiction else fact.contradiction
            aligned_texts = {str(item.get("text", "")) for item in hint_episodes}
            built = memory.build_prompt(query)
            prompt = str(built["prompt"])
            hint_present = "[Neural context]" in prompt
            answer = await self._generate(prompt, query)
            return GenerationResult(
                fact_id=fact.id,
                query=query,
                query_type=query_type,
                top_k=resolved_top_k,
                answer=answer,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                success=True,
                neural_hint_present=hint_present,
                neural_hint_text=hint_text,
                neural_hint_episodes=hint_episodes,
                neural_hint_expected_present=expected_text in aligned_texts,
                neural_hint_stale_present=stale_text in aligned_texts,
            )
        except Exception as exc:
            return GenerationResult(
                fact_id=fact.id,
                query=query,
                query_type=query_type,
                top_k=resolved_top_k,
                answer="",
                elapsed_ms=(time.perf_counter() - started) * 1000,
                success=False,
                neural_hint_present=False,
                neural_hint_text=None,
                neural_hint_episodes=[],
                neural_hint_expected_present=None,
                neural_hint_stale_present=None,
                error=str(exc),
            )

    async def _generate(self, prompt: str, query: str) -> str:
        if self._session is None:
            raise RuntimeError("generation session is not started")
        model = self.config.answer_model or self.config.judge_model
        cache_payload = json.dumps(
            [model, prompt, query],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        cache_key = hashlib.sha256(cache_payload.encode("utf-8")).hexdigest()
        cached = self._generation_cache.get(cache_key)
        if cached is not None:
            return cached

        payload = {
            "model": model,
            "stream": False,
            "think": False,
            "keep_alive": -1,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer the question using only the provided context. "
                        "If the context does not contain the answer, say so."
                    ),
                },
                {
                    "role": "user",
                    "content": f"{prompt}\n\nQuestion: {query}",
                },
            ],
            "options": {"temperature": 0.0, "num_predict": 256},
        }
        last_error = None
        async with self._generation_semaphore:
            for attempt in range(self.config.judge_retries + 1):
                try:
                    async with self._session.post(
                        f"{self.config.judge_base_url.rstrip('/')}/api/chat",
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=self.config.judge_timeout_sec),
                    ) as response:
                        data = await response.json()
                        if response.status >= 400:
                            raise RuntimeError(f"Ollama HTTP {response.status}: {data}")
                        answer = str((data.get("message") or {}).get("content", "")).strip()
                        if answer:
                            self._generation_cache[cache_key] = answer
                            self._generation_cache_path.parent.mkdir(
                                parents=True,
                                exist_ok=True,
                            )
                            self._generation_cache_path.write_text(
                                json.dumps(self._generation_cache, indent=2),
                                encoding="utf-8",
                            )
                            return answer
                        last_error = f"empty Ollama response: {data}"
                except (
                    aiohttp.ClientError,
                    asyncio.TimeoutError,
                    RuntimeError,
                ) as exc:
                    last_error = f"{type(exc).__name__}: {exc}"
                if attempt < self.config.judge_retries:
                    await asyncio.sleep(2**attempt)
        raise RuntimeError(last_error or "Ollama generation failed")

    async def reset_working_memory(self) -> None:
        self._session_counter += 1
        self._require_memory().new_session(f"eval_session_{self._session_counter}")
