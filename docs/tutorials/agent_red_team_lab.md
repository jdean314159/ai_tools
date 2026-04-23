# Agent red-team lab

This lab demonstrates three common policy-boundary and sandbox-boundary cases in `agent_lib`:

1. **Blocked command** — the agent is instructed to run a command that is not on the allowlist.
2. **Approval habituation** — the agent is told to apply a patch immediately, but the runtime only produces a proposal because approval is required.
3. **Degraded fallback** — the runtime succeeds only by falling back from the requested sandbox backend to host execution.

The point of the lab is not to prove a perfect sandbox. The point is to inspect:
- what was blocked
- what was merely gated by approval
- what was allowed only in a degraded mode

## Run the example

```bash
PYTHONPATH=agent_lib/src:llm_harness_core/src:llm_inspector/src:. python agent_lib/examples/agent_red_team_lab.py
```

## What to look for

- `blocked_count`, `degraded_count`, and `approval_count`
- warning codes such as:
  - `tool_execution_blocked`
  - `tool_approval_required`
  - `tool_execution_degraded`
- the difference between a **blocked** step and a **degraded but successful** step

## Key lesson

A successful command is not always a safe command. If the runtime fell back from the requested sandbox backend to host execution, that should be treated as a degraded success rather than a clean pass.

## Follow-up questions

1. Which scenario represents a true hard stop?
2. Which scenario could train users into unsafe approval habits?
3. Which scenario would be easy to miss if the UI only showed `success=True`?
