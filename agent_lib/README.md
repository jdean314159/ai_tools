# agent_lib

## Tier: **experimental** — API may change without notice

## Scope

Inspectable agent-orchestration layer. Provides the planner/executor/tool-runtime
loop, coordination primitives (mailbox, sessions), and memory adapters so agent
workflows can be built on top of `llm_engines` and `engram`. Does not provide
its own inference backend or memory store.

**Do not build production systems on `agent_lib`.** The API will move.

## Quick start

```python
# agent_lib is EXPERIMENTAL — expect API changes
from agent_lib import AgentRuntime, AgentTask, LLMActionPlanner, RoleEngineSet
from llm_engines import get_engine

engines = RoleEngineSet(
    planner=get_engine("ollama", "qwen3:27b"),
    executor=get_engine("ollama", "qwen3:8b"),
)
planner = LLMActionPlanner(engines=engines)
runtime = AgentRuntime(planner=planner)

task = AgentTask(goal="Summarize the contents of README.md", context={})
run = runtime.run(task)
print(run.result)
```

For deterministic unit tests, substitute `SequencePlanner`:

```python
from agent_lib import SequencePlanner, AgentRuntime, AgentAction

planner = SequencePlanner(actions=[AgentAction(type="finish", payload={"result": "done"})])
runtime = AgentRuntime(planner=planner)
```



`agent_lib` is the inspectable agent-orchestration layer for the `ai_tools` stack.

Its purpose is not only to help build agentic workflows. It is also meant to help users understand how those workflows behave:

- how plans are formed
- how tools are selected and called
- how state changes over a run
- where failures or stalls happen
- which safeguards constrain execution

In the broader `ai_tools` vision, `agent_lib` should become the agent-side analogue of what `rag_lib` is for retrieval and what `engram` is for memory augmentation: a reusable subsystem that also exposes educational, diagnostic, and observable behavior.

---

## Current design intent

`agent_lib` is meant to be a consumer of the stack, not the center of the stack.

The intended composition path is:

```text
llm_engines + engram + llm_inspector -> agent_lib
```

With optional advanced integrations:

```text
engram -> agent_lib
rag_lib -> agent_lib
```

The long-term direction is:

```text
llm_harness_core -> agent_lib -> llm_inspector -> llm_inspector_ui
```

Agent behavior now has a first shared interop vocabulary, but the package still needs deeper UI integration and stronger execution isolation.

---

## What is currently included

- canonical agent runtime contracts
- a minimal planner / executor / tool runtime loop
- `llm_inspector` trace emission for each step
- lightweight memory adapters for `engram`
- optional full `engram` memory path
- deterministic test helpers such as `SequencePlanner`
- programming-task examples and config-driven workflows
- mailbox/session-oriented integration-mode helpers

This gives the repo a concrete place to explore agent workflows without forcing the rest of the stack to adopt a large external orchestration framework.

---

## What is intentionally not included yet

- distributed runtimes
- large multi-agent frameworks
- provider-specific backend ownership
- a UI of its own
- a hard dependency on LangGraph or any one agent framework

If integrations with external orchestration frameworks are added later, they should sit behind the same public contracts rather than redefining the package around one ecosystem.

---

## Most important current limitation

`agent_lib` is **partially adapted to the newer interop and observability architecture**, but still incomplete.

In particular:

- it does not yet emit the shared `llm_harness_core` event/result vocabulary end to end
- it does not yet participate in the workbench as cleanly as memory and RAG now do
- its execution safety story is still policy-based and partial, not a full OS/container sandbox

So the package should currently be read as:

> promising and useful, but still earlier in architectural maturity than the memory and retrieval paths

---

## Example

```python
from agent_lib import (
    AgentAction,
    AgentRuntime,
    AgentTask,
    LocalTool,
    LocalToolRuntime,
    SequencePlanner,
)

planner = SequencePlanner([
    AgentAction.tool("add", {"a": 2, "b": 3}),
    AgentAction.final("The answer is 5."),
])

tools = LocalToolRuntime([
    LocalTool(
        name="add",
        description="Add two integers.",
        handler=lambda a, b: a + b,
    )
])

runtime = AgentRuntime(planner=planner, tool_runtime=tools)
run = runtime.run(AgentTask(task_id="demo", goal="Add 2 and 3."))
print(run.final_output)
```

---

## Programming-task reference workflow

The package includes a small reference workflow under `agent_lib.examples.programming_task`.

It demonstrates:

- planner/executor role separation via `EngineRoles(planner="mentor", executor="worker")`
- local file-oriented tools such as `read_file`, `replace_text`, and `run_check`
- `engram` as the default memory path
- durable programming-task state and persisted plans under `.agent_state/`
- context-budget management with artifact-backed tool outputs
- `llm_inspector` traces for each step

```python
from agent_lib.examples import run_programming_demo

run, root = run_programming_demo(memory_backend="engram")
print(run.final_output)
print((root / "main.py").read_text())
```

---

## Config-driven programming runtime

```python
from agent_lib import ProgrammingRoleBindings
from agent_lib.examples import (
    build_default_programming_config,
    run_programming_demo_from_config,
)

config = build_default_programming_config(
    session_id="programming_demo",
    memory_backend="engram",
    role_bindings=ProgrammingRoleBindings(
        planner="deepseek_mentor",
        executor="local_worker",
        critic="deepseek_mentor",
    ),
)

run, root = run_programming_demo_from_config(
    config,
    engines_by_name={
        "deepseek_mentor": mentor_engine,
        "local_worker": worker_engine,
    },
)
```

