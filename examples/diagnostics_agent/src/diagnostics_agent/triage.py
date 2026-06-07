from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
import json
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from diagnostics_agent.rules import BenignSuppressor, TriageRule


class Severity(IntEnum):
    UNKNOWN = 0
    DEBUG = 1
    INFO = 2
    NOTICE = 3
    WARNING = 4
    ERROR = 5
    CRITICAL = 6
    ALERT = 7
    EMERGENCY = 8


@dataclass(frozen=True)
class LogRecord:
    raw: str
    timestamp: datetime | None
    host: str | None
    process: str | None
    pid: int | None
    severity: Severity
    message: str
    parsed: bool
    container_name: str | None = None


@dataclass(frozen=True)
class EventCluster:
    template: str
    count: int
    severity: Severity
    first_seen: datetime | None
    last_seen: datetime | None
    processes: tuple[str, ...]
    examples: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    rule_name: str
    category: str
    severity: Severity
    count: int
    template: str
    first_seen: datetime | None
    last_seen: datetime | None
    examples: tuple[str, ...]


@dataclass(frozen=True)
class TriageSummary:
    time_range: tuple[datetime | None, datetime | None]
    total_lines: int
    parsed_lines: int
    unparsed_lines: int
    severity_counts: dict[Severity, int]
    findings: tuple[Finding, ...]
    top_clusters: tuple[EventCluster, ...]
    suppressed: tuple[tuple[Severity, int], ...]
    excluded_self_noise: int = 0

    def to_dict(self) -> dict:
        return {
            "time_range": [_datetime_to_json(item) for item in self.time_range],
            "total_lines": self.total_lines,
            "parsed_lines": self.parsed_lines,
            "unparsed_lines": self.unparsed_lines,
            "severity_counts": {
                severity.name: self.severity_counts[severity]
                for severity in Severity
                if self.severity_counts.get(severity, 0)
            },
            "findings": [_finding_to_dict(finding) for finding in self.findings],
            "top_clusters": [_cluster_to_dict(cluster) for cluster in self.top_clusters],
            "suppressed": [
                {"severity": severity.name, "count": count}
                for severity, count in self.suppressed
            ],
            "excluded_self_noise": self.excluded_self_noise,
        }


@dataclass(frozen=True)
class TriageConfig:
    rules: tuple["TriageRule", ...] | None = None
    suppressors: tuple["BenignSuppressor", ...] | None = None
    max_clusters: int = 25
    max_examples_per_group: int = 3
    min_cluster_severity: Severity = Severity.NOTICE
    assume_year: int | None = None
    exclude_self_noise: bool = True

    def resolved_rules(self) -> tuple["TriageRule", ...]:
        if self.rules is not None:
            return self.rules
        from diagnostics_agent.rules import DEFAULT_RULES

        return DEFAULT_RULES

    def resolved_suppressors(self) -> tuple["BenignSuppressor", ...]:
        if self.suppressors is not None:
            return self.suppressors
        from diagnostics_agent.rules import BENIGN_SUPPRESSORS

        return BENIGN_SUPPRESSORS


