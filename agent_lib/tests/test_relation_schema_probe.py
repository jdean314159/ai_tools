from __future__ import annotations

import json
from pathlib import Path

from agent_lib.eval.relation_schema_probe import run_relation_schema_probe
from llm_engines.contracts import ChatMessage, GenerationResponse, UsageStats


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "nav_verifiable"


class ScriptedProbeModel:
    def __init__(self, responses: list[dict]) -> None:
        self.responses = iter(responses)

    def generate(self, request) -> GenerationResponse:
        assert request.json_schema is not None
        return GenerationResponse(
            message=ChatMessage(
                role="assistant",
                content=json.dumps(next(self.responses)),
            ),
            finish_reason="stop",
            usage=UsageStats(
                input_tokens=100,
                output_tokens=50,
                total_tokens=150,
            ),
            model_name="scripted",
            backend="test",
        )


def test_formatter_probe_requires_schema_and_exact_relations() -> None:
    model = ScriptedProbeModel(
        [
            {
                "relation_claims": [
                    {
                        "kind": "call_edge",
                        "path": "sample.py",
                        "symbol": "sample.Pipeline._prepare",
                        "target": "sample.Pipeline._store_add",
                        "path_symbols": [],
                        "evidence": [
                            {
                                "path": "sample.py",
                                "start_line": 11,
                                "end_line": 11,
                            }
                        ],
                    }
                ]
            },
            {
                "relation_claims": [
                    {
                        "kind": "call_path",
                        "path": "sample.py",
                        "symbol": "sample.Pipeline.ingest",
                        "target": "sample.Pipeline._store_add",
                        "path_symbols": [
                            "sample.Pipeline.ingest",
                            "sample.Pipeline._prepare",
                            "sample.Pipeline._store_add",
                        ],
                        "evidence": [
                            {
                                "path": "sample.py",
                                "start_line": 8,
                                "end_line": 11,
                            }
                        ],
                    }
                ]
            },
            {
                "relation_claims": [
                    {
                        "kind": "mutation_target",
                        "path": "sample.py",
                        "symbol": "sample.Pipeline._store_add",
                        "target": "self.store.add",
                        "path_symbols": [],
                        "evidence": [
                            {
                                "path": "sample.py",
                                "start_line": 14,
                                "end_line": 14,
                            }
                        ],
                    }
                ]
            },
        ]
    )

    result = run_relation_schema_probe(
        engine=model,
        fixture_root=FIXTURE_ROOT,
        task_set_path=FIXTURE_ROOT / "tasks.json",
    )

    assert result["passed"] is True
    assert [trial["schema_valid"] for trial in result["trials"]] == [
        True,
        True,
        True,
    ]


def test_formatter_probe_separates_schema_failure_from_relation_failure() -> None:
    model = ScriptedProbeModel(
        [
            {"wrong": []},
            {
                "relation_claims": [
                    {
                        "kind": "call_path",
                        "path": "sample.py",
                        "symbol": "sample.Pipeline.ingest",
                        "target": "sample.Pipeline._store_add",
                        "path_symbols": [
                            "sample.Pipeline.ingest",
                            "sample.Pipeline._store_add",
                        ],
                        "evidence": [
                            {
                                "path": "sample.py",
                                "start_line": 8,
                                "end_line": 8,
                            }
                        ],
                    }
                ]
            },
            {
                "relation_claims": [
                    {
                        "kind": "mutation_target",
                        "path": "sample.py",
                        "symbol": "sample.Pipeline._store_add",
                        "target": "self.store.add",
                        "path_symbols": [],
                        "evidence": [
                            {
                                "path": "sample.py",
                                "start_line": 14,
                                "end_line": 14,
                            }
                        ],
                    }
                ]
            },
        ]
    )

    result = run_relation_schema_probe(
        engine=model,
        fixture_root=FIXTURE_ROOT,
        task_set_path=FIXTURE_ROOT / "tasks.json",
    )

    assert result["passed"] is False
    assert result["trials"][0]["schema_valid"] is False
    assert result["trials"][1]["schema_valid"] is True
    assert result["trials"][1]["exact_relation_correct"] is False
