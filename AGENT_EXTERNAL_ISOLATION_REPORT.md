# agent_lib external isolation update

## What changed

- Added optional external command isolation controls to `WorkspacePolicy`:
  - `command_isolation_backend`
  - `command_isolation_image`
  - `command_isolation_network`
  - `command_isolation_fallback_to_host`
  - `command_isolation_extra_args`
  - `command_isolation_mount_path`
- `execute_workspace_command(...)` can now:
  - run directly on the host (`host`)
  - select Docker/Podman automatically (`auto`)
  - require Docker explicitly (`docker`)
  - require Podman explicitly (`podman`)
- Explicit sandbox requests fail safely when the requested backend is unavailable.
- `auto` can fall back to host execution only when the workspace policy allows it.
- Tool metadata now records:
  - requested backend
  - actual backend
  - whether external isolation was used
  - whether fallback occurred
  - image / mount / network settings
  - container command used for execution
- Agent runtime summaries and capability descriptors now surface the new command-isolation settings.

## Validation

- `python -m compileall -q agent_lib llm_inspector_ui engram`
- `PYTHONPATH=. pytest -q agent_lib/tests` → 46 passed
- `PYTHONPATH=. pytest -q llm_inspector_ui/tests` → 23 passed

## Remaining gap

This is optional container-backed isolation, not a complete high-assurance sandbox. Commands still run on the host through a local container engine. Stronger isolation options and richer UI surfacing of blocked/degraded execution remain future work.
