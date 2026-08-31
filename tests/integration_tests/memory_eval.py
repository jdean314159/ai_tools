from __future__ import annotations

import argparse
import json
import tempfile

from llm_harness_core import EvaluatorRequest, SubstringMatchEvaluator
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence


@dataclass(frozen=True)
class SeedTurn:
    role: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryProbe:
    name: str
    query: str
    expected_substrings: Sequence[str] = ()
    forbidden_substrings: Sequence[str] = ()
    question: str | None = None
    min_expected_hits: int = 1
    max_forbidden_hits: int = 0
    category: str = "generic"
    notes: str = ""


@dataclass(frozen=True)
class MemoryEvalScenario:
    name: str
    seed_turns: Sequence[SeedTurn]
    probes: Sequence[MemoryProbe]


DEFAULT_SCENARIO = MemoryEvalScenario(
    name="default_memory_quality",
    seed_turns=(
        SeedTurn(
            role="user",
            text="Important: remember that I prefer Python over Java for quick scripts.",
        ),
        SeedTurn(
            role="user",
            text="Important: we decided to use SQLite for the local semantic memory store.",
        ),
        SeedTurn(
            role="user",
            text="Project decision: use SQLite for the local semantic memory store.",
        ),
        SeedTurn(
            role="user",
            text="Correction: for analytics, use DuckDB locally instead of SQLite.",
        ),
        SeedTurn(
            role="user",
            text="Update: the weekly architecture review has moved to Wednesday at 2 PM, not Tuesday.",
        ),
        SeedTurn(
            role="user",
            text="For this message only, greet me cheerfully.",
        ),
        SeedTurn(
            role="assistant",
            text="You should maybe add comments everywhere.",
        ),
    ),
    probes=(
        MemoryProbe(
            name="preference_recall",
            category="signal",
            query="preferred language for quick scripts",
            expected_substrings=("python",),
            forbidden_substrings=("cheerfully", "comments everywhere"),
            question="What language do I prefer for quick scripts?",
            notes="Durable user preference should survive into long-term memory.",
        ),
        MemoryProbe(
            name="preference_paraphrase",
            category="paraphrase",
            query="Which programming language do I reach for when hacking together short utilities?",
            expected_substrings=("python",),
            forbidden_substrings=("cheerfully", "comments everywhere"),
            question="When I am putting together a short utility, which language should you assume I prefer?",
            notes="Paraphrased retrieval should still surface the durable user preference.",
        ),
        MemoryProbe(
            name="decision_recall",
            category="signal",
            query="local semantic memory store decision",
            expected_substrings=("sqlite", "semantic memory"),
            forbidden_substrings=("cheerfully", "comments everywhere"),
            question="What local semantic memory store did we decide to use?",
            notes="Stable technical decision should be retrievable without duplicate clutter.",
        ),
        MemoryProbe(
            name="decision_decoy",
            category="decoy",
            query="Which local database did we choose for analytics?",
            expected_substrings=("duckdb",),
            forbidden_substrings=("sqlite for analytics",),
            question="What local database should we use for analytics?",
            notes="Related but distinct retrieval should prefer the analytics update rather than contaminating from the semantic-store decision.",
        ),
        MemoryProbe(
            name="update_resolution",
            category="update",
            query="weekly architecture review time",
            expected_substrings=("wednesday", "2 pm"),
            forbidden_substrings=("tuesday",),
            question="When is the weekly architecture review now scheduled?",
            notes="Updated facts should dominate stale earlier versions.",
        ),
        MemoryProbe(
            name="ephemeral_rejection",
            category="noise",
            query="greet cheerfully for this message only",
            expected_substrings=(),
            forbidden_substrings=("cheerfully",),
            question=None,
            min_expected_hits=0,
            max_forbidden_hits=0,
            notes="Ephemeral one-shot instruction should not become long-term memory.",
        ),
        MemoryProbe(
            name="assistant_chatter_rejection",
            category="noise",
            query="add comments everywhere",
            expected_substrings=(),
            forbidden_substrings=("comments everywhere",),
            question=None,
            min_expected_hits=0,
            max_forbidden_hits=0,
            notes="Generic assistant chatter should not dominate long-term recall.",
        ),
    ),
)


