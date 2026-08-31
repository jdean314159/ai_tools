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
    _rule(
        "ssh_failed_auth",
        "auth",
        Severity.WARNING,
        r"\bsshd\b.*\b(Failed password|authentication failure)\b",
    ),
    _rule(
        "ssh_invalid_user", "auth", Severity.WARNING, r"\bsshd\b.*\b(Invalid user|user unknown)\b"
    ),
    _rule(
        "sudo_failure",
        "auth",
        Severity.WARNING,
        r"\bsudo\b.*\b(authentication failure|incorrect password attempts)\b",
    ),
    _rule("pam_failure", "auth", Severity.WARNING, r"pam_unix\([^)]*\): authentication failure"),
    _rule("oom_kill", "memory", Severity.CRITICAL, r"\b(Out of memory|oom-kill|Killed process)\b"),
    _rule(
        "disk_io_error",
        "disk",
        Severity.ERROR,
        r"\b(I/O error|Buffer I/O error|EXT4-fs error|ata\d+.*(?:error|softreset failed|reset failed|failed command))\b",
    ),
    _rule("segfault", "stability", Severity.ERROR, r"\b(segfault|general protection fault)\b"),
    _rule(
        "kernel_bug",
        "stability",
        Severity.CRITICAL,
        r"\bkernel\b.*\bOops\b|\bBUG:\b|\bCall Trace:\b",
    ),
    _rule(
        "service_failed",
        "service",
        Severity.ERROR,
        r"\bsystemd\b.*\b(Failed to start|entered failed state)\b",
    ),
)


@dataclass(frozen=True)
class BenignSuppressor:
    """Pattern that identifies known-benign log noise; matching clusters are suppressed."""

    name: str
    pattern: re.Pattern[str]


def _suppress(name: str, pattern: str) -> BenignSuppressor:
    return BenignSuppressor(name=name, pattern=re.compile(pattern, re.IGNORECASE))


# Clusters whose template/examples match any of these patterns are unconditionally
# suppressed before rule matching.  Each pattern is a known-benign OS/firmware
# event that small models consistently over-escalate.
BENIGN_SUPPRESSORS: tuple[BenignSuppressor, ...] = (
    _suppress(
        "acpi_ae_already_exists",
        r"ACPI.*AE_ALREADY_EXISTS",
    ),
    _suppress(
        "ata_drm_info",
        r"ata\d+.*supports DRM functions and may not be fully accessible",
    ),
    _suppress(
        "i915_fifo_underrun",
        r"i915.*CPU pipe [A-Z] FIFO underrun",
    ),
    _suppress(
        "atkbd_setkeycodes",
        r"atkbd.*Use .setkeycodes",
    ),
    _suppress(
        "overlayfs_xino_fallback",
        r"overlayfs.*does not support file handles.*falling back to xino=off",
    ),
    _suppress(
        "ntp_time_jump",
        r"(chronyd|ntpd|systemd-timesyncd).*forward time jump detected",
    ),
    _suppress(
        "gnome_keyring_noise",
        r"(gnome-keyring|login keyring).*",
    ),
    _suppress(
        "screensaver_unlock_noise",
        r"pam_unix\((?:cinnamon-screensaver|gnome-screensaver|xscreensaver|"
        r"light-locker|kscreenlocker)[^)]*\):",
    ),
    _suppress(
        "polkit_session_noise",
        r"(?:polkitd?|pkexec)\b.*(?:Operator of unix-session|"
        r"Registered Authentication Agent|Unregistered Authentication Agent)",
    ),
    _suppress(
        "gdm_session_noise",
        r"(?:gdm-(?:session|launch-environment|password)|gdm3)\][^:]*:.*"
        r"(?:pam_unix|session opened|session closed)",
    ),
    _suppress(
        "bluetooth_tx_timeout",
        r"Bluetooth:\s*hci\d+:\s*command\s+(?:0x[0-9a-fA-F]+|<HEX>)\s+tx timeout",
    ),
)
