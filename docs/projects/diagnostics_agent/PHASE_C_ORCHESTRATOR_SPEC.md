# §C Build Spec — Diagnostics Orchestrator (end-to-end, read-only)

**For:** an autonomous coding agent (Codex).
**Parent:** `docs/projects/diagnostics_agent/CAMPAIGN.md`; the follow-on named in
the Phase 2 spec §C.
**Status:** committed (completes the read-only Phase 0–2 arc).
**Composes:** Phase 0 sandbox, Phase 1 triage, Phase 2 interpreter.

This is the first end-to-end run against real host logs and the first place the
Phase 0 §7 permission wrinkle goes live. Read it before writing code.

---

## 1. Objective

Chain the three built components into one read-only diagnostic run:
**collect → (sandbox) read → triage → interpret → audit.** No LLM-generated
commands (that is Phase 3), no writes, no remediation, no cloud path.

## 2. The collection model — decided: host-side collection, sandbox reads staged data

There are two ways to get logs to the triage stage. The spec mandates **Model B**:

- **Model A (rejected):** mount `/var/log:ro` into the sandbox and read logs there.
  This hits the §7 wrinkle head-on (root-owned `0640` logs unreadable by the
  sandbox user) and makes `journalctl` inside a container painful (needs the host
  journal dir + matching machine-id).
- **Model B (mandated):** a **host-side collector** runs a fixed, operator-configured,
  read-only command (`journalctl -o short-iso ...`, or reads specific files),
  writes the output to an ephemeral **staging dir**, and the **sandbox reads only
  that staged file** read-only. Collection runs with the host process's privilege;
  the sandbox/interpretation path never runs privileged.

Why Model B: collection is deterministic, fixed, and never LLM-generated in this
arc, so it does not need sandboxing. The sandbox's job is to be the locked-down
execution context for the *read* step — which in Phase 3 becomes LLM-generated
queries against the same staged data. Wiring the sandbox read now (against a fixed
command) proves the staging→mount→read path so Phase 3 is a small delta, not a
simultaneous debug of generated queries *and* the read path.

## 3. The §7 permission resolution (resolve at integration, document the outcome)

Two distinct privilege boundaries:

1. **Collection privilege (host):** reading `auth.log`/`kern.log` may need elevated
   rights. This is the operator's responsibility — run the tool with sufficient
   privilege for the logs requested. Document that privileged logs require elevated
   collection; the default collection command should target typically-readable
   sources and note the limitation.
2. **Sandbox read of staged files:** under rootless podman the staged file is owned
   by the host user, so the container's effective user must be able to read it. The
   Phase 0 config ran as `--user 65534` (nobody), which generally **cannot** read a
   host-user-owned file. Resolve this at integration — the recommended approach is
   `--userns=keep-id` so the container user maps to the host user that owns the
   staging dir; the alternative is world-readable staging in a world-traversable
   dir (weaker, exposes sensitive log content to other local users). Verify which
   works on the target host and record it in the README. This is the live form of
   the §7 wrinkle.

## 4. Deliverables (added to the existing package)

```
src/diagnostics_agent/
  collect.py        # Collector protocol, CommandCollector, CollectedLogs
  orchestrate.py    # DiagnosticsOrchestrator, DiagnosticResult
tests/
  test_orchestrate.py
```
Update `__init__.py` exports. No new runtime dependencies (stdlib + the three
existing components + `llm_engines`).

## 5. Public API

```python
@dataclass(frozen=True)
class CollectedLogs:
    staging_path: Path          # file the sandbox will read
    command: list[str]          # host collection command run (audit)
    source_description: str     # human label, e.g. "journalctl -p warning --since -24h"
    byte_count: int

class Collector(Protocol):
    def collect(self, staging_dir: Path) -> CollectedLogs: ...

class CommandCollector:
    """Runs a FIXED, operator-configured, read-only command on the HOST and stages
    its stdout. The command is never LLM-generated."""
    def __init__(self, command: list[str], *, source_description: str,
                 timeout_s: float = 30.0) -> None: ...
    def collect(self, staging_dir: Path) -> CollectedLogs: ...

@dataclass(frozen=True)
class DiagnosticResult:
    collected: CollectedLogs
    sandbox_result: SandboxResult | None       # None if sandbox read disabled
    summary: TriageSummary
    interpretation: Interpretation | None       # None if interpretation failed
    interpretation_error: str | None
    audit: dict                                 # JSON-serializable full record
    def to_dict(self) -> dict: ...

class DiagnosticsOrchestrator:
    def __init__(self, *, collector: Collector, triage: LogTriage,
                 interpreter: LogInterpreter,
                 sandbox: ReadOnlySandbox | None = None,
                 sandbox_mount: str = "/staging",
                 read_command: list[str] | None = None) -> None: ...
    def run(self) -> DiagnosticResult: ...
```
- If `sandbox is None`, the read step is skipped and triage runs directly on the
  staged file (host-side read) — a fallback for hosts without a container runtime.
  Default usage passes a real sandbox.