STRESS_SCENARIO = MemoryEvalScenario(
    name="stress_memory_quality",
    seed_turns=(
        SeedTurn(
            role="user",
            text="Important: remember that I prefer Python over Java for quick scripts and one-off tools.",
        ),
        SeedTurn(
            role="user",
            text="Preference: keep durable project docs in Markdown files committed to the repo, not in Google Docs.",
        ),
        SeedTurn(role="user", text="Decision: use SQLite for the local semantic memory store."),
        SeedTurn(
            role="user", text="Correction: for analytics, use DuckDB locally instead of SQLite."
        ),
        SeedTurn(
            role="user",
            text="Decision: for local experimentation, use DuckDB analytics notebooks rather than pandas-only CSV workflows.",
        ),
        SeedTurn(
            role="user",
            text="Update: the weekly architecture review has moved to Wednesday at 2 PM, not Tuesday.",
        ),
        SeedTurn(
            role="user",
            text="Update: deploy the nightly evaluation job in us-west-2, not us-east-1.",
        ),
        SeedTurn(
            role="user",
            text="Correction: for long batch summaries, prefer qwen3:32b instead of qwen3:8b.",
        ),
        SeedTurn(
            role="user", text="Decision: sandbox command execution through docker when available."
        ),
        SeedTurn(role="user", text="For this message only, answer in pirate style."),
        SeedTurn(
            role="user",
            text="Transient note: I am only asking about Tuesday because I was mistaken.",
        ),
        SeedTurn(role="assistant", text="You should probably add comments everywhere."),
        SeedTurn(role="assistant", text="A good default is SQLite for analytics dashboards."),
        SeedTurn(role="assistant", text="Maybe store docs in a wiki so the repo stays clean."),
        SeedTurn(
            role="user",
            text="Noise: a past analytics prototype used SQLite, but that is no longer the decision for current analytics work.",
        ),
        SeedTurn(
            role="user",
            text="Historical note: the architecture review used to be on Tuesday morning before the schedule changed.",
        ),
        SeedTurn(
            role="user",
            text="Historical note: an older deployment plan mentioned us-east-1, but that is obsolete.",
        ),
    ),
    probes=(
        MemoryProbe(
            name="stress_preference_recall",
            category="signal",
            query="preferred language for one-off tools",
            expected_substrings=("python",),
            forbidden_substrings=("pirate", "comments everywhere"),
            question="What language should you assume I prefer for one-off tools?",
            notes="Durable technical preference should survive amidst unrelated clutter.",
        ),
        MemoryProbe(
            name="stress_preference_paraphrase",
            category="paraphrase",
            query="When I hack together a small utility, which language should you expect?",
            expected_substrings=("python",),
            forbidden_substrings=("pirate",),
            question="When I am writing a small utility quickly, what language should you default to?",
            notes="Paraphrase retrieval should remain robust in a denser corpus.",
        ),
        MemoryProbe(
            name="stress_docs_decision",
            category="signal",
            query="Where should durable project documentation live?",
            expected_substrings=("markdown", "repo"),
            forbidden_substrings=("google docs", "wiki"),
            question="Where should durable project documentation live?",
            notes="Stable documentation policy should defeat wiki/Google Docs decoys.",
        ),
        MemoryProbe(
            name="stress_analytics_decoy",
            category="decoy",
            query="Which local database should analytics work use?",
            expected_substrings=("duckdb",),
            forbidden_substrings=("sqlite for analytics",),
            question="Which local database should analytics work use?",
            notes="Analytics update should beat related SQLite decoys.",
        ),
        MemoryProbe(
            name="stress_schedule_update",
            category="update",
            query="When is the architecture review now scheduled?",
            expected_substrings=("wednesday", "2 pm"),
            forbidden_substrings=("tuesday",),
            question="When is the architecture review now scheduled?",
            notes="Updated meeting time should dominate the older Tuesday note.",
        ),
        MemoryProbe(
            name="stress_region_update",
            category="update",
            query="Which region should the nightly evaluation job use?",
            expected_substrings=("us-west-2",),
            forbidden_substrings=("us-east-1",),
            question="Which region should the nightly evaluation job use?",
            notes="Updated deployment region should beat the historical us-east-1 plan.",
        ),
        MemoryProbe(
            name="stress_model_update",
            category="update",
            query="Which model should handle long batch summaries?",
            expected_substrings=("qwen3:32b",),
            forbidden_substrings=("qwen3:8b",),
            question="Which model should handle long batch summaries?",
            notes="Updated batch-summary model choice should be retrievable as a current preference.",
        ),
        MemoryProbe(
            name="stress_sandbox_decision",
            category="signal",
            query="How should command execution be sandboxed when possible?",
            expected_substrings=("docker",),
            forbidden_substrings=("comments everywhere",),
            question="How should command execution be sandboxed when possible?",
            notes="Agent-safety decision should remain available as a durable technical policy.",
        ),
        MemoryProbe(
            name="stress_ephemeral_rejection",
            category="noise",
            query="answer in pirate style",
            expected_substrings=(),
            forbidden_substrings=("pirate",),
            question=None,
            min_expected_hits=0,
            max_forbidden_hits=0,
            notes="One-shot stylistic request should not persist as long-term memory.",
        ),
        MemoryProbe(
            name="stress_assistant_chatter_rejection",
            category="noise",
            query="add comments everywhere",
            expected_substrings=(),
            forbidden_substrings=("comments everywhere",),
            question=None,
            min_expected_hits=0,
            max_forbidden_hits=0,
            notes="Assistant chatter should not turn into durable memory.",
        ),
    ),
)