This keeps the programming path explicit and inspectable while still allowing deterministic fallback behavior when no live engines are supplied.

---

## Native mode and integration mode

`agent_lib` supports two complementary execution styles.

### Native mode
Use the built-in `AgentRuntime`, planners, memory adapters, and tool runtime.

This is the clearest path for learning explicit agent orchestration with typed state and unified traces.

### Integration mode
Use the coordination helpers for persistent external agent sessions.

This mode models:

- external agent identities
- typed inter-agent messages
- advisory file reservations
- lightweight team registration

This path is intentionally small. It is meant to support mailbox/session-based orchestration systems without forcing them into the native runtime loop.

---

## Qwen repository-navigation evaluation

`agent_lib.eval.repo_navigation` implements the read-only NAV-TEST-00 harness. It composes the
existing `AgentRuntime` and `LocalToolRuntime` with confined `read_file`, `grep`, and `list_files`
tools, a no-write bounded context builder, cumulative token accounting, tool telemetry, environment
manifests, and region-based scoring.

The live runner requires a pinned Qwen3.6 deployment served by `llama-server` and a ground-truth JSON
file outside the confined root. It uses the server's native `/apply-template`, `/tokenize`, and
`/completion` endpoints so prompt fitting and usage are measured with the deployed model itself:

```bash
python agent_lib/examples/repo_navigation_eval.py \
  --root /path/to/ai_tools \
  --answer-key /outside/eval/answer-key.json \
  --base-url http://127.0.0.1:8081 \
  --output-dir /outside/eval/run-00
```

Each answer-key region must provide `id`, `path`, `start_line`, `end_line`, `classification`, and a
non-empty `required_answer_terms` array. The runner refuses answer keys and result directories inside
the navigation root. It verifies the server's context window and chat template before running,
sends `cache_prompt=false` on every native completion, rejects any response reporting cached prompt
tokens or truncation, and writes all artifacts only to the external result directory.

The experimental `reasoning_loop_guard` text detector is not integrated into
this evaluation. Replay against the recorded NAV runs produced a false positive
on the successful control because the model emitted repeated JSON actions with
thinking disabled. A future NAV guard must inspect typed action/tool trajectory
events here in `agent_lib`; adding reasoning-block events to `llm_engines`
would not expose a signal these runs contain. See
[`NAV-TEST-00-LOOP-GUARD-VALIDATION.md`](../docs/projects/agent_lib/NAV-TEST-00-LOOP-GUARD-VALIDATION.md).

The superseding `action_trajectory_loop_guard` consumes the typed `AgentStep`
trajectory instead. Its pure detector passed the four recorded NAV gate runs:
it fired before 120K on seed0 and sampled seeds 1/3 and did not fire on
successful sampled seed2. `build_navigation_harness` enables the corresponding
between-step control hook: it retains the audited trajectory, removes only the
looping suffix from finalization context, disables tools with a final-only
prompt/schema, and permits at most one finalization call. Unsafe remaining
budget stops without an engine call. See
[`NAV-TEST-00-ACTION-GUARD-VALIDATION.md`](../docs/projects/agent_lib/NAV-TEST-00-ACTION-GUARD-VALIDATION.md).

The evaluation CLI records an explicit `--action-guard-mode`: `off` reproduces
unguarded behavior, `shadow` records the first would-fire intervention without
changing control flow, and `enforce` performs constrained finalization.

See:

- `agent_lib.coordination`
- `agent_lib.examples.integration_mode`
- `../docs/native_vs_integration.md`

---

## Safety and control boundaries

A major architectural concern for `agent_lib` is preventing agent workflows from becoming opaque or unsafe.

The package already has some control mechanisms, but they should not be mistaken for a full sandbox.

Current direction:

- explicit tool runtime boundaries
- workspace/path policy enforcement
- inspectable step traces
- deterministic test/runtime helpers

Still needed:

- stronger filesystem isolation
- process isolation
- network policy control
- resource/time-limit hardening
- clearer stuck-run / monitor / supervisor behavior

This is one of the highest-priority future areas in the repo.

---

## Development

```bash
cd agent_lib
pip install -e .[dev]
pytest -q
```

---

## Project context

For repo-wide architecture and current priorities, see:

- `../docs/design/VISION.md`
- `../docs/internal/ROADMAP.md`
- `../ADR_INDEX.md`


## Current safety controls

`agent_lib` now has stronger process-level protections for programming-style tool execution:

- exact command allowlist enforcement
- workspace-root path confinement for file tools
- approval modes for patch application
- patch ownership leasing across workers
- isolated copy/worktree workspace preparation
- command timeout enforcement
- environment scrubbing by default for `run_command`
- output truncation for large command output
- POSIX process-group isolation so timeout cleanup reaches spawned subprocesses
- optional external command isolation through Docker or Podman

Key `WorkspacePolicy` controls now include:

- `command_timeout_seconds`
- `max_command_output_chars`
- `inherit_environment`
- `allowed_environment_keys`
- `denied_environment_keys`
- `command_isolation_backend`
- `command_isolation_image`
- `command_isolation_network`
- `command_isolation_fallback_to_host`

External command isolation is now available as an explicit workspace-policy choice. When enabled, `run_command` can execute through Docker or Podman with the workspace mounted into a dedicated container and networking disabled by default. The resulting tool metadata records which backend was requested, which backend actually ran, whether host fallback was used, and the container/image settings involved.

This is still not a complete kernel- or VM-level sandbox. Commands are better isolated than before, but the broader safety story still needs optional higher-assurance execution backends and clearer UI surfacing of blocked or degraded runs.
