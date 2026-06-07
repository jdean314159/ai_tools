from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path

import pytest

from diagnostics_agent import (
    ConcernAssessment,
    Interpretation,
    InterpretationParseError,
    LogInterpreter,
    LogTriage,
    RemoteEngineRefused,
    TriageConfig,
)
from diagnostics_agent.interpret import (
    _apply_risk_coherence,
    _count_request_tokens,
    _summary_for_prompt,
)
from diagnostics_agent.system_facts import SystemFacts
from diagnostics_agent.triage import Finding, Severity
from llm_engines.contracts import ChatMessage, GenerationRequest, GenerationResponse, UsageStats


FIXTURES = Path(__file__).parent / "fixtures"


def test_interpret_builds_schema_request_with_summary_content() -> None:
    engine = _StubEngine(_valid_interpretation_json())
    summary = _summary()

    LogInterpreter(engine).interpret(summary)

    request = engine.requests[0]
    assert request.json_schema == Interpretation.model_json_schema()
    assert request.temperature == 0.2
    assert request.max_tokens == 2048
    user_text = request.messages[1].content or ""
    assert "ssh_failed_auth" in user_text
    assert "warning connection reset from <IP>:<PORT>" in user_text
    assert "recommended_checks" in user_text

    system_text = request.messages[0].content or ""
    assert "Do not invent events" in system_text
    assert "Verified host facts" not in user_text
    assert "never assert an OS version" in system_text


def test_interpret_includes_system_facts_before_triage_json() -> None:
    engine = _StubEngine(_valid_interpretation_json())
    facts = SystemFacts(
        hostname="hammerhead",
        kernel_release="6.17.0-23-generic",
        kernel_version="#1 SMP",
        os_name="Ubuntu 25.10",
        os_version="25.10",
        arch="x86_64",
    )

    LogInterpreter(engine).interpret(_summary(), system_facts=facts)

    user_text = engine.requests[0].messages[1].content or ""
    assert "Verified host facts" in user_text
    assert "- hostname: hammerhead" in user_text
    assert "- os: Ubuntu 25.10" in user_text
    assert "- kernel: 6.17.0-23-generic" in user_text
    assert user_text.index("Verified host facts") < user_text.index("Triage summary JSON:")


def test_interpret_without_system_facts_keeps_prompt_unanchored() -> None:
    engine = _StubEngine(_valid_interpretation_json())

    LogInterpreter(engine).interpret(_summary())

    user_text = engine.requests[0].messages[1].content or ""
    assert "Verified host facts" not in user_text
    assert "No verified host facts" not in user_text


def test_prompt_guides_auth_risk_by_service_and_count() -> None:
    engine = _StubEngine(_valid_interpretation_json())

    LogInterpreter(engine).interpret(_summary())

    user_text = engine.requests[0].messages[1].content or ""
    assert "weight risk by service and count" in user_text
    assert "sshd, sudo, or login" in user_text
    assert "cinnamon-screensaver, polkit, or gdm" in user_text
    assert "A single auth failure is usually low risk" in user_text


def test_prompt_separates_security_and_operational_risk() -> None:
    engine = _StubEngine(_valid_interpretation_json())

    LogInterpreter(engine).interpret(_summary())

    user_text = engine.requests[0].messages[1].content or ""
    assert "security_risk" in user_text
    assert "operational_risk" in user_text
    assert "Do not equate 'not a security threat' with 'low severity'" in user_text
    assert "Repeated disk/ATA errors" in user_text
    assert "medium or higher operational_risk" in user_text


def test_interpret_parses_valid_json_response() -> None:
    interpreter = LogInterpreter(_StubEngine(_valid_interpretation_json()))

    result = interpreter.interpret(_summary())

    assert result.summary == "Repeated SSH failures and app warnings need review."
    assert result.security_risk == "medium"
    assert result.operational_risk == "medium"
    assert result.prioritized_concerns[0].finding_ref == "ssh_failed_auth"
    assert result.recommended_checks == ["Review recent auth logs by source IP."]


