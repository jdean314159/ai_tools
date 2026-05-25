# AGENT.md — agent_lib

## Role

`agent_lib` provides inspectable agent orchestration, programming-task workflows, policy checks, safety labs, and adapters to the shared `ai_tools` stack.

## Before expanding this package

Read `docs/design/AGENT_BUILD_NOTES.md` first. It captures the design stance
(co-evolution: build a capability when a concrete run fails without it, not when
a design discussion suggests it), the worker/mentor pattern for the ASC rebuild,
gated oversight, long-horizon-loop engineering, and context-rot reduction over
Engram primitives.

## Safety invariants

- Empty `WorkspacePolicy.writable_paths` means no write permission.
- `runnable_commands` is an exact allowlist unless a future typed command policy replaces it.
- Approval gates are not sandboxing.
- Sandbox fallback must be reported as degraded execution, not clean success.
- Path resolution must remain confined to the configured workspace root.

## Preferred validation

```bash
python -m compileall -q agent_lib
python -m pytest -q agent_lib/tests
```

For targeted policy changes:

```bash
python -m pytest -q agent_lib/tests/test_programming_harness.py
```
