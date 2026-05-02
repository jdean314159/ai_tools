# Native versus integration-mode orchestration

Use this guide with the agent stage of the learning path.

## Native runtime

A native runtime owns the task model, tool runtime, policy checks, traces, and persistence directly. It is easier to make inspectable because every step can emit shared `llm_harness_core` records.

Use native mode when:

- policy enforcement and traceability are central to the lesson
- agent runs need resumable state
- tool calls must be constrained by workspace, command, and approval policy

## Integration mode

Integration mode adapts an external agent or orchestration system into the `ai_tools` inspection and evaluation surface. It is useful when comparing another runtime against the native design, but the external runtime may not expose all internal decisions.

Use integration mode when:

- the lesson is about interoperability
- the external runtime is already required by a project
- partial trace visibility is acceptable and clearly labeled

## Teaching rule

Do not present policy restrictions as sandboxing. A write allowlist, command allowlist, or approval gate is useful, but hard isolation requires a real sandbox boundary such as a container or separate worktree/process model.