def test_interpret_extracts_json_from_markdown_response() -> None:
    interpreter = LogInterpreter(
        _StubEngine(f"Here is the object:\n```json\n{_valid_interpretation_json()}\n```")
    )

    result = interpreter.interpret(_summary())

    assert result.summary == "Repeated SSH failures and app warnings need review."
    assert result.security_risk == "medium"


def test_interpret_normalizes_log_severity_labels_to_risk_labels() -> None:
    payload = json.dumps(
        {
            "reasoning": "x",
            "summary": "x",
            "security_risk": "WARNING",
            "operational_risk": "ERROR",
            "prioritized_concerns": [
                {
                    "finding_ref": "ssh_failed_auth",
                    "rationale": "x",
                    "severity": "WARNING",
                }
            ],
            "recommended_checks": ["x"],
        }
    )

    result = LogInterpreter(_StubEngine(payload)).interpret(_auth_summary())

    assert result.security_risk == "medium"
    assert result.operational_risk == "high"
    assert result.prioritized_concerns[0].severity == "medium"


def test_operational_floor_clamps_disk_findings() -> None:
    summary = LogTriage().triage(
        [
            "2026-05-29T14:03:11-07:00 host kernel: ata10: softreset failed (device not ready)",
            "2026-05-29T14:04:11-07:00 host kernel: ata10: softreset failed (device not ready)",
        ]
    )
    payload = json.dumps(
        {
            "reasoning": "The ATA reset issue is not an attack.",
            "summary": "Storage reset warnings were observed.",
            "security_risk": "none",
            "operational_risk": "none",
            "prioritized_concerns": [
                {
                    "finding_ref": "disk_io_error",
                    "rationale": "Repeated ATA reset failures may indicate storage instability.",
                    "severity": "low",
                }
            ],
            "recommended_checks": ["Run smartctl."],
        }
    )

    result = LogInterpreter(_StubEngine(payload)).interpret(summary)

    assert summary.findings[0].rule_name == "disk_io_error"
    assert summary.findings[0].category == "disk"
    assert result.security_risk == "none"
    assert result.operational_risk == "medium"
    assert result.prioritized_concerns[0].severity == "medium"


def test_operational_floor_synthesizes_missing_concern() -> None:
    summary = LogTriage().triage(
        ["2026-05-29T14:03:11-07:00 host kernel: ata10: softreset failed (device not ready)"]
    )
    payload = json.dumps(
        {
            "reasoning": "The ATA reset issue is not an attack.",
            "summary": "Storage reset warning observed.",
            "security_risk": "none",
            "operational_risk": "none",
            "prioritized_concerns": [],
            "recommended_checks": ["Run smartctl."],
        }
    )

    result = LogInterpreter(_StubEngine(payload)).interpret(summary)

    assert result.operational_risk == "medium"
    assert len(result.prioritized_concerns) == 1
    concern = result.prioritized_concerns[0]
    assert concern.finding_ref == "disk_io_error"
    assert concern.severity == "medium"
    assert "Deterministic triage classified this as a disk finding" in concern.rationale


def test_operational_floor_does_not_duplicate_template_referenced_concern() -> None:
    summary = LogTriage().triage(
        ["2026-05-29T14:03:11-07:00 host kernel: ata10: softreset failed (device not ready)"]
    )
    finding_template = summary.findings[0].template
    payload = json.dumps(
        {
            "reasoning": "The ATA reset issue is not an attack.",
            "summary": "Storage reset warning observed.",
            "security_risk": "none",
            "operational_risk": "none",
            "prioritized_concerns": [
                {
                    "finding_ref": finding_template,
                    "rationale": "Repeated ATA reset failures may indicate storage instability.",
                    "severity": "low",
                }
            ],
            "recommended_checks": ["Run smartctl."],
        }
    )

    result = LogInterpreter(_StubEngine(payload)).interpret(summary)

    assert result.operational_risk == "medium"
    assert len(result.prioritized_concerns) == 1
    assert result.prioritized_concerns[0].finding_ref == finding_template
    assert result.prioritized_concerns[0].severity == "medium"


