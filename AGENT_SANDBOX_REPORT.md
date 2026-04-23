# Agent sandbox hardening report

## Completed

- `ProgrammingToolRuntime` now handles `run_command` directly after workspace-policy validation.
- `execute_workspace_command(...)` now accepts an optional `WorkspacePolicy` and uses it to enforce:
  - timeout limits
  - default environment scrubbing
  - explicit environment allow/deny lists
  - output truncation
  - POSIX process-group isolation for timeout cleanup
- `WorkspacePolicy` now carries command execution controls:
  - `command_timeout_seconds`
  - `max_command_output_chars`
  - `inherit_environment`
  - `allowed_environment_keys`
  - `denied_environment_keys`
- `agent_lib` capability and runtime summaries now surface the new safety controls.
- Added a monorepo convenience shim for `engram` so root-level test runs are reliable.

## Validation

- `python -m compileall -q agent_lib llm_inspector_ui engram`
- `pytest -q agent_lib/tests`
- `pytest -q llm_inspector_ui/tests`

## New regression coverage

- environment scrubbing by default
- explicit re-allow of selected environment variables
- timeout reporting for long-running commands
- truncation of oversized command output

## Remaining gap

This is stronger process-level hardening, not a true OS/container sandbox. Commands still run on the local host. The next safety step is optional external isolation (for example, containerized or sandboxed execution) with the same traceability and policy diagnostics.
