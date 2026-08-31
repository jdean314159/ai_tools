from __future__ import annotations

from datetime import datetime, timezone

from llm_inspector_ui.state.models import RunArtifact
from llm_inspector_ui.utils.teaching_text import (
    describe_compare_group_for_beginners,
    describe_compare_group_for_teaching,
    describe_readiness_steps_for_beginners,
    describe_run_for_beginners,
    describe_run_for_teaching,
    explain_agent_tab,
    explain_agent_tab_for_beginners,
    explain_evidence_tab,
    explain_evidence_tab_for_beginners,
    explain_prompt_tab,
    explain_prompt_tab_for_beginners,
    explain_readiness_for_beginners,
    explain_readiness_for_teaching,
    explain_retrieval_tab,
    explain_retrieval_tab_for_beginners,
    explain_token_tab_for_beginners,
)


def _run(
    *, augmenter_id: str, trace: dict, status: str = "ok", error: str | None = None
) -> RunArtifact:
    return RunArtifact(
        run_id=f"run-{augmenter_id}",
        session_id="session-1",
        turn_id="turn-1",
        assistant_turn_id=None,
        created_at=datetime.now(timezone.utc),
        engine_id="echo",
        model_id="echo",
        augmenter_id=augmenter_id,
        mode="compare",
        status=status,
        error=error,
        user_text="hello",
        prompt="prompt",
        response_text="response",
        trace=trace,
    )


def test_describe_compare_group_mentions_control_and_augmented_checks():
    runs = [
        _run(augmenter_id="baseline", trace={}),
        _run(augmenter_id="engram", trace={}),
        _run(augmenter_id="rag", trace={}),
    ]
    lessons = describe_compare_group_for_teaching(runs)
    assert any("control" in lesson for lesson in lessons)
    assert any("memory" in lesson for lesson in lessons)
    assert any("retrieval" in lesson for lesson in lessons)


def test_beginner_compare_group_describes_step_by_step_reading_order():
    runs = [
        _run(augmenter_id="baseline", trace={}),
        _run(augmenter_id="rag", trace={}),
    ]
    steps = describe_compare_group_for_beginners(runs)
    assert any("Start with the Response tab" in step for step in steps)
    assert any("Treat baseline as the control branch" in step for step in steps)
    assert any("RAG branch" in step for step in steps)


def test_describe_run_for_teaching_mentions_evidence_retrieval_and_tokens():
    run = _run(
        augmenter_id="rag",
        trace={
            "context": {
                "evidence": [{"source": "doc.txt", "text": "fact"}],
                "token_accounting": {"total_tokens": 321},
                "signals": {"retrieval_summary": {"selected_count": 2}},
            },
        },
    )
    text = describe_run_for_teaching(run)
    assert "retrieval stage selected 2 documents" in text
    assert "1 evidence item" in text
    assert "321 total tokens" in text


def test_beginner_run_description_explains_branch_role():
    run = _run(
        augmenter_id="engram",
        trace={
            "context": {
                "evidence": [{"source": "memory", "text": "fact"}],
                "token_accounting": {"total_tokens": 80},
            },
        },
    )
    text = describe_run_for_beginners(run)
    assert "memory branch" in text
    assert "stored context" in text
    assert "80 tokens" in text


def test_prompt_explainers_distinguish_teaching_and_beginner_language():
    trace = {
        "context": {
            "sections": [{"title": "Final prompt", "text": "hello"}],
            "token_accounting": {"total_tokens": 100, "compressed": True, "truncated": True},
        }
    }
    text = explain_prompt_tab(trace)
    beginner = explain_prompt_tab_for_beginners(trace)
    assert "100 tokens" in text
    assert "Compression was applied" in text
    assert "Truncation occurred" in text
    assert "exact text the model saw" in beginner
    assert "did not get everything" in beginner


def test_evidence_explainers_distinguish_missing_vs_present_support():
    missing = explain_evidence_tab({"context": {"evidence": []}})
    present = explain_evidence_tab(
        {"context": {"evidence": [{"source": "doc.txt", "text": "fact"}]}}
    )
    beginner_missing = explain_evidence_tab_for_beginners({"context": {"evidence": []}})
    beginner_present = explain_evidence_tab_for_beginners(
        {"context": {"evidence": [{"source": "doc.txt", "text": "fact"}]}}
    )
    assert "No explicit evidence" in missing
    assert "1 evidence item" in present
    assert "warning sign" in beginner_missing
    assert "actually inspect" in beginner_present


def test_retrieval_explainers_mention_selected_documents_and_events():
    trace = {
        "context": {"signals": {"retrieval_summary": {"selected_count": 3}}},
        "events": [
            {"event_type": "retrieval_stage1_completed", "tags": ["retrieval"]},
            {"event_type": "query_expanded", "tags": ["rag"]},
        ],
    }
    text = explain_retrieval_tab(trace)
    beginner = explain_retrieval_tab_for_beginners(trace)
    assert "selected 3 documents" in text
    assert "2 retrieval-stage events" in text
    assert "kept 3 documents" in beginner
    assert "improves the answer" in beginner


def test_agent_explainers_mention_blocked_degraded_and_approval():
    trace = {
        "context": {"signals": {"agent_summary": {"tool_count": 1}}},
        "events": [
            {
                "event_type": "agent_tool_result",
                "source_package": "agent_lib",
                "payload": {
                    "tool_result": {
                        "name": "run_command",
                        "meta": {
                            "error": "command_denied",
                            "approval_required": True,
                            "sandbox_fallback_used": True,
                        },
                    }
                },
                "tags": ["agent", "approval", "blocked", "degraded"],
            }
        ],
    }
    text = explain_agent_tab(trace)
    beginner = explain_agent_tab_for_beginners(trace)
    assert "1 step required approval" in text
    assert "1 step was blocked" in text
    assert "1 step ran in a degraded mode" in text
    assert "behaved safely and predictably" in beginner
    assert "not proof" in beginner


def test_readiness_explainers_distinguish_engine_failure_modes():
    assert "not registered" in explain_readiness_for_teaching(
        status="error", exists=False, reachable=None, models_available=None
    )
    assert "unreachable" in explain_readiness_for_teaching(
        status="error", exists=True, reachable=False, models_available=None
    )
    assert "no models are visible" in explain_readiness_for_teaching(
        status="warning", exists=True, reachable=True, models_available=False
    )
    assert "ready" in explain_readiness_for_teaching(
        status="ok", exists=True, reachable=True, models_available=True
    )


def test_beginner_readiness_explanations_and_steps_are_actionable():
    text = explain_readiness_for_beginners(
        status="warning", exists=True, reachable=True, models_available=False
    )
    steps = describe_readiness_steps_for_beginners(
        status="warning", exists=True, reachable=True, models_available=False
    )
    assert "no models are available" in text
    assert any("register at least one model" in step for step in steps)
    assert any("baseline call" in step for step in steps)


def test_beginner_token_explainer_mentions_cost_signal():
    text = explain_token_tab_for_beginners({"context": {"token_accounting": {"total_tokens": 42}}})
    assert "rough cost meter" in text
    assert "42 tokens" in text