def test_operational_floor_clamps_critical_memory_findings_to_high() -> None:
    summary = LogTriage().triage(
        ["2026-05-29T14:03:11-07:00 host kernel: Out of memory: Killed process 1234 (worker)"]
    )
    payload = json.dumps(
        {
            "reasoning": "The OOM event is not an attacker indicator.",
            "summary": "OOM kill observed.",
            "security_risk": "none",
            "operational_risk": "low",
            "prioritized_concerns": [
                {
                    "finding_ref": "oom_kill",
                    "rationale": "OOM kill affects reliability.",
                    "severity": "low",
                }
            ],
            "recommended_checks": ["Review memory pressure."],
        }
    )

    result = LogInterpreter(_StubEngine(payload)).interpret(summary)

    assert summary.findings[0].rule_name == "oom_kill"
    assert summary.findings[0].category == "memory"
    assert result.security_risk == "none"
    assert result.operational_risk == "high"
    assert result.prioritized_concerns[0].severity == "high"


def test_operational_floor_does_not_clamp_auth_findings() -> None:
    payload = json.dumps(
        {
            "reasoning": "One SSH failure is not necessarily an attack.",
            "summary": "Single auth failure observed.",
            "security_risk": "low",
            "operational_risk": "none",
            "prioritized_concerns": [
                {
                    "finding_ref": "ssh_failed_auth",
                    "rationale": "One failed login should be reviewed but is not operational failure.",
                    "severity": "low",
                }
            ],
            "recommended_checks": ["Review auth logs."],
        }
    )

    result = LogInterpreter(_StubEngine(payload)).interpret(_auth_summary())

    assert result.operational_risk == "none"
    assert result.prioritized_concerns[0].severity == "low"


def test_risk_coherence_raises_higher_axis_for_auth_gap() -> None:
    interpretation = _interpretation(
        security_risk="none",
        operational_risk="low",
        concern_severity="high",
    )

    result = _apply_risk_coherence(interpretation)

    assert result.security_risk == "none"
    assert result.operational_risk == "high"
    assert result.prioritized_concerns == interpretation.prioritized_concerns


def test_risk_coherence_leaves_already_coherent_interpretation_unchanged() -> None:
    interpretation = _interpretation(
        security_risk="high",
        operational_risk="low",
        concern_severity="medium",
    )

    result = _apply_risk_coherence(interpretation)

    assert result is interpretation


def test_risk_coherence_leaves_empty_concerns_unchanged() -> None:
    interpretation = Interpretation(
        reasoning="x",
        summary="x",
        security_risk="none",
        operational_risk="none",
        prioritized_concerns=[],
        recommended_checks=["x"],
    )

    result = _apply_risk_coherence(interpretation)

    assert result is interpretation


def test_risk_coherence_tie_break_raises_operational_risk() -> None:
    interpretation = _interpretation(
        security_risk="low",
        operational_risk="low",
        concern_severity="high",
    )

    result = _apply_risk_coherence(interpretation)

    assert result.security_risk == "low"
    assert result.operational_risk == "high"


def test_risk_coherence_maps_info_concern_to_low_axis() -> None:
    interpretation = _interpretation(
        security_risk="none",
        operational_risk="none",
        concern_severity="info",
    )

    result = _apply_risk_coherence(interpretation)

    assert result.security_risk == "none"
    assert result.operational_risk == "low"