class LogTriage:
    def __init__(self, config: TriageConfig | None = None) -> None:
        self.config = config or TriageConfig()

    def parse_lines(self, lines: Iterable[str]) -> list[LogRecord]:
        return [_parse_line(line.rstrip("\n"), self.config.assume_year) for line in lines]

    def triage(self, source: Iterable[str] | str) -> TriageSummary:
        lines = source.splitlines() if isinstance(source, str) else source
        all_records = self.parse_lines(lines)
        records = all_records
        excluded_self_noise = 0
        if self.config.exclude_self_noise:
            records = [record for record in all_records if not _is_self_noise(record)]
            excluded_self_noise = len(all_records) - len(records)
        clusters = _build_clusters(records, self.config.max_examples_per_group)
        findings, remaining_clusters = _classify_findings(clusters, self.config.resolved_rules(), self.config.resolved_suppressors())

        top_candidates = [
            cluster
            for cluster in remaining_clusters
            if cluster.severity >= self.config.min_cluster_severity
        ]
        top_clusters = tuple(
            sorted(top_candidates, key=lambda cluster: (-cluster.count, cluster.template))[: self.config.max_clusters]
        )
        top_templates = {cluster.template for cluster in top_clusters}

        suppressed_counter: Counter[Severity] = Counter()
        for cluster in remaining_clusters:
            if cluster.template not in top_templates:
                suppressed_counter[cluster.severity] += cluster.count

        severity_counts = Counter(record.severity for record in all_records)
        parsed_lines = sum(1 for record in all_records if record.parsed)
        timestamps = [record.timestamp for record in all_records if record.timestamp is not None]

        return TriageSummary(
            time_range=(min(timestamps) if timestamps else None, max(timestamps) if timestamps else None),
            total_lines=len(all_records),
            parsed_lines=parsed_lines,
            unparsed_lines=len(all_records) - parsed_lines,
            severity_counts=dict(sorted(severity_counts.items(), key=lambda item: item[0].value)),
            findings=tuple(sorted(findings, key=_finding_sort_key)),
            top_clusters=top_clusters,
            suppressed=tuple(
                sorted(suppressed_counter.items(), key=lambda item: item[0].value)
            ),
            excluded_self_noise=excluded_self_noise,
        )


_ISO_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\S+)\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<header>[^:]+):\s*"
    r"(?P<message>.*)$"
)
_SYSLOG_RE = re.compile(
    r"^(?P<month>[A-Z][a-z]{2})\s+"
    r"(?P<day>\d{1,2})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<host>\S+)\s+"
    r"(?P<header>[^:]+):\s*"
    r"(?P<message>.*)$"
)
_HEADER_RE = re.compile(r"^(?P<process>[^\[]+?)(?:\[(?P<pid>\d+)\])?$")

_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}

_SEVERITY_KEYWORDS: tuple[tuple[Severity, re.Pattern[str]], ...] = (
    (Severity.EMERGENCY, re.compile(r"\bemerg(?:ency)?\b", re.IGNORECASE)),
    (Severity.ALERT, re.compile(r"\balert\b", re.IGNORECASE)),
    (Severity.CRITICAL, re.compile(r"\b(crit(?:ical)?|fatal)\b", re.IGNORECASE)),
    (Severity.ERROR, re.compile(r"\b(err|error)\b", re.IGNORECASE)),
    (Severity.WARNING, re.compile(r"\bwarn(?:ing)?\b", re.IGNORECASE)),
    (Severity.NOTICE, re.compile(r"\bnotice\b", re.IGNORECASE)),
    (Severity.INFO, re.compile(r"\binfo\b", re.IGNORECASE)),
    (Severity.DEBUG, re.compile(r"\bdebug\b", re.IGNORECASE)),
)

_SYSLOG_PRIORITY_RE = re.compile(r"^<(?P<priority>\d{1,3})>")

_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6_RE = re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){2,}[0-9A-Fa-f:]*\b")
_PORT_RE = re.compile(r":\d{2,5}\b")
_UUID_RE = re.compile(r"\b[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}\b")
_HEX_RE = re.compile(r"\b(?:0x[0-9A-Fa-f]+|[0-9A-Fa-f]{12,})\b")
_INT_RE = re.compile(r"\b\d+\b")
_SELF_SANDBOX_SIGNATURE = "diag-sbx-"


def _parse_line(raw: str, assume_year: int | None) -> LogRecord:
    journal_record = _parse_journal_json(raw)
    if journal_record is not None:
        return journal_record

    iso_match = _ISO_RE.match(raw)
    if iso_match:
        message = _strip_priority(iso_match.group("message"))
        timestamp = _parse_iso_timestamp(iso_match.group("timestamp"))
        process, pid = _parse_header(iso_match.group("header"))
        return LogRecord(
            raw=raw,
            timestamp=timestamp,
            host=iso_match.group("host"),
            process=process,
            pid=pid,
            severity=_detect_severity(iso_match.group("message"), parsed=True),
            message=message,
            parsed=True,
        )

    syslog_match = _SYSLOG_RE.match(raw)
    if syslog_match:
        message = _strip_priority(syslog_match.group("message"))
        process, pid = _parse_header(syslog_match.group("header"))
        return LogRecord(
            raw=raw,
            timestamp=_parse_syslog_timestamp(syslog_match, assume_year),
            host=syslog_match.group("host"),
            process=process,
            pid=pid,
            severity=_detect_severity(syslog_match.group("message"), parsed=True),
            message=message,
            parsed=True,
        )

    return LogRecord(
        raw=raw,
        timestamp=None,
        host=None,
        process=None,
        pid=None,
        severity=Severity.UNKNOWN,
        message=raw,
        parsed=False,
    )