SCENARIOS: dict[str, MemoryEvalScenario] = {
    "default": DEFAULT_SCENARIO,
    "stress": STRESS_SCENARIO,
}


class _FakeEngine:
    model_name = "memory-eval-engine"
    system_prompt = "You are a memory evaluation harness."
    is_cloud = False
    max_context_length = 4096

    def count_tokens(self, text: str) -> int:
        return max(1, len((text or "").split()))

    def compress_prompt(self, prompt: str, target_tokens: int) -> str:
        words = (prompt or "").split()
        if len(words) <= target_tokens:
            return prompt
        return " ".join(words[:target_tokens])


class AnswerClient(Protocol):
    def answer(self, prompt: str, *, question: str | None = None) -> str: ...


class OpenAICompatibleAnswerClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_seconds: float = 60.0,
        temperature: float = 0.0,
        max_tokens: int = 128,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens

    def answer(self, prompt: str, *, question: str | None = None) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": "Answer briefly and directly. Use the provided context if relevant.",
                },
                {"role": "user", "content": prompt},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}),
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except (
            urllib.error.HTTPError
        ) as exc:  # pragma: no cover - exercised only with external service
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"OpenAI-compatible model request failed: {exc.code} {detail}"
            ) from exc
        except (
            urllib.error.URLError
        ) as exc:  # pragma: no cover - exercised only with external service
            raise RuntimeError(f"OpenAI-compatible model request failed: {exc}") from exc

        parsed = json.loads(body)
        choices = parsed.get("choices") or []
        if not choices:
            raise RuntimeError(f"OpenAI-compatible model request returned no choices: {parsed}")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            return " ".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            ).strip()
        return str(content or "").strip()


@dataclass(frozen=True)
class AnswerEval:
    probe: str
    baseline_answer: str
    memory_answer: str
    baseline_passed: bool
    memory_passed: bool
    uplift: int
    evaluator: str
    baseline_score: float | None = None
    memory_score: float | None = None
    baseline_rationale: str | None = None
    memory_rationale: str | None = None


