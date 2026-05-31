# Phase 1 Build Spec — Deterministic Log Triage

**For:** an autonomous coding agent (Codex) to produce the first draft.
**Parent:** `docs/projects/diagnostics_agent/CAMPAIGN.md`, Phase 1.
**Status:** committed.
**Builds on:** Phase 0 (`diagnostics_agent` package). **Does not import the sandbox.**

---

## 1. Objective

Reduce raw log text into a structured, risk-ordered summary **before any model
sees it**. Pure, deterministic text processing: parse lines into records, collapse
repetition into templated clusters, classify severity, flag known-bad patterns,
and emit a JSON-serializable summary. No LLM, no container, no network, no file
I/O inside the module.

This phase carries most of the real engineering. Its blind spots become the whole
system's blind spots, so the governing discipline is: **demote, don't drop.**
Everything is accounted for in the summary even when it isn't shown in detail.

## 2. Relationship to Phase 0

Phase 1 operates on the **string** that `SandboxResult.stdout` happens to contain,
but it **must not import `sandbox.py`** or depend on a container runtime. The
triage takes `Iterable[str]` (lines) or `str` and returns a summary. Composition
of sandbox → triage is a later orchestration concern. Keep them decoupled so
triage is testable with plain fixtures.

## 3. Deliverables (added to the existing package)

```
src/diagnostics_agent/
  triage.py     # LogTriage, TriageConfig, and the data model below
  rules.py      # TriageRule + DEFAULT_RULES
tests/
  test_triage.py
  fixtures/
    syslog_sample.log        # legacy syslog lines
    journal_iso_sample.log   # journalctl -o short-iso lines
    mixed_noise.log          # high-volume repetition + a few real findings
```

Update `__init__.py` to export the public names. Python 3.11+, stdlib only
(`re`, `datetime`, `dataclasses`, `enum`, `collections`). No new dependencies.

## 4. Data model (implement this contract)

```python
class Severity(IntEnum):          # higher value = more urgent (intuitive for max())
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
    timestamp: datetime | None     # None when unparseable; raw text never lost
    host: str | None
    process: str | None
    pid: int | None
    severity: Severity
    message: str                   # body after "process[pid]:"; == raw if unparsed
    parsed: bool

@dataclass(frozen=True)
class EventCluster:
    template: str                  # message with volatile tokens masked
    count: int
    severity: Severity             # max severity observed in the cluster
    first_seen: datetime | None
    last_seen: datetime | None
    processes: tuple[str, ...]     # distinct emitting processes, sorted
    examples: tuple[str, ...]      # up to config.max_examples_per_group raw lines

@dataclass(frozen=True)
class Finding:                     # a cluster that matched a known-bad rule
    rule_name: str
    category: str
    severity: Severity             # max(rule severity, observed cluster severity)
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
    severity_counts: dict[Severity, int]      # over all records
    findings: tuple[Finding, ...]              # risk-ordered (see §6)
    top_clusters: tuple[EventCluster, ...]     # non-finding clusters, freq-ordered
    suppressed: tuple[tuple[Severity, int], ...]  # (severity, count) demoted below the cutoff
    def to_dict(self) -> dict: ...             # JSON-safe: Severity->name, datetime->isoformat()|None
```

```python
@dataclass(frozen=True)
class TriageConfig:
    rules: tuple[TriageRule, ...] = DEFAULT_RULES
    max_clusters: int = 25                 # cap on top_clusters
    max_examples_per_group: int = 3
    min_cluster_severity: Severity = Severity.NOTICE  # below this: suppressed-summarized
    assume_year: int | None = None         # for legacy syslog lacking a year; see §5

class LogTriage:
    def __init__(self, config: TriageConfig | None = None) -> None: ...
    def parse_lines(self, lines: Iterable[str]) -> list[LogRecord]: ...   # public, testable
    def triage(self, source: Iterable[str] | str) -> TriageSummary: ...
```

## 5. Parsing semantics

Two first-class formats; best-effort, never destructive:

1. **ISO / journalctl `-o short-iso`** — `2026-05-29T14:03:11-07:00 host proc[pid]: msg`.
   This is the recommended collection format; parse the timestamp fully.
2. **Legacy syslog** — `May 29 14:03:11 host proc[pid]: msg`. No year in the format.
   Use `config.assume_year` if set; if `None`, leave `timestamp=None` (do **not**
   call `datetime.now()` — the module must stay pure and deterministic) but keep
   the raw line. Cluster first/last-seen then fall back to input order.

Any line that matches neither shape becomes a `LogRecord(parsed=False, raw=line,
message=line, severity=UNKNOWN, ...)`. **Unparsed lines are kept and counted**, never
discarded — an unparseable line may be the important one.

**Severity** comes from a syslog priority when present (map 0→EMERGENCY … 7→DEBUG),
otherwise from case-insensitive keyword heuristics on the message
(`emerg/alert/crit/fatal`, `err/error`, `warn`, `notice`, `info`, `debug`),
defaulting to `INFO` for a parsed line with no signal and `UNKNOWN` for unparsed.