def test_risk_coherence_composes_after_critical_disk_floor() -> None:
    summary = LogTriage().triage(
        ["2026-05-29T14:03:11-07:00 host kernel: kernel Oops: unable to handle kernel NULL pointer dereference"]
    )
    payload = json.dumps(
        {
            "reasoning": "Kernel bug was observed.",
            "summary": "Kernel bug observed.",
            "security_risk": "none",
            "operational_risk": "low",
            "prioritized_concerns": [],
            "recommended_checks": ["Review kernel logs."],
        }
    )

    result = LogInterpreter(_StubEngine(payload)).interpret(summary)

    assert summary.findings[0].rule_name == "kernel_bug"
    assert result.security_risk == "none"
    assert result.operational_risk == "high"
    assert len(result.prioritized_concerns) == 1
    assert result.prioritized_concerns[0].finding_ref == "kernel_bug"
    assert result.prioritized_concerns[0].severity == "high"


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("UNKNOWN", "info"),
        ("DEBUG", "info"),
        ("INFO", "low"),
        ("NOTICE", "low"),
        ("WARNING", "medium"),
        ("ERROR", "high"),
        ("CRITICAL", "critical"),
        ("ALERT", "critical"),
        ("EMERGENCY", "critical"),
    ],
)
def test_concern_severity_normalizes_syslog_labels(label: str, expected: str) -> None:
    concern = {
        "finding_ref": "ref",
        "severity": label,
        "rationale": "reason",
    }

    parsed = Interpretation.model_validate(
        {
            "reasoning": "x",
            "summary": "x",
            "security_risk": "low",
            "operational_risk": "low",
            "prioritized_concerns": [concern],
            "recommended_checks": ["check"],
        }
    )

    assert parsed.prioritized_concerns[0].severity == expected


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("UNKNOWN", "none"),
        ("DEBUG", "none"),
        ("INFO", "low"),
        ("NOTICE", "low"),
        ("WARNING", "medium"),
        ("ERROR", "high"),
        ("CRITICAL", "critical"),
        ("ALERT", "critical"),
        ("EMERGENCY", "critical"),
    ],
)
def test_interpretation_risks_normalize_syslog_labels(label: str, expected: str) -> None:
    parsed = Interpretation.model_validate(
        {
            "reasoning": "x",
            "summary": "x",
            "security_risk": label,
            "operational_risk": label,
            "prioritized_concerns": [
                {
                    "finding_ref": "ref",
                    "rationale": "reason",
                    "severity": "low",
                }
            ],
            "recommended_checks": ["check"],
        }
    )

    assert parsed.security_risk == expected
    assert parsed.operational_risk == expected


def test_remote_engine_refused_by_default() -> None:
    with pytest.raises(RemoteEngineRefused):
        LogInterpreter(_StubEngine(_valid_interpretation_json(), backend="openai"))


def test_unknown_backend_refused_by_default() -> None:
    with pytest.raises(RemoteEngineRefused):
        LogInterpreter(_StubEngine(_valid_interpretation_json(), backend="mycloud"))


@pytest.mark.parametrize("backend", ["ollama", "llamacpp", "llama_cpp", "vllm", "mock"])
def test_known_local_backends_allowed_by_default(backend: str) -> None:
    interpreter = LogInterpreter(_StubEngine(_valid_interpretation_json(), backend=backend))

    result = interpreter.interpret(_summary())

    assert result.security_risk == "medium"


def test_remote_engine_allowed_with_explicit_override() -> None:
    interpreter = LogInterpreter(
        _StubEngine(_valid_interpretation_json(), backend="mycloud"),
        allow_remote=True,
    )

    result = interpreter.interpret(_summary())

    assert result.security_risk == "medium"


def test_malformed_json_raises_parse_error() -> None:
    interpreter = LogInterpreter(_StubEngine("not json"))

    with pytest.raises(InterpretationParseError):
        interpreter.interpret(_summary())


def test_parse_failure_retries_with_correction_message() -> None:
    first_response = json.dumps(
        {
            "reasoning": "x",
            "summary": "x",
            "security_risk": "low",
        }
    )
    engine = _StubEngine([first_response, _valid_interpretation_json()])

    result = LogInterpreter(engine).interpret(_summary())

    assert result.security_risk == "medium"
    assert result.operational_risk == "medium"
    assert len(engine.requests) == 2
    retry_request = engine.requests[1]
    assert retry_request.temperature == 0.0
    assert retry_request.messages[-2].role == "assistant"
    assert retry_request.messages[-2].content == first_response
    correction = retry_request.messages[-1].content or ""
    assert "prioritized_concerns" in correction
    assert "security_risk" in correction
    assert "operational_risk" in correction
    assert "recommended_checks" in correction
    assert "Validation error" in correction


def test_prompt_is_deterministic_for_same_summary() -> None:
    summary = _summary()
    first_engine = _StubEngine(_valid_interpretation_json())
    second_engine = _StubEngine(_valid_interpretation_json())

    LogInterpreter(first_engine).interpret(summary)
    LogInterpreter(second_engine).interpret(summary)

    assert [message.model_dump() for message in first_engine.requests[0].messages] == [
        message.model_dump() for message in second_engine.requests[0].messages
    ]


