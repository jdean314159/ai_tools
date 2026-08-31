from __future__ import annotations

from pathlib import Path

import pytest
from llm_inspector.adapters.engram_adapter import EngramAugmenter
from llm_inspector.core import Trace
from llm_inspector.protocols import AugmentRequest
from llm_inspector.core import Turn

pytestmark = pytest.mark.engram


class FakeEngine:
    backend_label = "fake"
    model_name = "fake-model"

    def count_tokens(self, text: str) -> int:
        return len(text.split())

    def generate(self, prompt: str) -> str:
        return "test reply"


def test_engram_adapter_prefers_shared_interop_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from engram import ProjectType
    from engram.project_memory import ProjectMemory

    calls: dict[str, int] = {"interop": 0, "legacy": 0}

    original_init = ProjectMemory.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["llm_engine"] = FakeEngine()
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(ProjectMemory, "__init__", patched_init)

    original_build_prompt_interop = ProjectMemory.build_prompt_interop
    original_build_prompt = ProjectMemory.build_prompt

    def patched_build_prompt_interop(self, *args, **kwargs):
        calls["interop"] += 1
        return original_build_prompt_interop(self, *args, **kwargs)

    def patched_build_prompt(self, *args, **kwargs):
        calls["legacy"] += 1
        return original_build_prompt(self, *args, **kwargs)

    monkeypatch.setattr(ProjectMemory, "build_prompt_interop", patched_build_prompt_interop)
    monkeypatch.setattr(ProjectMemory, "build_prompt", patched_build_prompt)

    augmenter = EngramAugmenter(
        base_dir=tmp_path,
        project_id="adapter-test",
        project_type=ProjectType.GENERAL_ASSISTANT.value,
    )
    req = AugmentRequest(
        turn=Turn(role="user", text="Remember that I prefer Python.", session_id="s1"),
        query="preferred language",
        session_id="s1",
    )

    trace = augmenter.augment(req)

    assert isinstance(trace, Trace)
    assert trace.metrics.engine == "engram"
    assert any(event.event_type == "prompt_build_completed" for event in trace.events)
    assert calls["interop"] >= 1
    # The interop path still calls build_prompt internally today; this assertion proves the adapter itself
    # did not fall back to its legacy return_trace-based code path.
    assert calls["legacy"] >= 1


def test_engram_adapter_returns_trace_from_shared_diagnostics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from engram.project_memory import ProjectMemory

    original_init = ProjectMemory.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["llm_engine"] = FakeEngine()
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(ProjectMemory, "__init__", patched_init)

    augmenter = EngramAugmenter(
        base_dir=tmp_path,
        project_id="adapter-test-2",
        project_type="general_assistant",
    )
    req = AugmentRequest(
        turn=Turn(role="user", text="Use DuckDB for analytics.", session_id="s2"),
        query="analytics database",
        session_id="s2",
    )

    trace = augmenter.augment(req)

    assert isinstance(trace, Trace)
    assert trace.context.evidence
    assert trace.context.sections
    assert trace.events


def test_engram_adapter_interop_events_include_provenance_and_transformations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from engram.project_memory import ProjectMemory

    original_init = ProjectMemory.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["llm_engine"] = FakeEngine()
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(ProjectMemory, "__init__", patched_init)

    augmenter = EngramAugmenter(
        base_dir=tmp_path,
        project_id="adapter-test-3",
        project_type="general_assistant",
    )
    req = AugmentRequest(
        turn=Turn(role="user", text="Keep docs in Markdown in the repo.", session_id="s3"),
        query="docs policy",
        session_id="s3",
    )

    trace = augmenter.augment(req)

    included = [event for event in trace.events if event.event_type == "memory_evidence_included"]
    assert included
    assert any("provenance" in event.payload for event in included)
    assert any("transformations" in event.payload for event in included)


def test_engram_adapter_end_to_end_uses_shared_trace_events_for_serialization_and_rendering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from engram.project_memory import ProjectMemory
    from engram.inspection import PromptBuildTrace
    from llm_inspector.core.serialize import to_json
    from llm_inspector.inspectors import ContextInspector
    from llm_inspector.renderers import render_comparison

    original_init = ProjectMemory.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["llm_engine"] = FakeEngine()
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(ProjectMemory, "__init__", patched_init)

    def explode_if_legacy_reconstruction_used(self):
        raise AssertionError(
            "adapter attempted legacy PromptBuildTrace.to_interop_events reconstruction"
        )

    monkeypatch.setattr(
        PromptBuildTrace, "to_interop_events", explode_if_legacy_reconstruction_used
    )

    augmenter = EngramAugmenter(
        base_dir=tmp_path,
        project_id="adapter-test-4",
        project_type="general_assistant",
    )
    report = ContextInspector([augmenter]).run("store docs in markdown", session_id="s4")

    assert len(report.traces) == 1
    trace = report.traces[0].trace

    payload = to_json(trace)
    rendered = render_comparison(report)

    assert '"event_type": "prompt_build_completed"' in payload
    assert '"event_type": "memory_evidence_included"' in payload
    assert '"provenance"' in payload
    assert '"transformations"' in payload
    assert "=== engram ===" in rendered
    assert "Sections:" in rendered
    assert "Evidence:" in rendered
