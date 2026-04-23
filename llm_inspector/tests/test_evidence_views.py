from __future__ import annotations

from pathlib import Path

import pytest

from llm_inspector.adapters.engram_adapter import EngramAugmenter
from llm_inspector.core import EvidenceFlow, Turn
from llm_inspector.inspectors import ContextInspector
from llm_inspector.protocols import AugmentRequest
from llm_inspector.renderers import render_comparison


class FakeEngine:
    backend_label = "fake"
    model_name = "fake-model"

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def generate(self, prompt: str) -> str:
        return "test reply"


def test_engram_adapter_builds_evidence_flows_with_provenance(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from engram.project_memory import ProjectMemory

    original_init = ProjectMemory.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["llm_engine"] = FakeEngine()
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(ProjectMemory, "__init__", patched_init)

    augmenter = EngramAugmenter(base_dir=tmp_path, project_id="flows-test", project_type="general_assistant")
    req = AugmentRequest(turn=Turn(role="user", text="Keep docs in Markdown in the repo.", session_id="s1"), query="docs policy", session_id="s1")

    trace = augmenter.augment(req)

    assert trace.context.evidence_flows
    flow = trace.context.evidence_flows[0]
    assert isinstance(flow, EvidenceFlow)
    assert flow.source
    assert flow.after_text
    assert flow.stage == "prompt_included"
    assert isinstance(flow.provenance, dict)
    assert flow.transformations


def test_render_comparison_includes_evidence_flow_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from engram.project_memory import ProjectMemory

    original_init = ProjectMemory.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["llm_engine"] = FakeEngine()
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(ProjectMemory, "__init__", patched_init)

    augmenter = EngramAugmenter(base_dir=tmp_path, project_id="flows-render", project_type="general_assistant")
    report = ContextInspector([augmenter]).run("store docs in markdown", session_id="s2")

    rendered = render_comparison(report)

    assert "Evidence flow:" in rendered
    assert "provenance=" in rendered
    assert "xforms=" in rendered
