"""
Cross-package smoke tests for the prompt-augmentation spine.

The goal is to catch repo-level drift between llm_inspector_ui, engram,
optional full engram, rag_lib-shaped traces, and llm_inspector trace
normalization. These tests avoid live model calls and external services.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any

import pytest

from engram.contracts import AugmentRequest
from llm_harness_core import RetrievedDocument, TraceEvent
from llm_inspector_ui.services.augmenter_service import AugmenterService, RagAugmenter
from llm_inspector_ui.services.inspector_service import InspectorService
from llm_inspector_ui.utils.trace_access import (
    get_final_prompt,
    get_retrieval_events,
    get_retrieval_summary,
    get_sections,
    get_token_accounting,
)


@dataclass
class _FakeRagTrace:
    selected_results: tuple[RetrievedDocument, ...]
    assembled_prompt: str
    events: tuple[TraceEvent, ...]
    diagnostics: dict[str, Any]

    def to_serializable_dict(self) -> dict[str, Any]:
        return {
            "selected_results": [
                {
                    "text": doc.text,
                    "source": doc.source,
                    "doc_id": doc.doc_id,
                    "score": doc.score,
                    "metadata": dict(doc.metadata),
                }
                for doc in self.selected_results
            ],
            "events": [
                {
                    "event_type": event.event_type,
                    "source_package": event.source_package,
                    "source_component": event.source_component,
                    "payload": dict(event.payload),
                    "severity": event.severity,
                    "message": event.message,
                    "tags": list(event.tags),
                }
                for event in self.events
            ],
            "diagnostics": dict(self.diagnostics),
        }


class _FakeRagPipeline:
    def inspect_query(self, query: str, **kwargs: Any) -> _FakeRagTrace:
        doc = RetrievedDocument(
            text="Project Orion uses DuckDB for analytics.",
            source="orion_decision.md",
            doc_id="orion-db",
            score=0.93,
            metadata={"stage": "selected", "query": query},
        )
        return _FakeRagTrace(
            selected_results=(doc,),
            assembled_prompt=(
                "## Retrieved context\n"
                "Project Orion uses DuckDB for analytics.\n\n"
                "## User\nWhich database should Project Orion use?"
            ),
            events=(
                TraceEvent(
                    event_type="retrieval_stage1_completed",
                    source_package="rag_lib",
                    source_component="FakeRagPipeline",
                    payload={"selected_count": 1},
                    tags=("rag", "retrieval"),
                ),
            ),
            diagnostics={"selected_count": 1, "collection": "default"},
        )

    def describe_component(self):  # pragma: no cover - RagAugmenter fallback also covers this path.
        return AugmenterService().describe_augmenter("baseline")


def _request() -> AugmentRequest:
    return AugmentRequest(
        session_id="spine-session",
        user_text="Which database should Project Orion use?",
        query="Project Orion analytics database",
        max_prompt_tokens=1024,
        reserve_output_tokens=64,
    )


def _assert_normalized_trace(
    *,
    augmenter_id: str,
    result: Any,
    inspector: InspectorService,
) -> dict[str, Any]:
    trace = inspector.inspect(
        augmenter_id=augmenter_id,
        augment_result=result,
        user_text=_request().user_text,
        session_id=_request().session_id,
    )

    assert trace["turn"]["session_id"] == _request().session_id
    assert get_final_prompt(trace, fallback=result.prompt)
    assert get_sections(trace)
    assert isinstance(get_token_accounting(trace), dict)
    return trace


def test_baseline_and_engram_augmenters_normalize_to_inspector_traces(tmp_path):
    service = AugmenterService(engram_base_dir=tmp_path, engram_project_id="spine")
    inspector = InspectorService()
    request = _request()

    assert "baseline" in service.list_augmenters()
    assert "engram" in service.list_augmenters()

    baseline = service.create(
        "baseline",
        session_id=request.session_id,
        options={"system_prompt": "Answer from provided context only."},
    )
    baseline_result = baseline.augment(request)
    baseline_trace = _assert_normalized_trace(
        augmenter_id="baseline",
        result=baseline_result,
        inspector=inspector,
    )
    assert baseline_result.metadata["source"] == "baseline"
    assert "Project Orion" in get_final_prompt(baseline_trace, fallback="")

    engram = service.create(
        "engram",
        session_id=request.session_id,
        options={
            "base_dir": tmp_path,
            "project_id": "spine",
            "system_prompt": "Answer from durable memory when relevant.",
        },
    )
    try:
        engram.new_session(request.session_id)
        engram.add_turn("user", "Project Orion uses DuckDB for analytics.", request.session_id)
        engram_result = engram.augment(request)
        engram_trace = _assert_normalized_trace(
            augmenter_id="engram",
            result=engram_result,
            inspector=inspector,
        )

        assert engram_result.metadata["source"] == "engram"
        assert "DuckDB" in get_final_prompt(engram_trace, fallback=engram_result.prompt)
    finally:
        pm = getattr(engram, "_pm", None)
        if pm is not None and hasattr(pm, "close"):
            pm.close()


def test_full_engram_augmenter_normalizes_or_skips_cleanly(tmp_path):
    service = AugmenterService(engram_base_dir=tmp_path, engram_project_id="spine")
    readiness = service.get_augmenter_readiness(
        "engram",
        options={"base_dir": tmp_path, "project_id": "spine"},
    )
    if not readiness.can_run:
        pytest.skip(readiness.message)

    # Full Engram may start background maintenance components and pull in optional
    # persistence layers. Keep the default repo smoke test fast and deterministic;
    # run the live full-Engram augmentation path explicitly when desired.
    if os.environ.get("AI_TOOLS_TEST_FULL_ENGRAM") != "1":
        pytest.skip(
            "set AI_TOOLS_TEST_FULL_ENGRAM=1 to run the live full-Engram augmenter smoke test"
        )

    request = _request()
    augmenter = service.create(
        "engram",
        session_id=request.session_id,
        options={"base_dir": tmp_path, "project_id": "spine"},
    )
    augmenter.new_session(request.session_id)
    augmenter.add_turn("user", "Project Orion uses DuckDB for analytics.", request.session_id)

    try:
        result = augmenter.augment(request)
        trace = _assert_normalized_trace(
            augmenter_id="engram",
            result=result,
            inspector=InspectorService(),
        )

        assert result.metadata["source"] == "engram"
        assert "Project Orion" in get_final_prompt(trace, fallback=result.prompt)
    finally:
        pm = getattr(augmenter, "_pm", None)
        if pm is not None and hasattr(pm, "close"):
            pm.close()


def test_rag_augmenter_normalizes_retrieval_trace_without_live_services(monkeypatch):
    monkeypatch.setattr(RagAugmenter, "_ensure_pipeline", lambda self: _FakeRagPipeline())

    service = AugmenterService()
    request = _request()
    augmenter = service.create(
        "rag",
        session_id=request.session_id,
        options={"collection": "default", "system_prompt": "Use retrieved context."},
    )

    result = augmenter.augment(request)
    trace = _assert_normalized_trace(
        augmenter_id="rag",
        result=result,
        inspector=InspectorService(),
    )

    assert result.metadata["source"] == "rag"
    assert get_retrieval_summary(trace)["selected_count"] == 1
    assert get_retrieval_events(trace)[0]["event_type"] == "retrieval_stage1_completed"
    assert "DuckDB" in get_final_prompt(trace, fallback=result.prompt)
