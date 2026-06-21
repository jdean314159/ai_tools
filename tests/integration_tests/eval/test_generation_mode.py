from __future__ import annotations

import asyncio

import pytest

from integration_tests.eval.compare_backends import compare_metrics
from integration_tests.eval.corpus import Fact
from integration_tests.eval.engram_probe import EngramProbe, GenerationResult
from integration_tests.eval.eval_config import EvalConfig
from integration_tests.eval.metrics import compute_metrics
from integration_tests.eval.ollama_judge import OllamaJudge


class _PromptMemory:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def build_prompt(self, query: str) -> dict:
        self.queries.append(query)
        return {"prompt": "## Memory Layer Hints\n[Neural context]\nKnown pattern"}


def _fact() -> Fact:
    return Fact(
        id="f1",
        category="test",
        salience="high",
        canonical="The region is west.",
        direct_query="Which region?",
        paraphrase_query="Where is it deployed?",
        decoy_query="Is the region east?",
        expected_snippet="west",
        contradiction="The region is east.",
    )


def test_answer_query_builds_full_prompt_and_returns_generated_answer(tmp_path):
    probe = EngramProbe(EvalConfig(mode="generation"), "baseline", tmp_path)
    memory = _PromptMemory()
    probe._memory = memory
    generated_prompts: list[tuple[str, str]] = []

    async def fake_generate(prompt: str, query: str) -> str:
        generated_prompts.append((prompt, query))
        return "The region is west."

    probe._generate = fake_generate
    result = asyncio.run(probe.answer_query(_fact(), "direct"))

    assert result.success is True
    assert result.answer == "The region is west."
    assert result.neural_hint_present is True
    assert memory.queries == ["Which region?"]
    assert "[Neural context]" in generated_prompts[0][0]


def test_metrics_record_generation_mode():
    metrics = compute_metrics([], "baseline", mode="generation")
    assert metrics["mode"] == "generation"


def test_generation_judge_grades_answer_text(tmp_path):
    judge = OllamaJudge(cache_path=tmp_path / "judge.json")
    prompts: list[str] = []

    async def fake_call(prompt: str):
        prompts.append(prompt)
        return (
            '{"retrieved": true, "relevance": 5, "contaminated": false, '
            '"verbatim_match": true, "notes": "correct"}',
            None,
        )

    judge._call_ollama = fake_call
    result = GenerationResult(
        fact_id="f1",
        query="Which region?",
        query_type="direct",
        top_k=3,
        answer="The region is west.",
        elapsed_ms=1.0,
        success=True,
        neural_hint_present=True,
    )

    judgment = asyncio.run(judge.judge(_fact(), result, 0))

    assert judgment.correct is True
    assert "GENERATED ANSWER:\nThe region is west." in prompts[0]
    assert "RETRIEVED CHUNKS" not in prompts[0]


def test_compare_backends_rejects_mismatched_modes():
    baseline = compute_metrics([], "baseline", mode="retrieval")
    neural = compute_metrics([], "neural_on", mode="generation")

    with pytest.raises(ValueError, match="different modes"):
        compare_metrics(baseline, neural)


def test_generation_requests_respect_configured_concurrency(tmp_path):
    config = EvalConfig(
        mode="generation",
        judge_concurrency=2,
        judge_retries=0,
    )
    probe = EngramProbe(config, "baseline", tmp_path)

    class FakeResponse:
        status = 200

        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            self.session.active += 1
            self.session.max_active = max(
                self.session.max_active,
                self.session.active,
            )
            await asyncio.sleep(0.01)
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            self.session.active -= 1

        async def json(self):
            return {"message": {"content": "answer"}}

    class FakeSession:
        def __init__(self):
            self.active = 0
            self.max_active = 0

        def post(self, *args, **kwargs):
            del args, kwargs
            return FakeResponse(self)

    session = FakeSession()
    probe._session = session

    async def run_many():
        return await asyncio.gather(
            *[
                probe._generate(f"prompt {index}", f"query {index}")
                for index in range(8)
            ]
        )

    answers = asyncio.run(run_many())

    assert answers == ["answer"] * 8
    assert session.max_active == 2
