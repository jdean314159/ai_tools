"""Local Ollama retrieval judge with bounded retry behavior."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

import aiohttp

try:
    from .corpus import Fact
    from .engram_probe import GenerationResult, RetrievalResult
except ImportError:  # Direct execution through run_eval.py.
    from corpus import Fact
    from engram_probe import GenerationResult, RetrievalResult

JUDGE_SYSTEM = (
    "You are a strict memory evaluation judge. Return only one JSON object "
    "without markdown or commentary."
)

JUDGE_PROMPT = """
EXPECTED CURRENT FACT:
{expected}

EXPECTED SNIPPET:
{expected_snippet}

STALE OR CONTRADICTING FACT:
{stale_fact}

QUERY:
{query}

QUERY TYPE: {query_type}

RETRIEVED CHUNKS:
{chunks}

Return:
{{
  "retrieved": true|false,
  "relevance": 0-5,
  "contaminated": true|false,
  "verbatim_match": true|false,
  "notes": "one sentence"
}}

For direct or paraphrase queries, retrieved means the expected current fact is
present conceptually. contaminated means a stale or contradicting claim is
returned as support. For a decoy query, retrieved means the target fact was
erroneously returned; correct decoy behavior is retrieved=false.
"""

GENERATION_JUDGE_PROMPT = """
EXPECTED CURRENT FACT:
{expected}

EXPECTED SNIPPET:
{expected_snippet}

STALE OR CONTRADICTING FACT:
{stale_fact}

QUERY:
{query}

QUERY TYPE: {query_type}

GENERATED ANSWER:
{answer}

Return:
{{
  "retrieved": true|false,
  "relevance": 0-5,
  "contaminated": true|false,
  "verbatim_match": true|false,
  "notes": "one sentence"
}}