def _parse_journal_json(raw: str) -> LogRecord | None:
    if not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "MESSAGE" not in data:
        return None

    message = _journal_value(data.get("MESSAGE")) or ""
    return LogRecord(
        raw=raw,
        timestamp=_parse_journal_timestamp(data),
        host=_journal_value(data.get("_HOSTNAME")) or _journal_value(data.get("HOSTNAME")),
        process=(
            _journal_value(data.get("SYSLOG_IDENTIFIER"))
            or _journal_value(data.get("_COMM"))
            or _journal_value(data.get("_EXE"))
        ),
        pid=_parse_int(_journal_value(data.get("_PID")) or _journal_value(data.get("SYSLOG_PID"))),
        severity=_severity_from_journal_priority(data.get("PRIORITY")),
        message=message,
        parsed=True,
        container_name=(
            _journal_value(data.get("CONTAINER_NAME"))
            or _journal_value(data.get("container_name"))
            or _journal_value(data.get("_CONTAINER_NAME"))
        ),
    )


def _parse_header(header: str) -> tuple[str | None, int | None]:
    match = _HEADER_RE.match(header.strip())
    if not match:
        return header.strip() or None, None
    process = match.group("process").strip() or None
    pid = int(match.group("pid")) if match.group("pid") else None
    return process, pid


def _parse_iso_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_syslog_timestamp(match: re.Match[str], assume_year: int | None) -> datetime | None:
    if assume_year is None:
        return None
    hour, minute, second = (int(part) for part in match.group("time").split(":"))
    return datetime(
        assume_year,
        _MONTHS[match.group("month")],
        int(match.group("day")),
        hour,
        minute,
        second,
    )


def _parse_journal_timestamp(data: dict) -> datetime | None:
    realtime = _journal_value(data.get("__REALTIME_TIMESTAMP"))
    if realtime is not None:
        micros = _parse_int(realtime)
        if micros is not None:
            return datetime.fromtimestamp(micros / 1_000_000)

    timestamp = _journal_value(data.get("__TIMESTAMP")) or _journal_value(data.get("_SOURCE_REALTIME_TIMESTAMP"))
    if timestamp is not None:
        try:
            return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _detect_severity(message: str, *, parsed: bool) -> Severity:
    priority_match = _SYSLOG_PRIORITY_RE.match(message)
    if priority_match:
        priority = int(priority_match.group("priority"))
        return _severity_from_syslog_priority(priority)

    for severity, pattern in _SEVERITY_KEYWORDS:
        if pattern.search(message):
            return severity
    return Severity.INFO if parsed else Severity.UNKNOWN


def _severity_from_journal_priority(priority: object) -> Severity:
    parsed = _parse_int(_journal_value(priority))
    if parsed is None:
        return Severity.UNKNOWN
    return _severity_from_syslog_priority(parsed)


def _severity_from_syslog_priority(priority: int) -> Severity:
    severity_code = priority % 8
    return {
        0: Severity.EMERGENCY,
        1: Severity.ALERT,
        2: Severity.CRITICAL,
        3: Severity.ERROR,
        4: Severity.WARNING,
        5: Severity.NOTICE,
        6: Severity.INFO,
        7: Severity.DEBUG,
    }[severity_code]


def _strip_priority(message: str) -> str:
    return _SYSLOG_PRIORITY_RE.sub("", message, count=1)


