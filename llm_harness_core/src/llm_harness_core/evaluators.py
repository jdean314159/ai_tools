from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Callable, Protocol

from .results import OperationResult


@dataclass(frozen=True)
class EvaluatorRequest:
    candidate: str
    expected_texts: tuple[str, ...] = ()
    forbidden_texts: tuple[str, ...] = ()
    min_expected_hits: int = 1
    max_forbidden_hits: int = 0
    reference_answer: str | None = None
    rubric: str | None = None
    context: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationResult:
    evaluator: str
    score: float
    passed: bool
    rationale: str | None = None
    evidence: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)


class Evaluator(Protocol):
    name: str

    def evaluate(self, request: EvaluatorRequest) -> OperationResult[EvaluationResult]: ...


@dataclass(frozen=True)
class SubstringMatchEvaluator:
    name: str = "substring_match"

    def evaluate(self, request: EvaluatorRequest) -> OperationResult[EvaluationResult]:
        lowered = (request.candidate or "").lower()
        expected_hits = tuple(
            needle for needle in request.expected_texts if needle and needle.lower() in lowered
        )
        forbidden_hits = tuple(
            needle for needle in request.forbidden_texts if needle and needle.lower() in lowered
        )
        passed = (
            len(expected_hits) >= request.min_expected_hits
            and len(forbidden_hits) <= request.max_forbidden_hits
        )
        total_expected = len(request.expected_texts)
        hit_score = 1.0 if total_expected == 0 else len(expected_hits) / max(1, total_expected)
        penalty = (
            0.0
            if not forbidden_hits
            else min(1.0, len(forbidden_hits) / max(1, len(request.forbidden_texts) or 1))
        )
        score = max(0.0, round(hit_score - penalty, 3))
        rationale_parts: list[str] = []
        if request.expected_texts:
            rationale_parts.append(
                f"matched {len(expected_hits)}/{len(request.expected_texts)} expected substrings"
            )
        if request.forbidden_texts:
            rationale_parts.append(f"found {len(forbidden_hits)} forbidden substrings")
        result = EvaluationResult(
            evaluator=self.name,
            score=score,
            passed=passed,
            rationale="; ".join(rationale_parts) if rationale_parts else None,
            evidence=expected_hits + forbidden_hits,
            details={
                "expected_hits": list(expected_hits),
                "forbidden_hits": list(forbidden_hits),
                "min_expected_hits": request.min_expected_hits,
                "max_forbidden_hits": request.max_forbidden_hits,
            },
        )
        return OperationResult.success(result)


@dataclass(frozen=True)
class SimilarityEvaluator:
    threshold: float = 0.8
    name: str = "similarity"

    def evaluate(self, request: EvaluatorRequest) -> OperationResult[EvaluationResult]:
        refs = [ref for ref in (request.reference_answer, *request.expected_texts) if ref]
        if not refs:
            return OperationResult.failure(
                "missing_reference",
                "SimilarityEvaluator requires reference_answer or expected_texts.",
            )
        candidate = request.candidate or ""
        best = max(SequenceMatcher(None, candidate.lower(), ref.lower()).ratio() for ref in refs)
        result = EvaluationResult(
            evaluator=self.name,
            score=round(best, 3),
            passed=best >= self.threshold,
            rationale=f"best similarity {best:.3f} against {len(refs)} reference(s)",
            evidence=tuple(refs),
            details={"threshold": self.threshold},
        )
        return OperationResult.success(result)


JudgeFn = Callable[[EvaluatorRequest], EvaluationResult]


@dataclass(frozen=True)
class RubricEvaluator:
    judge: JudgeFn
    name: str = "rubric"

    def evaluate(self, request: EvaluatorRequest) -> OperationResult[EvaluationResult]:
        try:
            result = self.judge(request)
        except Exception as exc:
            return OperationResult.failure(
                "rubric_evaluator_failed",
                str(exc),
            )
        return OperationResult.success(result)


@dataclass(frozen=True)
class LLMJudgeEvaluator:
    judge: JudgeFn
    name: str = "llm_as_judge"

    def evaluate(self, request: EvaluatorRequest) -> OperationResult[EvaluationResult]:
        try:
            result = self.judge(request)
        except Exception as exc:
            return OperationResult.failure(
                "llm_judge_failed",
                str(exc),
            )
        return OperationResult.success(result)
