from __future__ import annotations

from dataclasses import dataclass
from pprint import pprint

from llm_harness_core import EvaluatorRequest, SubstringMatchEvaluator


@dataclass(frozen=True)
class Scenario:
    name: str
    question: str
    raw_memory: str
    repaired_memory: str
    expected: str
    forbidden: str


SCENARIOS = (
    Scenario(
        name="docs policy",
        question="Where should project documentation live?",
        raw_memory="Project docs are not in Google Docs; the team used to keep them in a shared folder.",
        repaired_memory="Project documentation lives in Markdown files committed to the repo.",
        expected="Markdown files committed to the repo",
        forbidden="Google Docs",
    ),
    Scenario(
        name="model update",
        question="Which local model should the smoke run use?",
        raw_memory="The smoke run should use llama3.1:8b instead of qwen3:8b.",
        repaired_memory="The smoke run should use qwen3:8b.",
        expected="qwen3:8b",
        forbidden="llama3.1:8b",
    ),
)


def _answer(memory: str) -> str:
    return memory


def render_scenario(scenario: Scenario) -> str:
    broken_answer = _answer(scenario.raw_memory)
    repaired_answer = _answer(scenario.repaired_memory)
    return "\n".join(
        [
            f"Question: {scenario.question}",
            "Broken path:",
            f"  Memory: {scenario.raw_memory}",
            f"  Answer: {broken_answer}",
            "Repaired path:",
            f"  Memory: {scenario.repaired_memory}",
            "  Evidence flow:",
            f"    before_text={scenario.raw_memory!r}",
            f"    after_text={scenario.repaired_memory!r}",
            "    exclusion_reason=stale_alternative_suppressed",
            f"  Answer: {repaired_answer}",
        ]
    )


def evaluate_lab() -> dict[str, object]:
    evaluator = SubstringMatchEvaluator()
    results: dict[str, object] = {}
    for scenario in SCENARIOS:
        broken = evaluator.evaluate(
            EvaluatorRequest(
                candidate=_answer(scenario.raw_memory),
                expected_texts=(scenario.expected,),
                forbidden_texts=(scenario.forbidden,),
            )
        )
        repaired = evaluator.evaluate(
            EvaluatorRequest(
                candidate=_answer(scenario.repaired_memory),
                expected_texts=(scenario.expected,),
                forbidden_texts=(scenario.forbidden,),
            )
        )
        assert broken.value is not None
        assert repaired.value is not None
        results[scenario.name] = {
            "broken_passed": broken.value.passed,
            "repaired_passed": repaired.value.passed,
            "repair": "canonicalize_current_state_and_suppress_stale_alternative",
        }
    return {"scenarios": results}


if __name__ == "__main__":
    for item in SCENARIOS:
        print(f"\n=== Scenario: {item.name} ===")
        print(render_scenario(item))
    print("\n=== Evaluation summary ===")
    pprint(evaluate_lab())
