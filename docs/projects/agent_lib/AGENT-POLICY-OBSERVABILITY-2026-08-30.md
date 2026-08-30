# Agent policy and observability characterization — 2026-08-30

## Question and frozen boundary

Does the existing native `AgentRuntime` expose policy decisions and objective
failure escalation consistently through Inspector step traces and shared
`OperationResult` diagnostics?

Profile `examples.agent_policy_observability`, version 2 freezes six
deterministic cases over `ProgrammingToolRuntime`:

1. an ungranted tool;
2. a path escaping the workspace;
3. a write outside the writable allowlist;
4. a command outside the command allowlist;
5. a write requiring human approval; and
6. an objective verifier failure that triggers the critic.

No command executes and no file handler applies a change. The probe uses no
model, network, Engram backend, OS sandbox, or external evaluator. It retains
only expected/observed error codes, booleans, warning codes, and the suite
digest; raw outputs, arguments, workspace paths, and environment values are
excluded.

## Predeclared gate

Every case must produce its expected policy outcome and the common action,
workspace-policy, tool-invocation, and tool-result events. Blocked actions must
agree across the Inspector `blocked` tag, shared `blocked_actions` diagnostics,
and `tool_execution_blocked` warning. Approval must agree across the equivalent
three surfaces. Objective failure must appear as a tool-failure warning, one
critic escalation in the run summary, and an escalated critic action event.

## Disclosed version-1 outcome

Version 1 preserved a failed gate. All six policy outcomes and all common trace
events were correct. Path escape, write denial, command denial, approval, and
objective-failure escalation had complete signal parity. `tool_not_granted`
enforced the deny but appeared as generic `agent_tool_failure` and
`tool_invocation_failed`: neither Inspector's `blocked` tag nor shared
`blocked_actions`/`tool_execution_blocked` represented it as a policy block.

Artifact:
`docs/projects/agent_lib/runs/2026-08-30-agent-policy-observability-v1.json`

SHA-256: `b65b2591202221b13c341e293d4525d0a92b73e912c8f2ce1af2451056c9b063`

Version 2 changes no case, expected outcome, or gate. It adds the existing
`tool_not_granted` error code to the blocked-error classification used by the
Inspector trace emitter and shared interop adapter.

## Version-2 outcome

Version 2 passed all three gates in 6/6 cases. Every case emitted the common
action, workspace-policy, invocation, and result events. All four policy denials
now agree across enforcement, Inspector `blocked` tags, shared
`blocked_actions`, and `tool_execution_blocked` warnings. Human approval agrees
across its trace tag, shared diagnostic, and warning. The objective verifier
failure produced a tool-failure warning, one critic escalation, and an escalated
critic action event.

Artifact:
`docs/projects/agent_lib/runs/2026-08-30-agent-policy-observability-v2.json`

SHA-256: `3044149abef32e2abc9fbbca7f9ba329d67e367451bdc864e5173d8e6465cc85`

This closes one classification defect, not the package's broader safety gap.
The profile does not exercise actual command execution, container isolation,
patch ownership under concurrency, model-generated plans, or UI rendering.
