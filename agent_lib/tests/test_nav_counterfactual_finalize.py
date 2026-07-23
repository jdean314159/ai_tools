from __future__ import annotations

import importlib.util
from pathlib import Path


_SCRIPT = Path(__file__).parents[1] / "examples" / "nav_counterfactual_finalize.py"
_SPEC = importlib.util.spec_from_file_location("nav_counterfactual_finalize", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _record() -> dict:
    return {
        "run": {
            "steps": [
                {
                    "index": 1,
                    "action": {
                        "kind": "tool",
                        "tool_call": {
                            "name": "read_file",
                            "arguments": {"path": "pkg/store.py"},
                        },
                    },
                    "observation": {
                        "text": (
                            "1: class ChromaStorage:\n"
                            "2:     def add(self):\n"
                            "3:         coll.upsert(ids=[])\n"
                        ),
                        "tool_result": {
                            "success": True,
                            "meta": {
                                "evidence": [
                                    {"path": "pkg/store.py", "lines": [1, 2, 3]}
                                ]
                            },
                        },
                    },
                }
            ]
        },
        "planner_usage": {"calls": [{"actual_total_tokens": 100}]},
    }


def test_observed_source_uses_lossless_production_ledger() -> None:
    evidence = _MODULE._observed_source(_record(), 1)

    assert "class ChromaStorage" in evidence
    assert "def add" in evidence
    assert "coll.upsert" in evidence
    assert _MODULE._cumulative_tokens(_record(), 1) == 100


def test_evidence_conditioned_score_uses_only_surfaced_regions() -> None:
    regions = [
        {
            "id": "GT-1",
            "path": "pkg/store.py",
            "start_line": 1,
            "end_line": 3,
            "required_answer_terms": ["ChromaStorage", "upsert"],
        },
        {
            "id": "GT-2",
            "path": "pkg/missing.py",
            "start_line": 1,
            "end_line": 1,
            "required_answer_terms": ["missing"],
        },
    ]
    surfaced = _MODULE._surfaced_regions(_record(), regions, 1)
    score = _MODULE._score_answer(
        "pkg/store.py: ChromaStorage uses upsert.", regions, surfaced
    )

    assert surfaced == {"GT-1"}
    assert score["evidence_conditioned_recall"] == 1.0
    assert score["full_answer_recall"] == 0.5