def test_prompt_compacts_large_raw_examples() -> None:
    raw_json_example = json.dumps(
        {
            "__REALTIME_TIMESTAMP": "1780077600000000",
            "_HOSTNAME": "host",
            "SYSLOG_IDENTIFIER": "daemon",
            "PRIORITY": "4",
            "MESSAGE": "x" * 1000,
            "EXTRA_FIELD": "y" * 1000,
        }
    )
    engine = _StubEngine(_valid_interpretation_json())
    summary = LogTriage().triage([raw_json_example])

    LogInterpreter(engine).interpret(summary)

    user_text = engine.requests[0].messages[1].content or ""
    assert "..." in user_text
    assert "y" * 500 not in user_text


def test_prompt_under_budget_keeps_summary_unchanged() -> None:
    engine = _CountingStubEngine(_valid_interpretation_json(), n_ctx=20_000)
    summary = _priority_summary()

    LogInterpreter(engine).interpret(summary)

    assert _prompt_summary_from_request(engine.requests[0]) == _summary_for_prompt(summary)


def test_prompt_over_budget_drops_lowest_priority_findings_and_stays_valid(
    caplog,
) -> None:
    summary = _priority_summary()
    sizing_engine = _CountingStubEngine(_valid_interpretation_json(), n_ctx=20_000)
    sizing_interpreter = LogInterpreter(sizing_engine)
    one_finding = _summary_for_prompt(summary)
    one_finding["findings"] = one_finding["findings"][:1]
    one_finding["top_clusters"] = []
    one_finding_request = sizing_interpreter._request_for_prompt_summary(  # noqa: SLF001
        one_finding,
        system_facts=None,
    )
    one_finding_tokens = _count_request_tokens(
        one_finding_request,
        count_tokens=sizing_engine.count_tokens,
    )
    context_limit = one_finding_tokens + 2048 + 512
    engine = _CountingStubEngine(_valid_interpretation_json(), n_ctx=context_limit)

    with caplog.at_level(logging.WARNING):
        LogInterpreter(engine).interpret(summary)

    request = engine.requests[0]
    prompt_summary = _prompt_summary_from_request(request)
    assert _count_request_tokens(request, count_tokens=engine.count_tokens) <= (
        context_limit - 2048 - 512
    )
    assert [item["rule_name"] for item in prompt_summary["findings"]] == ["critical_recent"]
    assert prompt_summary["top_clusters"] == []
    assert "Do not invent events" in (request.messages[0].content or "")
    assert request.json_schema == Interpretation.model_json_schema()
    assert "findings_dropped=2" in caplog.text


def test_prompt_clamp_uses_engine_token_counter() -> None:
    engine = _CountingStubEngine(_valid_interpretation_json(), n_ctx=20_000)

    LogInterpreter(engine).interpret(_summary())

    assert engine.counted_texts


def test_explicit_context_limit_overrides_engine_context() -> None:
    engine = _CountingStubEngine(_valid_interpretation_json(), n_ctx=2560)

    result = LogInterpreter(engine, context_limit=20_000).interpret(_summary())

    assert result.summary


def test_configured_max_tokens_above_floor_is_used_as_reserve_and_request_cap() -> None:
    engine = _CountingStubEngine(_valid_interpretation_json(), n_ctx=20_000)

    LogInterpreter(engine, max_tokens=3072).interpret(_summary())

    assert engine.requests[0].max_tokens == 3072


def test_prompt_clamp_uses_heuristic_without_engine_counter() -> None:
    engine = _StubEngine(_valid_interpretation_json(), n_ctx=20_000)

    LogInterpreter(engine).interpret(_summary())

    assert _count_request_tokens(engine.requests[0]) <= 20_000 - 2048 - 1024


def test_fixed_prompt_over_budget_raises_clear_error() -> None:
    engine = _CountingStubEngine(_valid_interpretation_json(), n_ctx=2560)

    with pytest.raises(
        ValueError,
        match=(
            r"fixed prompt exceeds token budget: prompt_tokens=\d+, budget=0, "
            r"context_limit=2560, output_reserve=2048, safety_margin=512"
        ),
    ):
        LogInterpreter(engine).interpret(_priority_summary())

    assert engine.requests == []