def _journal_value(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        first = value[0]
        return first if isinstance(first, str) else None
    return None


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _build_clusters(records: list[LogRecord], max_examples: int) -> list[EventCluster]:
    grouped: dict[str, list[tuple[int, LogRecord]]] = defaultdict(list)
    for index, record in enumerate(records):
        grouped[_template(record.message)].append((index, record))

    clusters = []
    for template, indexed_records in grouped.items():
        cluster_records = [record for _index, record in indexed_records]
        timestamps = [record.timestamp for record in cluster_records if record.timestamp is not None]
        processes = sorted({record.process for record in cluster_records if record.process is not None})
        clusters.append(
            EventCluster(
                template=template,
                count=len(cluster_records),
                severity=max(record.severity for record in cluster_records),
                first_seen=min(timestamps) if timestamps else None,
                last_seen=max(timestamps) if timestamps else None,
                processes=tuple(processes),
                examples=tuple(record.raw for _index, record in indexed_records[:max_examples]),
            )
        )
    return clusters


def _is_self_noise(record: LogRecord) -> bool:
    return bool(record.container_name and record.container_name.startswith(_SELF_SANDBOX_SIGNATURE))


def _classify_findings(
    clusters: list[EventCluster],
    rules: tuple["TriageRule", ...],
    suppressors: tuple["BenignSuppressor", ...] = (),
) -> tuple[list[Finding], list[EventCluster]]:
    findings: list[Finding] = []
    remaining: list[EventCluster] = []
    for cluster in clusters:
        if _is_benign(cluster, suppressors):
            continue
        rule = _matching_rule(cluster, rules)
        if rule is None:
            remaining.append(cluster)
            continue
        findings.append(
            Finding(
                rule_name=rule.name,
                category=rule.category,
                severity=max(rule.severity, cluster.severity),
                count=cluster.count,
                template=cluster.template,
                first_seen=cluster.first_seen,
                last_seen=cluster.last_seen,
                examples=cluster.examples,
            )
        )
    return findings, remaining


def _is_benign(cluster: EventCluster, suppressors: tuple["BenignSuppressor", ...]) -> bool:
    if not suppressors:
        return False
    haystacks = (cluster.template, *cluster.examples)
    return any(
        s.pattern.search(text) for s in suppressors for text in haystacks
    )


def _matching_rule(cluster: EventCluster, rules: tuple["TriageRule", ...]) -> "TriageRule | None":
    haystacks = (cluster.template, *cluster.examples)
    for rule in rules:
        if any(rule.pattern.search(text) for text in haystacks):
            return rule
    return None


def _template(message: str) -> str:
    masked = _IPV4_RE.sub("<IP>", message)
    masked = _IPV6_RE.sub("<IP>", masked)
    masked = _PORT_RE.sub(":<PORT>", masked)
    masked = _UUID_RE.sub("<UUID>", masked)
    masked = _HEX_RE.sub("<HEX>", masked)
    masked = _INT_RE.sub("<NUM>", masked)
    return re.sub(r"\s+", " ", masked).strip()


def _finding_sort_key(finding: Finding) -> tuple[int, int, float, str]:
    return (
        -finding.severity.value,
        -finding.count,
        -_timestamp_sort_value(finding.last_seen),
        finding.template,
    )


def _timestamp_sort_value(value: datetime | None) -> float:
    if value is None:
        return float("-inf")
    return value.timestamp()


def _datetime_to_json(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _cluster_to_dict(cluster: EventCluster) -> dict:
    return {
        "template": cluster.template,
        "count": cluster.count,
        "severity": cluster.severity.name,
        "first_seen": _datetime_to_json(cluster.first_seen),
        "last_seen": _datetime_to_json(cluster.last_seen),
        "processes": list(cluster.processes),
        "examples": list(cluster.examples),
    }


def _finding_to_dict(finding: Finding) -> dict:
    return {
        "rule_name": finding.rule_name,
        "category": finding.category,
        "severity": finding.severity.name,
        "count": finding.count,
        "template": finding.template,
        "first_seen": _datetime_to_json(finding.first_seen),
        "last_seen": _datetime_to_json(finding.last_seen),
        "examples": list(finding.examples),
    }