For direct or paraphrase queries, retrieved means the answer correctly states
the expected current fact. contaminated means it asserts the stale or
contradicting fact. For a decoy query, retrieved means the answer asserts the
false premise; correct behavior is to decline because the information is not
available.
"""


@dataclass
class JudgmentResult:
    fact_id: str
    trial: int
    query_type: str
    top_k: int
    retrieved: bool
    relevance: int
    contaminated: bool
    verbatim_match: bool
    notes: str
    judge_error: str | None = None

    @property
    def correct(self) -> bool:
        return not self.retrieved if self.query_type == "decoy" else self.retrieved

    def as_dict(self) -> dict:
        return {
            "fact_id": self.fact_id,
            "trial": self.trial,
            "query_type": self.query_type,
            "top_k": self.top_k,
            "retrieved": self.retrieved,
            "relevance": self.relevance,
            "contaminated": self.contaminated,
            "verbatim_match": self.verbatim_match,
            "correct": self.correct,
            "notes": self.notes,
            "judge_error": self.judge_error,
        }


class OllamaJudge:
    def __init__(
        self,
        *,
        model: str = "qwen3:8b",
        base_url: str = "http://localhost:11434",
        max_tokens: int = 384,
        timeout_sec: float = 120.0,
        retries: int = 2,
        concurrency: int = 4,
        cache_path: str | Path | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_tokens = int(max_tokens)
        self.timeout_sec = float(timeout_sec)
        self.retries = max(0, int(retries))
        self._session: aiohttp.ClientSession | None = None
        self._semaphore = asyncio.Semaphore(max(1, int(concurrency)))
        self._cache_path = Path(cache_path) if cache_path is not None else None
        self._cache: dict[str, dict] = {}

    async def start(self) -> None:
        if self._cache_path is not None and self._cache_path.exists():
            self._cache = json.loads(self._cache_path.read_text(encoding="utf-8"))
        self._session = aiohttp.ClientSession()

    async def stop(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    async def judge(
        self,
        fact: Fact,
        result: RetrievalResult | GenerationResult,
        trial: int,
        *,
        expect_contradiction: bool = False,
    ) -> JudgmentResult:
        if not result.success:
            return self._failed(
                fact,
                result,
                trial,
                f"Probe failed: {result.error or 'unknown error'}",
            )

        expected = fact.contradiction if expect_contradiction else fact.canonical
        stale = fact.canonical if expect_contradiction else fact.contradiction
        expected_snippet = expected if expect_contradiction else fact.expected_snippet
        mode = "generation" if isinstance(result, GenerationResult) else "retrieval"
        evidence = (
            result.answer
            if isinstance(result, GenerationResult)
            else "\n---\n".join(result.retrieved_chunks)
        )
        cache_key = self._cache_key(
            result.query,
            evidence,
            expected_snippet,
            mode,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return JudgmentResult(
                fact_id=fact.id,
                trial=trial,
                query_type=result.query_type,
                top_k=result.top_k,
                retrieved=bool(cached["retrieved"]),
                relevance=int(cached["relevance"]),
                contaminated=bool(cached["contaminated"]),
                verbatim_match=bool(cached["verbatim_match"]),
                notes=str(cached["notes"]),
            )

        if isinstance(result, GenerationResult):
            prompt = GENERATION_JUDGE_PROMPT.format(
                expected=expected,
                expected_snippet=expected_snippet,
                stale_fact=stale,
                query=result.query,
                query_type=result.query_type,
                answer=result.answer or "(no answer returned)",
            )
        else:
            prompt = JUDGE_PROMPT.format(
                expected=expected,
                expected_snippet=expected_snippet,
                stale_fact=stale,
                query=result.query,
                query_type=result.query_type,
                chunks=evidence or "(no chunks returned)",
            )

        async with self._semaphore:
            raw, error = await self._call_ollama(f"/no_think\n{JUDGE_SYSTEM}\n\n{prompt}")
        if raw is None:
            return self._failed(fact, result, trial, error or "Ollama call failed")

        try:
            parsed = json.loads(self._extract_json(raw))
            result = JudgmentResult(
                fact_id=fact.id,
                trial=trial,
                query_type=result.query_type,
                top_k=result.top_k,
                retrieved=bool(parsed.get("retrieved", False)),
                relevance=max(0, min(5, int(parsed.get("relevance", 0)))),
                contaminated=bool(parsed.get("contaminated", False)),
                verbatim_match=bool(parsed.get("verbatim_match", False)),
                notes=str(parsed.get("notes", "")),
            )
            self._cache[cache_key] = {
                "retrieved": result.retrieved,
                "relevance": result.relevance,
                "contaminated": result.contaminated,
                "verbatim_match": result.verbatim_match,
                "notes": result.notes,
            }
            self._persist_cache()
            return result
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            return self._failed(
                fact,
                result,
                trial,
                f"Parse error: {exc}; raw={raw[:200]!r}",
            )

    async def _call_ollama(self, prompt: str) -> tuple[str | None, str | None]:
        if self._session is None:
            raise RuntimeError("OllamaJudge.start() must be called first")
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "format": "json",
            "keep_alive": -1,
            "options": {
                "temperature": 0.0,
                "num_predict": self.max_tokens,
            },
        }
        last_error = None
        for attempt in range(self.retries + 1):
            try:
                async with self._session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_sec),
                ) as response:
                    data = await response.json()
                    if response.status >= 400:
                        raise RuntimeError(f"Ollama HTTP {response.status}: {data}")
                    raw = str(data.get("response", "")).strip()
                    if raw:
                        return raw, None
                    last_error = f"empty Ollama response: {data}"
            except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as exc:
                last_error = str(exc)
            if attempt < self.retries:
                await asyncio.sleep(2**attempt)
        return None, last_error

    @staticmethod
    def _cache_key(
        query_text: str,
        retrieved_text: str,
        expected_snippet: str,
        mode: str = "retrieval",
    ) -> str:
        payload = json.dumps(
            [mode, query_text, retrieved_text, expected_snippet],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _persist_cache(self) -> None:
        if self._cache_path is None:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(self._cache, indent=2),
            encoding="utf-8",
        )

    async def judge_batch(
        self,
        facts: list[Fact],
        results: list[RetrievalResult | GenerationResult],
        trial: int,
        contradicted_ids: set[str],
    ) -> list[JudgmentResult]:
        return await asyncio.gather(
            *[
                self.judge(
                    fact,
                    result,
                    trial,
                    expect_contradiction=fact.id in contradicted_ids,
                )
                for fact, result in zip(facts, results)
            ]
        )

    @staticmethod
    def _extract_json(raw: str) -> str:
        without_thinking = re.sub(
            r"<think>.*?</think>",
            "",
            raw,
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()
        if "```" in without_thinking:
            parts = [
                part.strip().removeprefix("json").strip() for part in without_thinking.split("```")
            ]
            without_thinking = next(
                (part for part in parts if part.startswith("{")),
                without_thinking,
            )
        start = without_thinking.find("{")
        end = without_thinking.rfind("}")
        return (
            without_thinking[start : end + 1] if start >= 0 and end >= start else without_thinking
        )

    @staticmethod
    def _failed(
        fact: Fact,
        result: RetrievalResult | GenerationResult,
        trial: int,
        error: str,
    ) -> JudgmentResult:
        return JudgmentResult(
            fact_id=fact.id,
            trial=trial,
            query_type=result.query_type,
            top_k=result.top_k,
            retrieved=False,
            relevance=0,
            contaminated=False,
            verbatim_match=False,
            notes="",
            judge_error=error,
        )