def test_interpretation_schema_keeps_reasoning_first() -> None:
    assert list(Interpretation.model_fields)[:1] == ["reasoning"]
    assert list(Interpretation.model_fields)[:4] == [
        "reasoning",
        "summary",
        "security_risk",
        "operational_risk",
    ]


def test_concern_schema_keeps_rationale_before_severity() -> None:
    assert list(ConcernAssessment.model_fields) == ["finding_ref", "rationale", "severity"]


def _summary():
    source = (FIXTURES / "mixed_noise.log").read_text(encoding="utf-8")
    return LogTriage(TriageConfig(max_clusters=2)).triage(source)


def _auth_summary():
    return LogTriage().triage(
        [
            "2026-05-29T14:03:11-07:00 host sshd[1234]: "
            "Failed password for invalid user admin from 192.0.2.10 port 53001 ssh2"
        ]
    )


def _priority_summary():
    summary = LogTriage().triage([])
    findings = (
        _finding("critical_recent", Severity.CRITICAL, "2026-06-06T12:00:00+00:00"),
        _finding("warning_recent", Severity.WARNING, "2026-06-06T11:00:00+00:00"),
        _finding("notice_old", Severity.NOTICE, "2026-06-05T12:00:00+00:00"),
    )
    return replace(summary, findings=findings)


def _finding(rule_name: str, severity: Severity, last_seen: str) -> Finding:
    timestamp = datetime.fromisoformat(last_seen).astimezone(timezone.utc)
    return Finding(
        rule_name=rule_name,
        category="test",
        severity=severity,
        count=1,
        template=f"{rule_name} template",
        first_seen=timestamp,
        last_seen=timestamp,
        examples=(f"{rule_name} " + "x" * 300,),
    )


def _prompt_summary_from_request(request: GenerationRequest) -> dict:
    user_text = request.messages[1].content or ""
    return json.loads(user_text.split("Triage summary JSON:\n", 1)[1])


def _valid_interpretation_json() -> str:
    return json.dumps(
        {
            "reasoning": "The summary contains repeated SSH failures plus frequent warning clusters.",
            "summary": "Repeated SSH failures and app warnings need review.",
            "security_risk": "medium",
            "operational_risk": "low",
            "prioritized_concerns": [
                {
                    "finding_ref": "ssh_failed_auth",
                    "rationale": "Repeated failed authentication can indicate probing.",
                    "severity": "medium",
                }
            ],
            "recommended_checks": ["Review recent auth logs by source IP."],
        }
    )


def _interpretation(
    *,
    security_risk: str,
    operational_risk: str,
    concern_severity: str,
) -> Interpretation:
    return Interpretation.model_validate(
        {
            "reasoning": "x",
            "summary": "x",
            "security_risk": security_risk,
            "operational_risk": operational_risk,
            "prioritized_concerns": [
                {
                    "finding_ref": "ref",
                    "rationale": "reason",
                    "severity": concern_severity,
                }
            ],
            "recommended_checks": ["check"],
        }
    )


class _StubEngine:
    def __init__(
        self,
        content: str | list[str],
        *,
        backend: str = "ollama",
        n_ctx: int = 8192,
    ) -> None:
        self.backend = backend
        self.n_ctx = n_ctx
        self.contents = [content] if isinstance(content, str) else list(content)
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.contents) - 1)
        return GenerationResponse(
            message=ChatMessage(role="assistant", content=self.contents[index]),
            finish_reason="stop",
            usage=UsageStats(input_tokens=10, output_tokens=20, total_tokens=30),
            model_name="stub",
            backend=self.backend,
        )


class _CountingStubEngine(_StubEngine):
    def __init__(
        self,
        content: str | list[str],
        *,
        backend: str = "ollama",
        n_ctx: int = 8192,
    ) -> None:
        super().__init__(content, backend=backend, n_ctx=n_ctx)
        self.counted_texts: list[str] = []

    def count_tokens(self, text: str) -> int:
        self.counted_texts.append(text)
        return math.ceil(len(text) / 4)
