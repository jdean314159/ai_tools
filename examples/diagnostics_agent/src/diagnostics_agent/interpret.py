from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, field_validator

from diagnostics_agent.engine_guard import require_local_engine
from diagnostics_agent.errors import InterpretationParseError
from diagnostics_agent.system_facts import SystemFacts
from diagnostics_agent.triage import TriageSummary
from llm_engines import StructuredOutputError, StructuredOutputHandler
from llm_engines.contracts import ChatMessage, GenerationRequest


RiskLevel = Literal["info", "low", "medium", "high", "critical"]
OverallRisk = Literal["none", "low", "medium", "high", "critical"]
_RISK_RANK = {"info": 0, "none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
_OPERATIONAL_FLOOR_CATEGORIES = {"disk", "memory", "stability"}


class ConcernAssessment(BaseModel):
    finding_ref: str
    rationale: str
    severity: RiskLevel

    @field_validator("severity", mode="before")
    @classmethod
    def _normalize_severity(cls, value: object) -> object:
        return _normalize_risk_label(value)


class Interpretation(BaseModel):
    reasoning: str
    summary: str
    security_risk: OverallRisk
    operational_risk: OverallRisk
    prioritized_concerns: list[ConcernAssessment]
    recommended_checks: list[str]

    @field_validator("security_risk", "operational_risk", mode="before")
    @classmethod
    def _normalize_risk_fields(cls, value: object) -> object:
        normalized = _normalize_risk_label(value)
        return "none" if normalized == "info" else normalized


class LogInterpreter:
    def __init__(
        self,
        engine,
        *,
        allow_remote: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> None:
        self.engine = engine
        self.temperature = temperature
        self.max_tokens = max_tokens
        require_local_engine(engine, allow_remote=allow_remote)

    def interpret(
        self,
        summary: TriageSummary,
        *,
        system_facts: SystemFacts | None = None,
    ) -> Interpretation:
        request = self._build_request(summary, system_facts=system_facts)
        last_exc: Exception | None = None
        for attempt in range(2):
            response = self.engine.generate(request)
            try:
                interpretation = StructuredOutputHandler.parse(
                    response.text,
                    Interpretation,
                    allow_repair=True,
                )
                interpretation = _apply_operational_floor(interpretation, summary)
                return _apply_risk_coherence(interpretation)
            except StructuredOutputError as exc:
                last_exc = exc
                if attempt == 0:
                    details = StructuredOutputHandler.parse_with_details(
                        response.text,
                        Interpretation,
                        allow_repair=True,
                    )
                    request = self._append_correction(
                        request,
                        response.text,
                        exc,
                        extracted_json=details.extracted_json,
                        parse_error=details.error,
                    )

        raise InterpretationParseError(
            "engine response was not valid Interpretation JSON after retry"
        ) from last_exc

    def _build_request(
        self,
        summary: TriageSummary,
        *,
        system_facts: SystemFacts | None = None,
    ) -> GenerationRequest:
        return GenerationRequest(
            messages=[
                ChatMessage(role="system", content=_SYSTEM_PROMPT),
                ChatMessage(role="user", content=_user_prompt(summary, system_facts=system_facts)),
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            json_schema=Interpretation.model_json_schema(),
        )

    def _append_correction(
        self,
        original: GenerationRequest,
        bad_output: str,
        exc: Exception,
        *,
        extracted_json: str | None = None,
        parse_error: str | None = None,
    ) -> GenerationRequest:
        details = f"Validation error: {parse_error or exc}. "
        if extracted_json:
            details += f"Extracted JSON: {extracted_json}. "
        correction = (
            "Your response did not validate against the required schema. "
            f"{details}"
            "Return the complete object including security_risk, operational_risk, "
            "prioritized_concerns "
            "(a list of concern objects with finding_ref, severity, and rationale) "
            "and recommended_checks (a list of read-only check strings). "
            "Use only these lowercase risk values: info, low, medium, high, critical. "
            "Return only the corrected JSON object."
        )
        return GenerationRequest(
            messages=[
                *original.messages,
                ChatMessage(role="assistant", content=bad_output),
                ChatMessage(role="user", content=correction),
            ],
            temperature=0.0,
            max_tokens=original.max_tokens,
            stop=list(original.stop),
            json_schema=original.json_schema,
            metadata=dict(original.metadata),
            optimizations=original.optimizations,
            session_id=original.session_id,
        )


_SYSTEM_PROMPT = (
    "You are a read-only local diagnostics interpreter for a security-conscious operator. "
    "Interpret only the triage summary provided. Do not invent events, files, users, hosts, "
    "network addresses, or causes that are not present in the summary. Correlate repeated "
    "events and findings, prioritize by actual operational or security risk, and recommend "
    "only read-only follow-up checks. When 'Verified host facts' are provided, treat them "
    "as authoritative: never contradict them and never assert an OS version, kernel version, "
    "or hostname that is not listed there."
)

_FIELD_GUIDE = (
    "Return the structured interpretation using these field meanings:\n"
    "- reasoning: concise prose reasoning from the supplied triage summary before final labels.\n"
    "- summary: one-line plain-language headline.\n"
    "- security_risk: one of none, low, medium, high, critical; estimate attacker/security exposure only.\n"
    "- operational_risk: one of none, low, medium, high, critical; estimate reliability, data integrity, "
    "availability, and maintenance urgency.\n"
    "- prioritized_concerns: ordered concerns mapped to a finding rule_name or cluster template. "
    "Concern severity means attention/action severity across both security and operational risk.\n"
    "- recommended_checks: read-only next checks only; advisory in this phase.\n"
    "Calibration guidance:\n"
    "- For auth findings, weight risk by service and count, not pattern name alone. "
    "PAM failures from sshd, sudo, or login are more security-relevant; failures "
    "from cinnamon-screensaver, polkit, or gdm are often local unlock/session noise. "
    "A single auth failure is usually low risk unless context indicates otherwise.\n"
    "- Do not equate 'not a security threat' with 'low severity'. Repeated disk/ATA errors, "
    "filesystem corruption, OOM kills, thermal failures, and persistent kernel hardware errors "
    "warrant medium or higher operational_risk and concern severity even when security_risk is none.\n"
)


def _user_prompt(
    summary: TriageSummary,
    *,
    system_facts: SystemFacts | None = None,
) -> str:
    facts = f"{system_facts.as_prompt_block()}\n\n" if system_facts is not None else ""
    summary_json = json.dumps(_summary_for_prompt(summary), sort_keys=True, separators=(",", ":"))
    return f"{facts}{_FIELD_GUIDE}\nTriage summary JSON:\n{summary_json}"


def _summary_for_prompt(summary: TriageSummary) -> dict:
    prompt_summary = summary.to_dict()
    for group_name in ("findings", "top_clusters"):
        for item in prompt_summary.get(group_name, []):
            examples = item.get("examples", [])
            item["examples"] = [_truncate_prompt_text(example, 240) for example in examples[:1]]
    return prompt_summary


def _truncate_prompt_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _normalize_risk_label(value: object) -> object:
    if not isinstance(value, str):
        return value
    cleaned = value.strip().lower()
    # Local models often copy Phase 1/syslog severity names into the Phase 2
    # risk fields. This is a policy mapping from log urgency to user-facing
    # diagnostic risk, not a syslog conversion: INFO/NOTICE become low risk,
    # WARNING becomes medium, ERROR becomes high, and CRITICAL+ becomes critical.
    return {
        "unknown": "info",
        "debug": "info",
        "info": "low",
        "notice": "low",
        "warning": "medium",
        "warn": "medium",
        "error": "high",
        "err": "high",
        "critical": "critical",
        "crit": "critical",
        "fatal": "critical",
        "alert": "critical",
        "emergency": "critical",
    }.get(cleaned, cleaned)


def _apply_operational_floor(
    interpretation: Interpretation,
    summary: TriageSummary,
) -> Interpretation:
    floors_by_ref: dict[str, RiskLevel] = {}
    floors_by_rule: dict[str, tuple[RiskLevel, str, str]] = {}
    for finding in summary.findings:
        floor = _operational_floor_for_finding(finding.category, finding.severity.name)
        if floor is None:
            continue
        floors_by_ref[finding.rule_name] = floor
        floors_by_ref[finding.template] = floor
        floors_by_rule[finding.rule_name] = (floor, finding.category, finding.severity.name)
    if not floors_by_ref:
        return interpretation

    operational_floor = max(floors_by_ref.values(), key=_risk_rank)
    concerns = []
    referenced_floor_rules = set()
    for concern in interpretation.prioritized_concerns:
        concern_floor = floors_by_ref.get(concern.finding_ref)
        if concern_floor is not None:
            referenced_floor_rules.update(
                rule_name
                for rule_name in _matching_floor_rules(concern.finding_ref, summary)
                if rule_name in floors_by_rule
            )
        if concern_floor is not None and _risk_rank(concern.severity) < _risk_rank(concern_floor):
            concerns.append(concern.model_copy(update={"severity": concern_floor}))
        else:
            concerns.append(concern)

    for rule_name, (floor, category, severity_name) in floors_by_rule.items():
        if rule_name in referenced_floor_rules:
            continue
        concerns.append(
            ConcernAssessment(
                finding_ref=rule_name,
                rationale=(
                    f"Deterministic triage classified this as a {category} finding "
                    f"at {severity_name} severity; operational risk is floored to {floor}."
                ),
                severity=floor,
            )
        )

    if (
        _risk_rank(interpretation.operational_risk) >= _risk_rank(operational_floor)
        and concerns == interpretation.prioritized_concerns
    ):
        return interpretation
    return interpretation.model_copy(
        update={
            "operational_risk": _max_risk(interpretation.operational_risk, operational_floor),
            "prioritized_concerns": concerns,
        }
    )


def _apply_risk_coherence(interpretation: Interpretation) -> Interpretation:
    if not interpretation.prioritized_concerns:
        return interpretation

    strongest_concern = max(
        (concern.severity for concern in interpretation.prioritized_concerns),
        key=_risk_rank,
    )
    target_risk = _axis_risk_for_concern_severity(strongest_concern)
    strongest_axis_rank = max(
        _risk_rank(interpretation.security_risk),
        _risk_rank(interpretation.operational_risk),
    )
    if strongest_axis_rank >= _risk_rank(target_risk):
        return interpretation

    if _risk_rank(interpretation.security_risk) > _risk_rank(interpretation.operational_risk):
        return interpretation.model_copy(update={"security_risk": target_risk})
    return interpretation.model_copy(update={"operational_risk": target_risk})


def _operational_floor_for_finding(category: str, severity_name: str) -> RiskLevel | None:
    if category not in _OPERATIONAL_FLOOR_CATEGORIES:
        return None
    if severity_name in {"CRITICAL", "ALERT", "EMERGENCY"}:
        return "high"
    return "medium"


def _matching_floor_rules(ref: str, summary: TriageSummary) -> tuple[str, ...]:
    return tuple(
        finding.rule_name
        for finding in summary.findings
        if ref in {finding.rule_name, finding.template}
    )


def _max_risk(current: OverallRisk, floor: RiskLevel) -> OverallRisk:
    return floor if _risk_rank(current) < _risk_rank(floor) else current


def _axis_risk_for_concern_severity(severity: RiskLevel) -> OverallRisk:
    return "low" if severity == "info" else severity


def _risk_rank(value: str) -> int:
    return _RISK_RANK[value]
