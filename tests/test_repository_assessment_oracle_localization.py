from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from llm_engines.contracts import ChatMessage, GenerationResponse, UsageStats


TOOLS = (
    Path(__file__).resolve().parents[1]
    / "docs/projects/repository_assessment/tools"
)


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


builder = _load("test_oracle_builder", "build_oracle_localization_manifest.py")
scorer = _load("test_oracle_scorer", "score_oracle_localization.py")
runner = _load("test_oracle_runner", "run_oracle_localization.py")


def test_matrix_has_three_seeds_and_balanced_conditions() -> None:
    payloads = builder.build_payloads()
    rows = payloads["run-matrix.json"]["runs"]

    assert len(rows) == 60
    for condition in ("B", "C"):
        selected = [row for row in rows if row["condition"] == condition]
        assert len(selected) == 30
        for item_id in {row["item_id"] for row in selected}:
            assert {row["seed"] for row in selected if row["item_id"] == item_id} == {
                17,
                31,
                47,
            }


def test_condition_b_does_not_receive_hypothesis_or_truth_label() -> None:
    payloads = builder.build_payloads()
    item = payloads["span-manifest.json"]["items"][0]
    oracle = payloads["oracle-manifest.json"]["oracles"][0]
    prompts = payloads["prompts.json"]

    messages = runner.render_messages(condition="B", item=item, oracle=oracle, prompts=prompts)
    rendered = "\n".join(message.content or "" for message in messages)

    assert oracle["hypothesis"] not in rendered
    assert item["item_id"] not in rendered
    assert item["kind"] not in rendered


def test_condition_c_receives_only_its_pair_hypothesis() -> None:
    payloads = builder.build_payloads()
    item = payloads["span-manifest.json"]["items"][0]
    oracle = payloads["oracle-manifest.json"]["oracles"][0]
    prompts = payloads["prompts.json"]

    messages = runner.render_messages(condition="C", item=item, oracle=oracle, prompts=prompts)
    rendered = "\n".join(message.content or "" for message in messages)

    assert oracle["hypothesis"] in rendered
    assert oracle["oracle"] not in rendered
    assert item["item_id"] not in rendered


def test_scorer_positive_and_negative_controls_pass() -> None:
    oracles = builder.build_payloads()["oracle-manifest.json"]["oracles"]
    result = scorer.run_controls(oracles)

    assert result["all_passed"] is True
    assert {row["control_id"] for row in result["controls"]} == {
        "accept_correct_identification",
        "reject_description_without_violation",
        "accept_negative_abstention",
        "detect_negative_false_assertion",
    }


def test_strict_parser_rejects_extra_fields_and_markdown_fence() -> None:
    valid = {
        "verdict": "violation",
        "affected_behavior": "behavior",
        "actionable_violation": "violation",
        "rationale": "rationale",
    }

    assert scorer.parse_response(json.dumps(valid), "B")[1] is None
    assert scorer.parse_response(json.dumps({**valid, "extra": True}), "B")[1] is not None
    assert scorer.parse_response(f"```json\n{json.dumps(valid)}\n```", "B")[1] is not None


def test_single_turn_runner_records_raw_usage_and_elapsed(tmp_path: Path) -> None:
    payloads = builder.build_payloads()
    matrix = payloads["run-matrix.json"]
    run = matrix["runs"][0]
    item = next(
        row for row in payloads["span-manifest.json"]["items"] if row["item_id"] == run["item_id"]
    )
    oracle = next(
        row for row in payloads["oracle-manifest.json"]["oracles"] if row["pair_id"] == item["pair_id"]
    )
    raw = json.dumps(
        {
            "verdict": "violation",
            "affected_behavior": "tool_not_granted classification",
            "actionable_violation": "It is not classified as blocked policy execution.",
            "rationale": "The blocked set omits it.",
        }
    )

    class FakeEngine:
        def generate(self, request):
            assert len(request.messages) == 2
            return GenerationResponse(
                message=ChatMessage(role="assistant", content=raw),
                finish_reason="stop",
                usage=UsageStats(
                    input_tokens=100,
                    output_tokens=25,
                    total_tokens=125,
                    latency_ms=2.5,
                ),
                model_name=matrix["model"],
                backend="fixture",
                seed_status="accepted",
            )

    output = tmp_path / "run"
    metadata = runner.run_one(
        engine=FakeEngine(),
        run=run,
        item=item,
        oracle=oracle,
        prompts=payloads["prompts.json"],
        matrix=matrix,
        fingerprint={
            "fingerprint_sha256": "fixture",
            "fingerprint": {"model_label": matrix["model"]},
        },
        output_dir=output,
    )

    transcript = [json.loads(line) for line in (output / "transcript.jsonl").read_text().splitlines()]
    assert metadata["validity"] == "valid"
    assert transcript[1]["content"] == raw
    assert transcript[1]["usage"] == metadata["usage"]
    assert transcript[1]["elapsed_ms"] == metadata["elapsed_ms"]
    assert (output / "parsed-response.json").is_file()
