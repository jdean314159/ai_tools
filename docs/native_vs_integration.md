# Native mode vs integration mode

This guide explains when to build directly on `agent_lib` and when to enhance an existing external-session orchestration system.

The same lower-level layers should support both paths:
- `llm_engines` for model access and role-aware engine selection
- `engram_lite` for memory and prompt augmentation
- `llm_inspector` for normalized traces and comparisons

The difference is where orchestration policy lives.

---

## Native mode

Native mode uses the typed runtime in `agent_lib`:
- `AgentRuntime`
- planners / critics
- tool runtime
- memory adapters
- normalized per-step traces

Use native mode when you want:
- explicit runtime policy in code
- typed task state and typed transitions
- unified patch / verification / escalation control
- strong inspectability
- a reusable architecture for new projects

### Strengths
- easier to reason about policy
- easier to test deterministically
- easier to compare runs and trace decisions
- better fit for reusable programming-tool workflows

### Costs
- more upfront design work
- more contracts to define
- less immediate reuse of existing agent shells

### Best fit
- new programming tools
- mentor / worker / critic orchestration
- tasks that need explicit patch lifecycle control
- systems where explainability matters

---

## Integration mode

Integration mode keeps orchestration outside the native runtime and uses `ai_tools` to enhance it.

Typical components:
- persistent external agent sessions
- mailbox or message-based coordination
- optional advisory file reservations
- `engram_lite` for shared and per-agent memory
- `llm_inspector` for traces and comparisons

Use integration mode when you want:
- to upgrade an existing workflow without rewriting it
- to preserve persistent agent sessions or a terminal-driven environment
- to add memory or observability to an already-working orchestration system
- to experiment quickly with multi-agent coordination

### Strengths
- pragmatic adoption path
- works well with existing tools and sessions
- lower migration cost for existing systems
- good for exploring external-agent coordination patterns

### Costs
- coordination policy is often more implicit
- inspectability is less uniform unless carefully added
- harder to guarantee patch lifecycle discipline
- easier for messaging complexity to grow

### Best fit
- mailbox/message-based systems
- persistent coding-agent sessions
- externally orchestrated agent teams
- incremental upgrades to a working stack

---

## The same simple programming task in both modes

`agent_lib` includes a side-by-side comparison example for the same bug-fix task:
- native mode repairs the file through `AgentRuntime`
- integration mode coordinates a mentor, scout, and worker through typed messages plus advisory file reservations

```python
from agent_lib.examples import run_mode_comparison_demo

result = run_mode_comparison_demo(memory_backend="engram_lite")
print(result.native_final_output)
print(result.integration.final_output)
```

This is the easiest way to compare the teaching value of the two styles without changing the task itself.

---

## Which mode should I choose?

Choose **native mode** if most of these are true:
- you are starting a new project
- you want a reusable runtime
- you need patch / verification / escalation to be explicit
- you want the strongest tracing story
- you want mentor/worker policy in code rather than mostly in prompts

Choose **integration mode** if most of these are true:
- you already have a working orchestrator
- you want to keep persistent external sessions
- you mainly need memory, coordination, or observability improvements
- you want low-friction adoption
- you do not want to rewrite your existing runtime yet

---

## Recommended teaching order

For new users, the recommended learning path is:
1. `llm_engines`
2. `engram_lite`
3. `llm_inspector`
4. `language_tutor`
5. native `agent_lib`
6. integration mode as a comparison and extension path

That order keeps the architecture clear while still showing that the stack is flexible enough to enhance external orchestration systems.
