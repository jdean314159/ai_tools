from __future__ import annotations

import json

import pytest

from diagnostics_agent import (
    ChatTurn,
    CollectedLogs,
    DiagnosticResult,
    FollowupChat,
    LogInterpreter,
    LogTriage,
    RemoteEngineRefused,
)
from llm_engines.contracts import ChatMessage, GenerationRequest, GenerationResponse, UsageStats


def test_followup_answer_returns_engine_text() -> None:
    engine = _StubEngine("Because the disk finding is operationally relevant.")

    answer = FollowupChat(engine).answer(_result(), "Why is disk medium?")

    assert answer == "Because the disk finding is operationally relevant."


def test_followup_prompt_is_grounded_in_result_and_question() -> None:
    engine = _StubEngine("Grounded answer.")

    FollowupChat(engine).answer(_result(), "Why did ata10 matter?")

    request = engine.requests[0]
    system_text = request.messages[0].content or ""
    grounding_text = request.messages[1].content or ""
    assert "Answer only from the provided diagnostic results" in system_text
    assert "Do not invent system state" in system_text
    assert "disk_io_error" in grounding_text
    assert "ata10: softreset failed" in grounding_text
    assert "excluded_self_noise" in grounding_text
    assert request.messages[-1].content == "Why did ata10 matter?"


def test_followup_rejects_remote_engine_by_default() -> None:
    with pytest.raises(RemoteEngineRefused):
        FollowupChat(_StubEngine("x", backend="openai"))


def test_followup_allows_remote_engine_with_explicit_override() -> None:
    chat = FollowupChat(_StubEngine("x", backend="openai"), allow_remote=True)

    assert isinstance(chat, FollowupChat)


def test_followup_caps_history_to_recent_turns() -> None:
    history = [
        ChatTurn("user", "old user"),
        ChatTurn("assistant", "old assistant"),
        ChatTurn("user", "recent user"),
        ChatTurn("assistant", "recent assistant"),
    ]
    engine = _StubEngine("Answer.")

    FollowupChat(engine, max_history_turns=2).answer(_result(), "new question", history)

    contents = [message.content for message in engine.requests[0].messages]
    assert "old user" not in contents
    assert "old assistant" not in contents
    assert "recent user" in contents
    assert "recent assistant" in contents
    assert contents[-1] == "new question"


def test_followup_zero_history_cap_drops_all_history() -> None:
    history = [ChatTurn("user", "old user"), ChatTurn("assistant", "old assistant")]
    engine = _StubEngine("Answer.")

    FollowupChat(engine, max_history_turns=0).answer(_result(), "new question", history)

    contents = [message.content for message in engine.requests[0].messages]
    assert "old user" not in contents
    assert "old assistant" not in contents
    assert contents[-1] == "new question"


def test_followup_does_not_mutate_result() -> None:
    result = _result()
    before = result.to_dict()

    FollowupChat(_StubEngine("Answer.")).answer(result, "What changed?")

    assert result.to_dict() == before


def _result() -> DiagnosticResult:
    source = "\n".join(
        [
            "2026-05-29T14:03:11-07:00 host kernel: ata10: softreset failed (device not ready)",
            "2026-05-29T14:04:11-07:00 host app[2222]: warning connection reset from 198.51.100.10:443",
        ]
    )
    summary = LogTriage().triage(source)
    interpretation = LogInterpreter(_StubEngine(_interpretation_json())).interpret(summary)
    collected = CollectedLogs(
        staging_path=__file__,
        command=["journalctl", "-o", "json", "-p", "warning", "--since", "-24h"],
        source_description="journalctl warning since -24h",
        byte_count=len(source.encode("utf-8")),
    )
    return DiagnosticResult(
        collected=collected,
        sandbox_result=None,
        summary=summary,
        interpretation=interpretation,
        interpretation_error=None,
        audit={},
    )


def _interpretation_json() -> str:
    return json.dumps(
        {
            "reasoning": "Disk reset warning and app warning are present.",
            "summary": "Disk reset warning needs attention.",
            "security_risk": "none",
            "operational_risk": "low",
            "prioritized_concerns": [],
            "recommended_checks": ["Run smartctl."],
        }
    )


class _StubEngine:
    def __init__(self, content: str, *, backend: str = "ollama") -> None:
        self.backend = backend
        self.content = content
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=self.content),
            finish_reason="stop",
            usage=UsageStats(input_tokens=10, output_tokens=20, total_tokens=30),
            model_name="stub",
            backend=self.backend,
        )