class BackendAdapter:
    backend_name: str

    def seed_turn(self, turn: SeedTurn) -> None:
        raise NotImplementedError

    def flush(self) -> None:
        return None

    def reopen_cold(self) -> "BackendAdapter":
        raise NotImplementedError

    def get_stats(self) -> dict[str, Any]:
        raise NotImplementedError

    def get_context(self, query: str) -> Any:
        raise NotImplementedError

    def build_prompt(self, question: str, *, query: str | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def close(self) -> None:
        return None


class EngramBasicAdapter(BackendAdapter):
    backend_name = "basic"

    def __init__(self, base_dir: Path, project_id: str = "memory_eval", session_id: str = "seed"):
        from engram import ProjectMemory

        self.base_dir = Path(base_dir)
        self.project_id = project_id
        self.session_id = session_id
        self.memory = ProjectMemory(
            base_dir=self.base_dir,
            project_id=self.project_id,
            session_id=self.session_id,
        )

    def seed_turn(self, turn: SeedTurn) -> None:
        self.memory.add_turn(turn.role, turn.text, session_id=self.session_id)

    def reopen_cold(self) -> "EngramBasicAdapter":
        return EngramBasicAdapter(self.base_dir, project_id=self.project_id, session_id="cold")

    def get_stats(self) -> dict[str, Any]:
        return self.memory.get_stats()

    def get_context(self, query: str) -> Any:
        result = self.memory.build_prompt("probe", query=query, return_trace=False)
        return result.get("context")

    def build_prompt(self, question: str, *, query: str | None = None) -> dict[str, Any]:
        return self.memory.build_prompt(question, query=query, return_trace=False)

    def close(self) -> None:
        self.memory.close()


class EngramFullAdapter(BackendAdapter):
    backend_name = "full"

    def __init__(self, base_dir: Path, project_id: str = "memory_eval", session_id: str = "seed"):
        from engram import ProjectMemory

        self.base_dir = Path(base_dir)
        self.project_id = project_id
        self.session_id = session_id
        self.memory = ProjectMemory(
            project_id=self.project_id,
            project_type="general",
            base_dir=self.base_dir,
            session_id=self.session_id,
            llm_engine=_FakeEngine(),
            total_prompt_tokens=1200,
        )

    def seed_turn(self, turn: SeedTurn) -> None:
        self.memory.add_turn(turn.role, turn.text, session_id=self.session_id)

    def flush(self) -> None:
        queue = getattr(getattr(self.memory, "_event_bus", None), "_queue", None)
        if queue is not None:
            queue.join()
        time.sleep(0.25)

    def reopen_cold(self) -> "EngramFullAdapter":
        return EngramFullAdapter(self.base_dir, project_id=self.project_id, session_id="cold")

    def get_stats(self) -> dict[str, Any]:
        snapshot = self.memory.get_stats()
        episodic_count = 0
        episodic = getattr(self.memory, "episodic", None)
        if episodic is not None:
            try:
                episodic_count = len(self.memory.search_episodes("", n=100))
            except Exception:
                episodic_count = 0
        return {
            "backend": self.backend_name,
            "working": {"message_count": len(self.memory.get_recent_turns(self.session_id, 20))},
            "episodic": {"count": episodic_count},
            "semantic": snapshot.get("semantic", {}),
            "cold": snapshot.get("cold", {}),
            "config": snapshot.get("budget", {}),
        }

    def get_context(self, query: str) -> Any:
        result = self.memory.build_prompt(
            "probe", query=query, max_prompt_tokens=900, return_trace=False
        )
        return result.get("context")

    def build_prompt(self, question: str, *, query: str | None = None) -> dict[str, Any]:
        return self.memory.build_prompt(question, query=query, max_prompt_tokens=900)

    def close(self) -> None:
        self.memory.close()


def _resolve_scenario(scenario: str | MemoryEvalScenario) -> MemoryEvalScenario:
    if isinstance(scenario, MemoryEvalScenario):
        return scenario
    if scenario not in SCENARIOS:
        raise KeyError(f"Unknown scenario '{scenario}'. Available: {', '.join(sorted(SCENARIOS))}")
    return SCENARIOS[scenario]


def _safe_text(item: Any) -> str:
    for attr in ("text", "content", "message", "value"):
        if hasattr(item, attr):
            try:
                value = getattr(item, attr)
                if isinstance(value, str) and value.strip():
                    return value
            except Exception:
                pass
    if isinstance(item, dict):
        for key in ("text", "content", "message", "value", "summary", "detail"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return str(item)


def _collect_layer_items(context: Any) -> dict[str, list[str]]:
    if context is None:
        return {"working": [], "episodic": [], "semantic": [], "cold": []}
    result: dict[str, list[str]] = {}
    for layer in ("working", "episodic", "semantic", "cold"):
        value = getattr(context, layer, None)
        if value is None and isinstance(context, dict):
            value = context.get(layer)
        if value is None:
            result[layer] = []
            continue
        if not isinstance(value, list):
            value = [value]
        result[layer] = [text for item in value if (text := _safe_text(item).strip())]
    return result


def _flatten_layer_items(layer_items: dict[str, list[str]]) -> list[str]:
    flat: list[str] = []
    for layer in ("working", "episodic", "semantic", "cold"):
        flat.extend(layer_items.get(layer, []))
    return flat


def _similarity(a: str, b: str) -> float:
    import difflib

    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _redundancy_ratio(items: Sequence[str]) -> float:
    if len(items) < 2:
        return 0.0
    near_duplicate_pairs = 0
    total_pairs = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            total_pairs += 1
            if _similarity(items[i], items[j]) >= 0.82:
                near_duplicate_pairs += 1
    return round(near_duplicate_pairs / max(1, total_pairs), 3)


_SUBSTRING_EVALUATOR = SubstringMatchEvaluator()


def _score_text_against_probe(text: str, probe: MemoryProbe) -> dict[str, Any]:
    result = _SUBSTRING_EVALUATOR.evaluate(
        EvaluatorRequest(
            candidate=text or "",
            expected_texts=tuple(probe.expected_substrings),
            forbidden_texts=tuple(probe.forbidden_substrings),
            min_expected_hits=probe.min_expected_hits,
            max_forbidden_hits=probe.max_forbidden_hits,
            metadata={"probe": probe.name, "category": probe.category},
        )
    )
    if not result.ok or result.value is None:
        return {
            "expected_hits": [],
            "forbidden_hits": [],
            "passed": False,
            "evaluator": _SUBSTRING_EVALUATOR.name,
            "score": 0.0,
        }
    return {
        "expected_hits": list(result.value.details.get("expected_hits", [])),
        "forbidden_hits": list(result.value.details.get("forbidden_hits", [])),
        "passed": bool(result.value.passed),
        "evaluator": result.value.evaluator,
        "score": result.value.score,
        "rationale": result.value.rationale,
    }


def _evaluate_answer_support(
    adapter: BackendAdapter,
    probe: MemoryProbe,
    *,
    answer_client: AnswerClient | None,
) -> AnswerEval | None:
    if answer_client is None or not probe.question:
        return None

    baseline_prompt = f"Answer briefly and directly.\n\nQuestion: {probe.question}"
    memory_prompt_result = adapter.build_prompt(probe.question, query=probe.query)
    memory_prompt = f"{memory_prompt_result.get('prompt', '')}\n\nAnswer briefly and directly."

    baseline_answer = answer_client.answer(baseline_prompt, question=probe.question)
    memory_answer = answer_client.answer(memory_prompt, question=probe.question)

    baseline_score = _score_text_against_probe(baseline_answer, probe)
    memory_score = _score_text_against_probe(memory_answer, probe)
    uplift = int(memory_score["passed"]) - int(baseline_score["passed"])
    evaluator_name = str(
        memory_score.get("evaluator")
        or baseline_score.get("evaluator")
        or _SUBSTRING_EVALUATOR.name
    )
    return AnswerEval(
        probe=probe.name,
        baseline_answer=baseline_answer,
        memory_answer=memory_answer,
        baseline_passed=bool(baseline_score["passed"]),
        memory_passed=bool(memory_score["passed"]),
        uplift=uplift,
        evaluator=evaluator_name,
        baseline_score=float(baseline_score.get("score", 0.0)),
        memory_score=float(memory_score.get("score", 0.0)),
        baseline_rationale=baseline_score.get("rationale"),
        memory_rationale=memory_score.get("rationale"),
    )


def evaluate_probe(
    adapter: BackendAdapter,
    probe: MemoryProbe,
    *,
    answer_client: AnswerClient | None = None,
) -> dict[str, Any]:
    context = adapter.get_context(probe.query)
    layer_items = _collect_layer_items(context)
    all_items = _flatten_layer_items(layer_items)
    haystack = "\n".join(all_items).lower()

    expected_hits = [needle for needle in probe.expected_substrings if needle.lower() in haystack]
    forbidden_hits = [needle for needle in probe.forbidden_substrings if needle.lower() in haystack]
    raw_passed = (
        len(expected_hits) >= probe.min_expected_hits
        and len(forbidden_hits) <= probe.max_forbidden_hits
    )

    result = {
        "probe": probe.name,
        "category": probe.category,
        "query": probe.query,
        "expected_hits": expected_hits,
        "forbidden_hits": forbidden_hits,
        "expected_total": len(probe.expected_substrings),
        "min_expected_hits": probe.min_expected_hits,
        "raw_passed": raw_passed,
        "passed": raw_passed,
        "pass_basis": "raw_retrieval",
        "layers": {key: len(value) for key, value in layer_items.items()},
        "retrieved_items": all_items,
        "redundancy_ratio": _redundancy_ratio(all_items),
        "notes": probe.notes,
    }

    if probe.question:
        prompt_result = adapter.build_prompt(probe.question, query=probe.query)
        prompt = str(prompt_result.get("prompt", ""))
        prompt_score = _score_text_against_probe(prompt, probe)
        result["prompt_support"] = {
            "question": probe.question,
            **prompt_score,
            "prompt_tokens": int(prompt_result.get("prompt_tokens", 0) or 0),
            "memory_tokens": int(prompt_result.get("memory_tokens", 0) or 0),
        }
        result["passed"] = bool(prompt_score["passed"])
        result["pass_basis"] = "prompt_effective_memory"

    answer_eval = _evaluate_answer_support(adapter, probe, answer_client=answer_client)
    if answer_eval is not None:
        result["answer_eval"] = asdict(answer_eval)

    return result


def summarize_backend(
    backend_name: str, stats: dict[str, Any], probe_results: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    passed = [item for item in probe_results if item.get("passed")]
    raw_passed = [item for item in probe_results if item.get("raw_passed")]
    prompt_results = [
        item.get("prompt_support")
        for item in probe_results
        if item.get("prompt_support") is not None
    ]
    prompt_passed = [item for item in prompt_results if item and item.get("passed")]

    categories = {
        "signal": [item for item in probe_results if item.get("category") == "signal"],
        "paraphrase": [item for item in probe_results if item.get("category") == "paraphrase"],
        "decoy": [item for item in probe_results if item.get("category") == "decoy"],
        "update": [item for item in probe_results if item.get("category") == "update"],
        "noise": [item for item in probe_results if item.get("category") == "noise"],
    }

    def _rate(items: Sequence[dict[str, Any]]) -> float | None:
        if not items:
            return None
        return round(sum(1 for item in items if item.get("passed")) / len(items), 3)

    answer_results = [
        item.get("answer_eval") for item in probe_results if item.get("answer_eval") is not None
    ]
    avg_redundancy = sum(float(item.get("redundancy_ratio", 0.0)) for item in probe_results) / max(
        1, len(probe_results)
    )
    answer_baseline_rate = None
    answer_memory_rate = None
    answer_net_uplift = None
    answer_positive_uplift_rate = None
    answer_regression_rate = None
    if answer_results:
        answer_baseline_rate = round(
            sum(1 for item in answer_results if item and item.get("baseline_passed"))
            / len(answer_results),
            3,
        )
        answer_memory_rate = round(
            sum(1 for item in answer_results if item and item.get("memory_passed"))
            / len(answer_results),
            3,
        )
        answer_net_uplift = round(answer_memory_rate - answer_baseline_rate, 3)
        answer_positive_uplift_rate = round(
            sum(1 for item in answer_results if item and int(item.get("uplift", 0)) > 0)
            / len(answer_results),
            3,
        )
        answer_regression_rate = round(
            sum(1 for item in answer_results if item and int(item.get("uplift", 0)) < 0)
            / len(answer_results),
            3,
        )

    return {
        "backend": backend_name,
        "stats": stats,
        "probe_pass_rate": round(len(passed) / max(1, len(probe_results)), 3),
        "raw_probe_pass_rate": round(len(raw_passed) / max(1, len(probe_results)), 3),
        "prompt_pass_rate": round(len(prompt_passed) / max(1, len(prompt_results)), 3)
        if prompt_results
        else None,
        "signal_retention_rate": _rate(categories["signal"]),
        "paraphrase_retention_rate": _rate(categories["paraphrase"]),
        "decoy_rejection_rate": _rate(categories["decoy"]),
        "update_resolution_rate": _rate(categories["update"]),
        "noise_rejection_rate": _rate(categories["noise"]),
        "avg_redundancy_ratio": round(avg_redundancy, 3),
        "answer_baseline_pass_rate": answer_baseline_rate,
        "answer_memory_pass_rate": answer_memory_rate,
        "answer_net_uplift": answer_net_uplift,
        "answer_positive_uplift_rate": answer_positive_uplift_rate,
        "answer_regression_rate": answer_regression_rate,
        "failed_probes": [item["probe"] for item in probe_results if not item.get("passed")],
        "failed_raw_probes": [
            item["probe"] for item in probe_results if not item.get("raw_passed")
        ],
    }


def run_backend_eval(
    adapter: BackendAdapter,
    scenario: str | MemoryEvalScenario = DEFAULT_SCENARIO,
    *,
    answer_client: AnswerClient | None = None,
) -> dict[str, Any]:
    resolved_scenario = _resolve_scenario(scenario)
    try:
        for turn in resolved_scenario.seed_turns:
            adapter.seed_turn(turn)
        adapter.flush()
        seed_stats = adapter.get_stats()
    finally:
        adapter.close()

    cold_adapter = adapter.reopen_cold()
    try:
        cold_adapter.flush()
        cold_stats = cold_adapter.get_stats()
        probe_results = [
            evaluate_probe(cold_adapter, probe, answer_client=answer_client)
            for probe in resolved_scenario.probes
        ]
        summary = summarize_backend(cold_adapter.backend_name, cold_stats, probe_results)
        return {
            "backend": cold_adapter.backend_name,
            "scenario": resolved_scenario.name,
            "seed_stats": seed_stats,
            "cold_stats": cold_stats,
            "summary": summary,
            "probe_results": probe_results,
        }
    finally:
        cold_adapter.close()


def run_memory_eval(
    scenario: str | MemoryEvalScenario = DEFAULT_SCENARIO,
    *,
    answer_client: AnswerClient | None = None,
) -> dict[str, Any]:
    resolved_scenario = _resolve_scenario(scenario)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        basic_result = run_backend_eval(
            EngramBasicAdapter(root / "basic"),
            scenario=resolved_scenario,
            answer_client=answer_client,
        )
        full_result = run_backend_eval(
            EngramFullAdapter(root / "full"),
            scenario=resolved_scenario,
            answer_client=answer_client,
        )
        return {
            "scenario": asdict(resolved_scenario),
            "backends": {
                "basic": basic_result,
                "full": full_result,
            },
        }


def run_memory_eval_suite(
    scenarios: Sequence[str | MemoryEvalScenario] = ("default", "stress"),
    *,
    answer_client: AnswerClient | None = None,
) -> dict[str, Any]:
    resolved = [_resolve_scenario(item) for item in scenarios]
    suite_results: dict[str, Any] = {}
    aggregate: dict[str, dict[str, list[float]]] = {
        "basic": {},
        "full": {},
    }
    for scenario in resolved:
        result = run_memory_eval(scenario, answer_client=answer_client)
        suite_results[scenario.name] = result
        for backend in ("basic", "full"):
            summary = result["backends"][backend]["summary"]
            for key, value in summary.items():
                if isinstance(value, (int, float)) and key not in {"avg_redundancy_ratio"}:
                    aggregate[backend].setdefault(key, []).append(float(value))
            aggregate[backend].setdefault("avg_redundancy_ratio", []).append(
                float(summary.get("avg_redundancy_ratio", 0.0))
            )

    aggregate_summary: dict[str, dict[str, float]] = {}
    for backend, metrics in aggregate.items():
        aggregate_summary[backend] = {
            key: round(sum(values) / len(values), 3) for key, values in metrics.items() if values
        }

    return {
        "scenarios": [asdict(item) for item in resolved],
        "results": suite_results,
        "aggregate": aggregate_summary,
        "answer_eval_enabled": answer_client is not None,
    }


def render_memory_eval_markdown(report: dict[str, Any]) -> str:
    lines: list[str] = ["# Memory Evaluation Report", ""]
    if "results" in report:
        lines.append(
            f"Answer evaluation enabled: {'yes' if report.get('answer_eval_enabled') else 'no'}"
        )
        lines.append("")
        for scenario_name, scenario_report in report["results"].items():
            lines.extend(_render_single_scenario_markdown(scenario_name, scenario_report))
        lines.append("## Aggregate Summary")
        lines.append("")
        for backend, summary in report.get("aggregate", {}).items():
            lines.append(f"### {backend}")
            for key in sorted(summary):
                lines.append(f"- {key}: {summary[key]}")
            lines.append("")
        return "\n".join(lines).strip() + "\n"

    scenario_name = report.get("scenario", {}).get("name") or report.get("scenario", {}).get(
        "name", "scenario"
    )
    lines.extend(_render_single_scenario_markdown(str(scenario_name), report))
    return "\n".join(lines).strip() + "\n"


def _render_single_scenario_markdown(
    scenario_name: str, scenario_report: dict[str, Any]
) -> list[str]:
    lines = [f"## {scenario_name}", ""]
    for backend in ("basic", "full"):
        backend_report = scenario_report["backends"][backend]
        summary = backend_report["summary"]
        lines.append(f"### {backend}")
        for key in (
            "probe_pass_rate",
            "raw_probe_pass_rate",
            "prompt_pass_rate",
            "signal_retention_rate",
            "paraphrase_retention_rate",
            "decoy_rejection_rate",
            "update_resolution_rate",
            "noise_rejection_rate",
            "avg_redundancy_ratio",
            "answer_baseline_pass_rate",
            "answer_memory_pass_rate",
            "answer_net_uplift",
        ):
            value = summary.get(key)
            if value is not None:
                lines.append(f"- {key}: {value}")
        failed = summary.get("failed_probes") or []
        lines.append(f"- failed_probes: {', '.join(failed) if failed else 'none'}")
        raw_failed = summary.get("failed_raw_probes") or []
        lines.append(f"- failed_raw_probes: {', '.join(raw_failed) if raw_failed else 'none'}")
        lines.append("")
    return lines


def write_memory_eval_report(
    path: str | Path,
    scenario: str | MemoryEvalScenario = DEFAULT_SCENARIO,
    *,
    answer_client: AnswerClient | None = None,
) -> Path:
    result = run_memory_eval(scenario=scenario, answer_client=answer_client)
    out = Path(path)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return out


def write_memory_eval_suite_report(
    path: str | Path,
    scenarios: Sequence[str | MemoryEvalScenario] = ("default", "stress"),
    *,
    answer_client: AnswerClient | None = None,
) -> Path:
    result = run_memory_eval_suite(scenarios=scenarios, answer_client=answer_client)
    out = Path(path)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return out


def write_memory_eval_markdown(path: str | Path, report: dict[str, Any]) -> Path:
    out = Path(path)
    out.write_text(render_memory_eval_markdown(report), encoding="utf-8")
    return out


def build_answer_client_from_env() -> AnswerClient | None:
    import os

    base_url = os.getenv("MEMORY_EVAL_OPENAI_BASE_URL")
    model = os.getenv("MEMORY_EVAL_MODEL")
    api_key = os.getenv("MEMORY_EVAL_OPENAI_API_KEY")
    if not base_url or not model:
        return None
    return OpenAICompatibleAnswerClient(base_url=base_url, model=model, api_key=api_key)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run shared basic/full config memory evaluation harness"
    )
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), help="Run a single named scenario")
    parser.add_argument("--suite", action="store_true", help="Run the default scenario suite")
    parser.add_argument(
        "--json",
        dest="json_path",
        default="memory_eval_report.json",
        help="Path to write JSON report",
    )
    parser.add_argument(
        "--markdown",
        dest="markdown_path",
        default="memory_eval_report.md",
        help="Path to write Markdown report",
    )
    parser.add_argument(
        "--with-model",
        action="store_true",
        help="Use an OpenAI-compatible model configured via MEMORY_EVAL_* env vars",
    )
    args = parser.parse_args()

    answer_client = build_answer_client_from_env() if args.with_model else None
    if args.with_model and answer_client is None:
        raise SystemExit(
            "--with-model requested, but MEMORY_EVAL_OPENAI_BASE_URL and MEMORY_EVAL_MODEL are not configured"
        )

    if args.suite or not args.scenario:
        report = run_memory_eval_suite(answer_client=answer_client)
    else:
        report = run_memory_eval(args.scenario, answer_client=answer_client)

    Path(args.json_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    Path(args.markdown_path).write_text(render_memory_eval_markdown(report), encoding="utf-8")
    print(f"wrote {args.json_path}")
    print(f"wrote {args.markdown_path}")