## 6. Clustering, flagging, ordering

- **Template masking** (applied to the *message* body, after the timestamp is
  removed): replace IPv4/IPv6 addresses → `<IP>`, `:port` → `<PORT>`, UUIDs →
  `<UUID>`, `0x…`/long hex → `<HEX>`, standalone integers (incl. bracketed PIDs)
  → `<NUM>`. Group records by the masked template. So "Failed password … from
  1.2.3.4" and "… from 5.6.7.8" collapse to one cluster with `count=2`.
- **Findings vs clusters:** build clusters first; test each cluster's template (or
  example messages) against `config.rules`. A match becomes a `Finding` (severity =
  max of rule severity and observed); matched clusters are **excluded** from
  `top_clusters` so nothing is double-reported.
- **`findings` ordering (risk):** severity desc, then count desc, then last_seen
  desc, with template string as the final stable tiebreak (determinism).
- **`top_clusters`:** non-finding clusters with `severity >= min_cluster_severity`,
  ordered by count desc then template; truncated to `max_clusters`.
- **`suppressed`:** non-finding clusters below `min_cluster_severity` are not listed
  individually; their record counts are aggregated per severity into `suppressed`.
  This is the demote-don't-drop accounting.
- **Invariant:** `total_lines == parsed_lines + unparsed_lines`, and the sum of all
  counts across findings + top_clusters + suppressed equals `total_lines`. Nothing
  is silently lost.

## 7. Default ruleset (`rules.py`) — explicit so it can be reviewed and tuned

These are log-line patterns only. (Listening-port / open-socket checks are
*system-state* checks against a different input source — not Phase 1; deferred.)

| name | category | severity | matches (intent) |
|---|---|---|---|
| ssh_failed_auth | auth | WARNING | sshd "Failed password", "authentication failure" |
| ssh_invalid_user | auth | WARNING | sshd "Invalid user", "user unknown" |
| sudo_failure | auth | WARNING | sudo "authentication failure", "incorrect password attempts" |
| pam_failure | auth | WARNING | "pam_unix(...): authentication failure" |
| oom_kill | memory | CRITICAL | "Out of memory", "oom-kill", "Killed process" |
| disk_io_error | disk | ERROR | "I/O error", "Buffer I/O error", "EXT4-fs error", "ata… error" |
| segfault | stability | ERROR | "segfault", "general protection fault" |
| kernel_bug | stability | CRITICAL | "kernel: … Oops", "BUG:", "Call Trace:" |
| service_failed | service | ERROR | systemd "Failed to start", "entered failed state" |

```python
@dataclass(frozen=True)
class TriageRule:
    name: str
    category: str
    severity: Severity
    pattern: re.Pattern[str]       # compiled, case-insensitive; matched on message
```

`DEFAULT_RULES: tuple[TriageRule, ...]`. The README must list these patterns and
state plainly what the triage filters/demotes — this is the documented blind-spot
surface from the CAMPAIGN.

## 8. Tests (`test_triage.py`, fixtures only — no LLM, no podman)

- **Parse ISO line:** fields extracted correctly (timestamp tz-aware, host, process,
  pid, severity, message).
- **Parse legacy syslog:** with `assume_year` set → dated; with `None` →
  `timestamp is None`, raw preserved, still counted.
- **Unparsed line:** `parsed is False`, raw kept, `severity == UNKNOWN`, counted.
- **Templating/dedup:** N "Failed password … from <varying IP>" lines → one cluster,
  `count == N`, template contains `<IP>`.
- **Severity heuristics:** keyword lines classify correctly without a priority.
- **Rule fires:** an OOM fixture line produces a `Finding(category="memory",
  severity=CRITICAL)`; findings precede top_clusters.
- **Suppression accounting:** high-volume low-severity lines land in `suppressed`,
  not `top_clusters`; counts still reconcile.
- **Conservation invariant:** `total_lines == parsed + unparsed` and the count sum
  across findings + top_clusters + suppressed == `total_lines`.
- **Determinism:** triaging the same fixture twice yields equal `TriageSummary`
  (stable ordering, no `now()` dependence).
- **Serialization:** `to_dict()` is JSON-serializable (`json.dumps` succeeds;
  Severity rendered as name, datetimes as ISO strings or null).

## 9. Non-goals (do NOT build in Phase 1)

No LLM or `llm_engines`. No import of `sandbox.py`; no container, no subprocess, no
network. No file reading inside the module (callers/tests pass text in). No
journalctl-JSON parser (leave the parser structured so a third format can be added,
but don't build it now). No system-state checks (ports, processes, disk usage) —
those are a different input source for a later phase. No new dependencies.

## 10. Acceptance criteria

1. All tests pass with no container runtime and no network.
2. Parsing is best-effort and lossless: every input line is represented; the
   conservation invariant in §6/§8 holds.
3. `triage()` is deterministic — no `datetime.now()`, no unordered set iteration
   leaking into output; repeated runs are byte-identical after `to_dict()` + `json.dumps`.
4. `DEFAULT_RULES` matches §7 and is documented in the README.
5. Lint/type checks clean against the repo config.