- `read_command` defaults to `["cat", f"{sandbox_mount}/<staged filename>"]`. In
  Phase 3 this becomes generated queries; keep it a single configurable seam.

## 6. `run()` flow

1. Create an ephemeral staging dir (`tempfile.mkdtemp`), mode `0700`.
2. `collected = collector.collect(staging_dir)` — host writes the staged file.
3. **Read:** if `sandbox` is set, mount `staging_dir:ro` at `sandbox_mount`, run
   `read_command`, take `SandboxResult.stdout` as the log text; else read the
   staged file directly. Capture the `SandboxResult` for the audit.
4. `summary = triage.triage(text)`.
5. **Interpret (partial-failure tolerant):** `try interpreter.interpret(summary)`;
   on `InterpreterError`, capture the message into `interpretation_error`, leave
   `interpretation=None`. A failed interpretation must NOT discard the triage — a
   partial result (summary without interpretation) is more useful than an exception
   for a diagnostics tool. `RemoteEngineRefused` should still surface clearly.
6. Assemble the `audit` dict: collection command + source_description, sandbox argv
   and result metadata (exit_code, duration, truncated), `summary.to_dict()`,
   `interpretation.to_dict()` or the error, run timestamps, and whether the
   interpreter retry fired (if surfaced).
7. **Cleanup** the staging dir in a `finally` (it holds potentially sensitive log
   content — remove it even on error).
8. Return `DiagnosticResult`.

## 7. Local-only / sensitive data

The interpreter already enforces local-only; the orchestrator must add no cloud
path. The `audit` dict and staged files may contain auth data, IPs, usernames —
keep them local. If an `audit_path` is later added for persistence, it writes
locally only. Never transmit the audit or staged content off-host.

## 8. Tests (`test_orchestrate.py`)

### Unit (no podman, no model)
- **Full chain, sandbox disabled:** a fake collector that writes a fixture log into
  the staging dir, `sandbox=None`, a stub interpreter engine returning valid
  `Interpretation` JSON → assert `DiagnosticResult` has the summary, interpretation,
  and a populated, JSON-serializable `audit`.
- **Partial failure:** stub engine that raises `InterpretationParseError` (post-
  retry) → `interpretation is None`, `interpretation_error` set, `summary` still
  present, `audit` still complete and serializable.
- **Remote refusal propagates:** a remote-backend engine without `allow_remote`
  raises at interpreter construction (guard the orchestrator wires it correctly).
- **Staging cleanup:** the staging dir is removed after a normal run and after a
  raised error (assert the temp dir no longer exists).

### Integration (`skipif` no podman; separately `skipif` no reachable model)
- **Sandbox read path:** real `ReadOnlySandbox` reading a fixture staged file
  through the mount → `SandboxResult.stdout` equals the staged content; flows to
  triage. (Stub the engine so this needs only podman.)
- **End-to-end:** real sandbox + real local model → a populated `Interpretation`
  with all five fields. This is the seam that exercises the §3 permission
  resolution; if it fails on file readability, that is the wrinkle to resolve and
  document, not a code bug to paper over.

## 9. Non-goals

No LLM-generated collection or read commands (Phase 3). No writes, no remediation.
No scheduling, no multi-run history or correlation. No `journalctl`-inside-container
(collection is host-side). No cloud engines. No `llm_inspector` wiring yet (the
`audit` dict is the precursor; Phase 5 routes it).

## 10. Acceptance criteria

1. Unit tests pass with no container runtime and no model (fake collector +
   `sandbox=None` + stub engine).
2. Partial-failure path returns the triage summary with `interpretation=None` and a
   recorded error — never discards completed work.
3. Staging dir is always cleaned up, including on error.
4. `DiagnosticResult.to_dict()` / `audit` is JSON-serializable and contains the
   collection command, sandbox metadata, summary, and interpretation-or-error.
5. The §3 sandbox-read permission outcome is resolved and documented in the README.
6. Lint/type checks clean against the repo config.
```
