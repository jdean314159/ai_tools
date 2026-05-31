from __future__ import annotations

from dataclasses import dataclass
import re

from diagnostics_agent.triage import Severity


@dataclass(frozen=True)
class TriageRule:
    name: str
    category: str
    severity: Severity
    pattern: re.Pattern[str]


def _rule(name: str, category: str, severity: Severity, pattern: str) -> TriageRule:
    return TriageRule(
        name=name,
        category=category,
        severity=severity,
        pattern=re.compile(pattern, re.IGNORECASE),
    )


DEFAULT_RULES: tuple[TriageRule, ...] = (
    _rule("ssh_failed_auth", "auth", Severity.WARNING, r"\bsshd\b.*\b(Failed password|authentication failure)\b"),
    _rule("ssh_invalid_user", "auth", Severity.WARNING, r"\bsshd\b.*\b(Invalid user|user unknown)\b"),
    _rule("sudo_failure", "auth", Severity.WARNING, r"\bsudo\b.*\b(authentication failure|incorrect password attempts)\b"),
    _rule("pam_failure", "auth", Severity.WARNING, r"pam_unix\([^)]*\): authentication failure"),
    _rule("oom_kill", "memory", Severity.CRITICAL, r"\b(Out of memory|oom-kill|Killed process)\b"),
    _rule(
        "disk_io_error",
        "disk",
        Severity.ERROR,
        r"\b(I/O error|Buffer I/O error|EXT4-fs error|ata\d+.*(?:error|softreset failed|reset failed|failed command))\b",
    ),
    _rule("segfault", "stability", Severity.ERROR, r"\b(segfault|general protection fault)\b"),
    _rule("kernel_bug", "stability", Severity.CRITICAL, r"\bkernel\b.*\bOops\b|\bBUG:\b|\bCall Trace:\b"),
    _rule("service_failed", "service", Severity.ERROR, r"\bsystemd\b.*\b(Failed to start|entered failed state)\b"),
)
