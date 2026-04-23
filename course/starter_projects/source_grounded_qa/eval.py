from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
CORE_SRC = REPO_ROOT / "llm_harness_core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from llm_harness_core import EvaluatorRequest, SimilarityEvaluator, SubstringMatchEvaluator


def _score(name: str, candidate: str, *, expected: tuple[str, ...], forbidden: tuple[str, ...] = (), reference: str | None = None) -> dict:
    substring = SubstringMatchEvaluator().evaluate(
        EvaluatorRequest(
            candidate=candidate,
            expected_texts=expected,
            forbidden_texts=forbidden,
            min_expected_hits=1 if expected else 0,
            max_forbidden_hits=0,
        )
    ).value
    similarity = SimilarityEvaluator(threshold=0.55).evaluate(
        EvaluatorRequest(
            candidate=candidate,
            reference_answer=reference or (expected[0] if expected else ""),
        )
    ).value
    return {
        "name": name,
        "substring_passed": substring.passed,
        "substring_score": substring.score,
        "similarity_passed": similarity.passed,
        "similarity_score": similarity.score,
        "rationale": substring.rationale,
    }


def main() -> int:
    question = "Which database should analytics work use?"
    baseline_answer = "Use SQLite for analytics."
    grounded_answer = (
        "Use DuckDB for analytics. The updated analytics decision note is the supporting evidence."
    )
    evidence_text = "Updated analytics decision: use DuckDB locally instead of SQLite for analytics."

    baseline = _score(
        "baseline",
        baseline_answer,
        expected=("duckdb",),
        forbidden=("sqlite for analytics",),
        reference="DuckDB is the current analytics database choice.",
    )
    grounded = _score(
        "grounded",
        grounded_answer,
        expected=("duckdb",),
        forbidden=("sqlite for analytics",),
        reference="DuckDB is the current analytics database choice.",
    )
    evidence = _score(
        "evidence_presence",
        evidence_text,
        expected=("duckdb", "updated analytics decision"),
        forbidden=(),
        reference="Updated analytics decision: use DuckDB for analytics.",
    )

    uplift = grounded["substring_score"] - baseline["substring_score"]

    print("Evaluation summary")
    print(f"Question: {question}")
    print(f"Baseline answer: {baseline_answer}")
    print(f"Grounded answer: {grounded_answer}")
    print(f"Baseline substring score: {baseline['substring_score']}")
    print(f"Grounded substring score: {grounded['substring_score']}")
    print(f"Evidence substring score: {evidence['substring_score']}")
    print(f"Answer uplift: {uplift}")
    print(f"Grounded rationale: {grounded['rationale']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
