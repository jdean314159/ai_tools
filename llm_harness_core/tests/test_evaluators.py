from llm_harness_core import (
    EvaluationResult,
    EvaluatorRequest,
    LLMJudgeEvaluator,
    RubricEvaluator,
    SimilarityEvaluator,
    SubstringMatchEvaluator,
)


def test_substring_evaluator_matches_expected_and_forbidden() -> None:
    evaluator = SubstringMatchEvaluator()
    result = evaluator.evaluate(
        EvaluatorRequest(
            candidate="Use DuckDB locally. SQLite is only for the semantic store.",
            expected_texts=("duckdb",),
            forbidden_texts=("mysql",),
        )
    )
    assert result.ok is True
    assert result.value is not None
    assert result.value.passed is True
    assert result.value.details["expected_hits"] == ["duckdb"]
    assert result.value.details["forbidden_hits"] == []


def test_similarity_evaluator_uses_reference_answer() -> None:
    evaluator = SimilarityEvaluator(threshold=0.4)
    result = evaluator.evaluate(
        EvaluatorRequest(
            candidate="Python is preferred.",
            reference_answer="Preferred language: Python.",
        )
    )
    assert result.ok is True
    assert result.value is not None
    assert result.value.passed is True
    assert result.value.score >= 0.4


def test_rubric_evaluator_wraps_callback() -> None:
    evaluator = RubricEvaluator(
        judge=lambda req: EvaluationResult(
            evaluator="rubric",
            score=1.0,
            passed="complete" in req.candidate.lower(),
            rationale="simple rubric",
        )
    )
    result = evaluator.evaluate(EvaluatorRequest(candidate="Complete answer."))
    assert result.ok is True
    assert result.value is not None
    assert result.value.passed is True


def test_llm_judge_evaluator_wraps_callback() -> None:
    evaluator = LLMJudgeEvaluator(
        judge=lambda req: EvaluationResult(
            evaluator="llm_as_judge",
            score=0.75,
            passed=True,
            rationale=f"judged: {req.candidate}",
        )
    )
    result = evaluator.evaluate(EvaluatorRequest(candidate="Good answer"))
    assert result.ok is True
    assert result.value is not None
    assert result.value.evaluator == "llm_as_judge"
