# Phase 0 Build Spec — Read-Only Sandbox Spine

**For:** an autonomous coding agent (Codex) to produce the first draft.
**Parent:** `docs/projects/diagnostics_agent/CAMPAIGN.md`, Phase 0.
**Status:** committed.

---

## 1. Objective

Build the isolation boundary for the diagnostics agent and nothing else. The
deliverable is a small Python package that can run a **read-only** command inside
a locked-down container against host paths mounted read-only, capture its output,
enforce resource and time limits, and guarantee the container is torn down. No
LLM, no log parsing, no network — those are later phases.

The single most important property: the container **cannot write to the host and
cannot reach the network**, and that property is provable by tests.

## 2. Deliverables (exact layout)

```
diagnostics_agent/
  pyproject.toml
  README.md
  src/diagnostics_agent/
    __init__.py
    sandbox.py        # ReadOnlySandbox, SandboxConfig, SandboxResult
    errors.py         # typed exceptions
  tests/
    test_sandbox_argv.py    # unit — must pass with NO container runtime present
    test_sandbox_exec.py    # integration — skip when podman absent
```

- `src/` layout (matches the repo's six-of-seven convention).
- Python 3.11+. `from __future__ import annotations` at the top of each module.
- **Zero third-party runtime dependencies.** Use `subprocess` from the stdlib; do
  not add the podman Python bindings. Test dependency: `pytest` only.
- Match the repo's existing lint/type config (ruff/mypy) if present.

## 3. Public API (implement this contract; do not invent a different shape)

```python
# errors.py
class SandboxError(Exception): ...
class RuntimeNotFoundError(SandboxError): ...      # podman/docker binary missing
class ImageNotAvailableError(SandboxError): ...    # image not pulled locally
class MountError(SandboxError): ...                # mount path missing / not absolute
class SandboxTimeout(SandboxError): ...

# sandbox.py
@dataclass(frozen=True)
class SandboxConfig:
    image: str = "docker.io/library/alpine:3.20"   # minimal; must be pre-pulled
    mounts: tuple[tuple[str, str], ...] = ()        # (host_abs_path, container_path), mounted ro
    memory: str = "256m"
    cpus: str = "1.0"
    pids_limit: int = 128
    timeout_s: float = 30.0
    max_output_bytes: int = 1_048_576               # 1 MiB; stdout truncated beyond this
    user: str = "65534:65534"                       # nobody:nogroup inside the container
    tmpfs_tmp: bool = True                           # writable /tmp because rootfs is read-only
    tmpfs_size: str = "16m"
    runtime: str = "podman"                          # "docker" acceptable fallback
    extra_run_args: tuple[str, ...] = ()             # escape hatch; keep empty by default

@dataclass(frozen=True)
class SandboxResult:
    argv: list[str]            # full runtime invocation actually run (audit record)
    inner_command: list[str]   # the command executed inside the container
    stdout: str
    stderr: str
    exit_code: int
    duration_s: float
    timed_out: bool
    truncated: bool

class ReadOnlySandbox:
    def __init__(self, config: SandboxConfig | None = None) -> None: ...

    def build_argv(self, command: Sequence[str]) -> list[str]:
        """PURE function: construct the runtime argv from config + command.
        No side effects, no subprocess. This is the security-critical surface and
        MUST be unit-testable without a container runtime present."""

    def preflight(self) -> None:
        """Validate runtime binary exists, image is available locally, and every
        mount host path exists and is absolute. Raise the typed errors above."""

    def run(self, command: Sequence[str]) -> SandboxResult:
        """preflight(), then execute build_argv(command) via subprocess with the
        wall-clock timeout. Guarantee container teardown even on timeout/error."""
```

## 4. Security invariants — `build_argv` MUST always emit these

Every invocation, unconditionally:

- `--network none`
- `--read-only` (read-only container rootfs)
- `--cap-drop ALL`
- `--security-opt no-new-privileges`
- `--user <config.user>`
- `--pids-limit <config.pids_limit>`
- `--memory <config.memory>`
- `--cpus <config.cpus>`
- `--rm`
- a unique `--name diag-sbx-<uuid4hex>` (used to guarantee teardown)
- each mount rendered as `-v <host>:<container>:ro`
- if `tmpfs_tmp`: `--tmpfs /tmp:rw,noexec,nosuid,nodev,size=<tmpfs_size>`

Invariants `build_argv` MUST never emit: `--privileged`, any `--cap-add`, any
`--network` value other than `none`, any writable (`:rw` or unsuffixed) bind mount
of a host path, any `--device`.

`build_argv` MUST raise `ValueError` on an empty command and `MountError` on a
non-absolute host mount path.

## 5. `run` behavior

- Call `preflight()` first; let typed errors propagate.
- Execute with `subprocess.run(argv, capture_output=True, text=True, timeout=...)`.
- On `subprocess.TimeoutExpired`: set `timed_out=True`, `exit_code=124`, then
  **force teardown** by calling `<runtime> rm -f <name>` (the unique name from the
  argv). Do this in a `finally` so a normal exit also leaves no container behind.
- Truncate `stdout` to `max_output_bytes` (UTF-8 safe); set `truncated=True` when
  truncation occurred. `stderr` may be capped the same way.
- Always populate `argv` and `inner_command` in the result for the audit trail.

## 6. Tests

### Unit (`test_sandbox_argv.py`) — must pass with no podman/docker installed
- Parametrized: each required flag from §4 appears in `build_argv([...])`.
- Negative: `--privileged`, `--cap-add`, writable mounts, and non-`none` networks
  never appear.
- Mounts render exactly as `-v host:container:ro`.
- Non-default config (memory, cpus, pids_limit, user, tmpfs_size) propagates.
- Empty command → `ValueError`; relative mount path → `MountError`.

### Integration (`test_sandbox_exec.py`) — `pytest.mark.skipif(shutil.which("podman") is None ...)`
Use a **hermetic temp file** the test itself creates and mounts read-only; do not
depend on real host logs being present.
- Read back: `cat` the mounted temp file → its contents, `exit_code == 0`.
- **Read-only proof:** attempt to write to the mounted path from inside →
  non-zero exit (the boundary test, not just a happy path).
- **Network proof:** `ls /sys/class/net` lists only `lo` (no other interface).
- **Timeout:** `sleep 60` with `timeout_s=2` → `timed_out is True` and no leftover
  container with the run's name (`podman ps -a` clean).
- **Truncation:** generate output larger than a small `max_output_bytes` →
  `truncated is True`.

## 7. Known wrinkle to surface, not solve (expected Phase 0 friction)

Under **rootless podman**, container UID 0 maps to the invoking host user and a
non-root `--user` maps to a subuid. Real host logs like `/var/log/auth.log` are
often `root:adm 0640` and may be **unreadable** by the mapped user — a permission
denial, not a sandbox failure. Phase 0 hermetic tests sidestep this (the temp file
is owned by the test user). Do **not** work around it by loosening isolation
(no `--privileged`, no running as host root). Just note it in the README as the
finding that will inform the Phase 0+ choice between (a) a more permissive mapped
user and (b) the host-export staging pattern from the CAMPAIGN doc. Surfacing this
cleanly is a Phase 0 success, not a bug.

## 8. README (brief)

State purpose (sandbox spine for the diagnostics agent), the one-time setup
(`podman pull docker.io/library/alpine:3.20`), a 5-line usage example calling
`ReadOnlySandbox().run(["cat", "/logs/sample.log"])` with a mount, the test split
(unit runs anywhere; integration needs rootless podman), and the §7 wrinkle.

## 9. Non-goals (do NOT build these in Phase 0)

No LLM or `llm_engines` integration. No `journalctl` handling (plain file reads
only). No log parsing, dedup, or triage. No `engram` or `llm_inspector`. No
network access of any kind. No write/remediation capability. No CLI beyond an
optional minimal `__main__` demo. No multi-runtime abstraction beyond the
`runtime` string. Do not add runtime dependencies.

## 10. Acceptance criteria

1. Unit tests pass in an environment with no container runtime.
2. Integration tests pass on rootless podman with the image pulled, including the
   read-only-write-fails and network-isolation-fails proofs.
3. No leftover containers after the full test run.
4. `build_argv` is pure and every §4 invariant is asserted by a unit test.
5. Lint/type checks clean against the repo config.
