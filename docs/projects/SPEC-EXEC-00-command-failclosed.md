# SPEC-EXEC-00 — Fail-Closed Workspace Command Execution

**Status:** Implemented.
**Covers:** The agentic-execution boundary audit that ADR-020 left open ("confirm no `agent_lib`
tool-dispatch path executes model-proposed code outside the sandbox/tool boundary").
**Depends on:** `agent_lib` editable install. ADR-017 (deny-by-default enforcement model),
ADR-020 (data-only loading; this closes its open follow-on).
**Mode:** Deterministic-only. No live model. Single repo (`ai_tools`). No probe in
`computer_helper` — the defect and its proof are both in-tree, so this is not a cross-repo spec.
**Discipline:** READ the confirmed model below against `programming.py` before writing. Library
change + example fix + regression test in one commit; record the audit outcome in ADR-020 as a
closure addendum.

---

## 0. Confirmed enforcement model (the basis for this change)

All line numbers are against `agent_lib/src/agent_lib/programming.py` at HEAD `ccc50c6` unless noted.

**The gated path is correct — do not touch its logic.**
`EnforcingToolRuntime.invoke()` handles `run_command` at line 538: it reads the `command`
argument, denies empty commands, then calls `_command_allowed(command, self.workspace.runnable_commands)`
(line 542) and denies on miss before delegating to `execute_workspace_command(...)` (line 544).
`_command_allowed` (def near line 550) requires an **exact shlex-normalized string match** against
the allowlist (`normalized in allowed_norm`). A model-proposed command that is not verbatim
pre-approved is denied. This is the intended deny-by-default posture and is **out of scope** for
changes here except as the behavior the regression test must confirm still holds.

**The defect is the convenience default in `execute_workspace_command`.**
Signature (line 562):
```python
def execute_workspace_command(root, command, workspace_policy: WorkspacePolicy | None = None) -> ToolResult:
```
Line 564:
```python
policy = workspace_policy or WorkspacePolicy(root=str(workspace), runnable_commands=[command])
```
When `workspace_policy is None`, the function **fabricates a policy whose allowlist is the command
it was just handed** — i.e. it allowlists its own input — then `shlex.split`s the string and
`Popen`s it (line 608). Any command reaching this branch executes. The auto-built policy does not
configure external isolation, so `_resolve_command_isolation_backend` resolves to `host`: execution
is on the host, not in a container. This is the "model-proposed code outside the tool boundary"
ADR-020 named as open.

**The reachable exploit of that default is the example caller.**
`agent_lib/src/agent_lib/examples/programming_task.py:329`:
```python
handler=lambda command: execute_workspace_command(workspace.root, command),
```
No policy passed → the `None` branch fires → the model-supplied `command` string self-allowlists
and runs on the host. The `workspace` object holding the real policy is in scope at that line.

**Audit conclusion:** the dispatcher boundary (`EnforcingToolRuntime`) is intact. The exposure is a
fail-*open* default in a library function plus one example that relies on it. No other caller of
`execute_workspace_command` passes `None` (grep below).

---

## 1. Must be built (does not exist yet)

Nothing structural is missing. The change is a default-flip from fail-open to fail-closed plus a
caller fix. No new fields, no new types.

---

## Stage 1 — Make `execute_workspace_command` fail closed

**`agent_lib` change:**

In `execute_workspace_command`, replace the self-allowlisting default (line 564) with an explicit
fail-closed guard. When no policy is supplied, the function must refuse rather than invent
permission for its own argument:

```python
if workspace_policy is None:
    return ToolResult(
        name='run_command',
        output='run_command requires an explicit WorkspacePolicy; refusing to execute without one.',
        success=False,
        meta={
            'error': 'no_workspace_policy',
            'command': command,
            'cwd': str(workspace),
        },
    )
policy = workspace_policy
```

Rationale for refusing rather than defaulting to an empty allowlist: an empty-allowlist policy would
also deny the command, but it would do so *after* constructing environment, resolving the sandbox
backend, and entering the allowlist comparison — and it would silently mask a caller that forgot to
pass policy. An explicit `no_workspace_policy` result names the caller error at the boundary. Keep
the failure a returned `ToolResult(success=False)`, not a raise — consistent with every other denial
in this module (path-denied, command-denied, ownership-denied) and required for deterministic
assertion.

**Note:** `_command_allowed`, the `invoke()` gate, and the `Popen`/isolation path are unchanged. The
gated dispatcher already passes its real policy (line 544), so this change is invisible to the
correct path and only affects callers that pass `None`.

## Stage 2 — Fix the example caller

**`agent_lib` change:**

`examples/programming_task.py:329` — pass the in-scope policy:

```python
handler=lambda command: execute_workspace_command(
    workspace.root, command, workspace_policy=workspace.policy
),
```

Verify the attribute name against the `workspace` object actually constructed in that example
(read the construction site — it may be `workspace.policy`, `workspace.workspace`, or a local
`policy` variable; cite the real name in the commit message). The example's `run_command` tool must
execute only commands the example's own policy allowlists. If the example currently relies on
arbitrary commands running, that reliance is the bug being removed; constrain `runnable_commands`
in the example's policy to the verification/inspection commands the example actually needs.

## Stage 3 — Regression test (the audit's standing proof)

**New test** (place with the existing `programming.py` tests; match their fixture style):

1. `test_execute_workspace_command_refuses_without_policy`: call
   `execute_workspace_command(tmp_path, "echo hi")` with no `workspace_policy`. Assert
   `result.success is False` and `result.meta['error'] == 'no_workspace_policy'`. Assert the command
   did **not** run (e.g. no side-effect file it would have created; or assert output is the refusal
   string, not `echo` output).
2. `test_execute_workspace_command_runs_allowlisted_with_policy`: pass an explicit
   `WorkspacePolicy(root=..., runnable_commands=["echo hi"])`; assert `success is True` and the
   command ran. Confirms Stage 1 did not break the legitimate path.
3. `test_enforcing_runtime_still_denies_unlisted_command`: drive a `run_command` `ToolCall` with a
   command absent from `runnable_commands` through `EnforcingToolRuntime.invoke`; assert
   `error == 'command_denied'`. Confirms the dispatcher gate is untouched.

These three lock the audit conclusion in place: the only way to execute is an explicit policy whose
allowlist contains the exact command.

---

## Verification (run before the commit is considered complete)

- `grep -rn "execute_workspace_command" --include='*.py' agent_lib/src` shows no remaining
  production caller that passes `None` (the example is the only one; confirm it is fixed). Tests may
  call without a policy only to assert fail-closed refusal.
- Targeted `agent_lib` tests pass, including the three new ones.
- `python -c "import agent_lib"` (or the repo's editable-install smoke check) succeeds.

## Assumptions to verify (not read end-to-end)

- The exact policy attribute on the example's `workspace` object (Stage 2) — read the construction
  site before editing.
- That no caller outside `agent_lib` (e.g. in `examples/` of other packages, or `course/`) invokes
  `execute_workspace_command` with `None`. The grep above was scoped to `agent_lib`; widen it to the
  repo root during verification.

## Out of scope

- Container/sandbox backend behavior (`_resolve_command_isolation_backend`, `_build_container_command`)
  — unchanged; this spec does not alter isolation, only refuses to run when un-policied.
- The `EnforcingToolRuntime` allowlist semantics — confirmed correct, asserted by test 3, not modified.
- Any `computer_helper` probe — the defect and proof are in-tree; no cross-repo commit pair.

## ADR-020 closure note (write on completion)

Add an addendum to ADR-020 recording: the agentic-execution boundary audit found the dispatcher
gate (`EnforcingToolRuntime.invoke`) intact and deny-by-default, and one fail-open default in
`execute_workspace_command` (self-allowlisting when un-policied) reachable through
`examples/programming_task.py`. Resolved by failing closed on a missing policy plus fixing the
example to pass its policy; locked by regression tests. The ADR-020 follow-on is thereby closed.
