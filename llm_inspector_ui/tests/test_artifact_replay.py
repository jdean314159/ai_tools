from __future__ import annotations

import json
from pathlib import Path

import pytest

from llm_inspector_ui.services.inspector_service import InspectorService


ROOT = Path(__file__).resolve().parents[2]


def test_replay_supported_committed_artifact_without_execution():
    path = ROOT / "docs/projects/llm_engines/runs/2026-08-30-spark-qwen38-flash-next-characterization-v2.json"
    result = InspectorService().replay_artifact_json(path.read_bytes())
    assert result["body_support"] == "supported"
    assert result["common"]["kind"] == "experiment"
    assert result["body_summary"]["record_type"] == "model_characterization_campaign"


def test_replay_unsupported_profile_is_envelope_only():
    path = ROOT / "docs/projects/agent_lib/runs/2026-08-31-agent-command-isolation-v2.json"
    result = InspectorService().replay_artifact_json(path.read_bytes())
    assert result["body_support"] == "unsupported"
    assert result["body_summary"] is None
    assert any("unsupported" in notice for notice in result["notices"])


@pytest.mark.parametrize("payload", [b"not json", json.dumps([]).encode(), b"{}"])
def test_replay_rejects_invalid_artifacts_without_echoing_content(payload):
    with pytest.raises(ValueError, match="Invalid run artifact") as caught:
        InspectorService().replay_artifact_json(payload)
    assert "not json" not in str(caught.value)


def test_replay_enforces_upload_size_limit():
    with pytest.raises(ValueError, match="exceeds"):
        InspectorService().replay_artifact_json(b"12345", max_bytes=4)
