from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs/projects/repository_assessment/tools/validate_model_blind_transfer_pilot.py"
)
SPEC = importlib.util.spec_from_file_location("validate_model_blind_transfer_pilot", SCRIPT_PATH)
assert SPEC is not None
validator = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_incomplete_campaign_fails_without_inferring_recall(tmp_path: Path) -> None:
    source_root = tmp_path / "tools"
    source_root.mkdir()
    (source_root / "run_staged_assessment.py").write_text("fixture", encoding="utf-8")
    (source_root / "run_adaptive_staged_assessment.py").write_text("fixture", encoding="utf-8")

    result = validator.validate_campaign(tmp_path / "campaign", source_root)

    assert result["valid"] is False
    assert result["expected_runs"] == 4
    assert result["observed_run_metadata"] == 0
    assert result["recall_adjudicated"] is False
    assert result["grader_outcomes_valid"] is False
    assert "staged runner digest mismatch" in result["errors"]
    assert "missing independent grader results" in result["errors"]
    assert any("missing endpoint pair" in error for error in result["errors"])


def test_run_validation_checks_identity_hashes_and_budget(tmp_path: Path) -> None:
    target = next(iter(validator.TARGETS.values()))
    run_dir = tmp_path / "run"
    transcript = run_dir / "transcript.jsonl"
    report = run_dir / "raw-model-report.md"
    transcript.parent.mkdir()
    transcript.write_text("{}\n", encoding="utf-8")
    report.write_text("No finding.\n", encoding="utf-8")
    metadata = {
        **{
            field: target[field]
            for field in (
                "target_commit",
                "target_tree",
                "target_archive_sha256",
            )
        },
        "condition": "staged_scout_verifier_critic_synthesis",
        "seed": 17,
        "model": validator.MODEL_LABEL,
        "prompt_sha256": validator.PROMPT_SHA256["staged"],
        "shell_tool_calls": 45,
        "transcript_sha256": validator._sha256(transcript),
        "report_sha256": validator._sha256(report),
    }
    _write_json(run_dir / "run-metadata.json", metadata)

    errors = validator.validate_run(
        run_dir,
        target=target,
        condition="staged_scout_verifier_critic_synthesis",
        seed=17,
        runner_kind="staged",
    )

    assert errors == []
    metadata["shell_tool_calls"] = 46
    _write_json(run_dir / "run-metadata.json", metadata)
    errors = validator.validate_run(
        run_dir,
        target=target,
        condition="staged_scout_verifier_critic_synthesis",
        seed=17,
        runner_kind="staged",
    )
    assert errors == ["run: shell-call ceiling exceeded"]


def test_endpoint_comparison_accepts_null_to_known_slot_telemetry() -> None:
    before = {
        "fingerprint": {
            "model_label": validator.MODEL_LABEL,
            "total_slots": 1,
            "slots": [
                {
                    "id": 0,
                    "is_processing": False,
                    "n_ctx": 262144,
                    "speculative": True,
                    "speculative_types": None,
                }
            ],
        }
    }
    after = json.loads(json.dumps(before))
    after["fingerprint"]["slots"][0]["speculative_types"] = "none,draft-mtp"

    errors, observations = validator.compare_endpoint_snapshots(before, after)

    assert errors == []
    assert observations == [
        "endpoint slot 0 speculative_types telemetry changed from None to 'none,draft-mtp'"
    ]


def test_endpoint_comparison_rejects_conflicting_known_slot_telemetry() -> None:
    before = {
        "fingerprint": {
            "model_label": validator.MODEL_LABEL,
            "total_slots": 1,
            "slots": [
                {
                    "id": 0,
                    "is_processing": False,
                    "n_ctx": 262144,
                    "speculative": True,
                    "speculative_types": "draft",
                }
            ],
        }
    }
    after = json.loads(json.dumps(before))
    after["fingerprint"]["slots"][0]["speculative_types"] = "none,draft-mtp"

    errors, observations = validator.compare_endpoint_snapshots(before, after)

    assert errors == ["endpoint slot 0 speculative_types changed"]
    assert observations == []
