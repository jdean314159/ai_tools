# SPEC-COORD-01 — Coordination Control Plane: Permissions, Routing, Never-Execute Guard

**Status:** Draft for Codex.
**Covers:** Ledger gaps 2 (per-agent tool permissions), 1 (capability routing), 4 (never-execute
guard). Gap 3 (enforced reservations) is split to SPEC-COORD-02.
**Depends on:** SPEC-COORD-00 (gap ledger confirmed), `agent_lib` editable install.
**Mode:** Deterministic-first, staged. No live model. Each stage has its own probe assertion so a
failure localizes to the stage that introduced it.
**Discipline:** This spec touches BOTH repos. `agent_lib` changes land in `~/repos/ai_tools` with
ADR-017. Probe code lands in `~/repos/computer_helper`. Keep them in separate commits. READ the
confirmed enforcement model below against `programming.py` before writing.

---

## 0. Confirmed enforcement model (the basis for the location decision)

From `agent_lib/src/agent_lib/programming.py`:

- `EnforcingToolRuntime.invoke(call)` is the single gate. It intercepts every `ToolCall`, checks
  it against `WorkspacePolicy`, and either denies (returns `ToolResult(success=False,
  meta={'error': ...})`) or delegates to `self.inner.invoke(call)`.
- Enforcement is **per-runtime**, keyed to one `owner_id` and one `WorkspacePolicy`. It is already
  effectively per-agent — just not addressed through the coordination layer.
- Denials **return a failure result; they do not raise.** Same pattern as reservation conflicts.
  Good for deterministic assertion.
- The gate checks **paths** (`writable_paths`) and **commands** (`runnable_commands`). It has **no
  tool-name filter** — no "this agent may not call this tool at all." That absence is gap 2.

**Location decision (recommended, grounded in the above):** Do NOT build a parallel permission
layer in the coordination module, and do NOT bolt per-session state onto `WorkspacePolicy`'s
execution semantics. Instead:

1. Add an `allowed_tools: list[str] | None` field to `WorkspacePolicy` (None = no tool-name
   restriction, preserving current behavior). The existing `invoke()` gate consults it.
2. Give the coordination layer a factory that builds a per-session `EnforcingToolRuntime` carrying
   that session's grant.

This reuses the validated gate instead of duplicating enforcement, and keeps a single source of
truth for "is this call allowed." The coordination layer gains permission awareness by
*constructing correctly scoped runtimes*, not by re-implementing checks. Rejected alternatives and
their trade-offs are recorded in ADR-017 §Alternatives.

---

## Stage 1 — Per-agent tool permissions (gap 2)

**`agent_lib` change (ADR-017):**

1. Add to `WorkspacePolicy`:
   ```python
   allowed_tools: list[str] | None = None  # None = unrestricted (current behavior)
   ```
2. In `EnforcingToolRuntime.invoke()`, BEFORE the path/command checks, add a tool-name gate:
   ```python
   if self.workspace.allowed_tools is not None and call.name not in self.workspace.allowed_tools:
       return self._deny(call, reason=f"Tool {call.name!r} is not granted to this agent.",
                         error="tool_not_granted")
   ```
   Placement before path/command checks is deliberate: an ungranted tool is denied on identity
   alone, regardless of arguments.
3. Confirm `None` default leaves every existing test green — this is the backward-compat invariant.

**Deterministic probe (Stage 1 assertion, `computer_helper`):**
- Build an `EnforcingToolRuntime` with `allowed_tools=["read_file"]`.
- Assert `read_file` (valid path) succeeds.
- Assert `replace_text` returns `success=False`, `meta["error"]=="tool_not_granted"` — denied on
  identity, NOT `write_denied`, confirming the new gate fires before the path check.
- Assert a runtime with `allowed_tools=None` permits both (backward compat).

**Done:** existing `agent_lib` suite green; three Stage-1 assertions pass.

---

## Stage 2 — Capability-based routing (gap 1)

Routing composes on Stage 1: an agent's capability IS its tool grant.

**`agent_lib` change (ADR-017):**

1. Add to `ExternalAgentSession`:
   ```python
   capabilities: list[str] = field(default_factory=list)  # tool names this agent can serve
   ```
2. Add a router to the coordination module (new small function or method on
   `ExternalSessionCoordinator`), NOT a new class hierarchy:
   ```python
   def route_by_capability(team: ExternalAgentTeam, required_tool: str) -> ExternalAgentSession | None:
       """Return the first session whose capabilities include required_tool, else None."""
   ```
   First-match is intentional for the deterministic probe; ambiguity handling (multiple matches)
   is recorded as a Stage-2 ledger note, not built now.

**Deterministic probe (Stage 2 assertion):**
- Team: `fs_agent` (capabilities=["read_file","replace_text"]), `search_agent`
  (capabilities=["retrieve"]), `calc_agent` (capabilities=["compute"]).
- Assert `route_by_capability(team, "retrieve") is search_agent`.
- Assert `route_by_capability(team, "compute") is calc_agent`.
- Assert `route_by_capability(team, "nonexistent") is None` — no silent misroute.
- **Integration assertion (this is the point):** route a `"retrieve"` task → get `search_agent` →
  build its runtime with `allowed_tools=search_agent.capabilities` → assert that runtime DENIES
  `replace_text` with `tool_not_granted`. This proves routing and permissions compose: the routed
  agent physically cannot exceed its capability grant.

**Done:** four Stage-2 assertions pass, including the integration assertion.

---

## Stage 3 — Never-execute guard (gap 4)

The degenerate case of Stage 1: the coordinator is a session with an empty tool grant under the
same gate. This converts "never-executes-by-absence" into "never-executes-by-enforcement."

**`agent_lib` change (ADR-017):**

1. Provide a constructor/helper that builds the coordinator's runtime with `allowed_tools=[]`
   (empty list, NOT None — empty means "no tools granted," None means "unrestricted"). Document
   this distinction prominently; it is the crux and an easy place to introduce a bug.

**Deterministic probe (Stage 3 assertion):**
- Build a coordinator runtime with `allowed_tools=[]`.
- Assert EVERY tool call (`read_file`, `replace_text`, `run_command`) returns `success=False`,
  `meta["error"]=="tool_not_granted"`.
- Assert the distinction explicitly: a runtime with `allowed_tools=[]` denies all; a runtime with
  `allowed_tools=None` permits. A test that conflates these two is the failure mode to guard
  against.

**Done:** Stage-3 assertions pass; the empty-vs-None distinction is asserted, not assumed.

---

## 1. ADR-017 requirements

Write `~/repos/ai_tools/adr/ADR-017-coordination-permission-model.md`:
- Decision: tool-grant check added to existing `EnforcingToolRuntime` gate; coordination gains
  permission awareness via scoped-runtime construction.
- §Alternatives: (a) parallel permission layer in coordination module — rejected, duplicates
  enforcement; (b) per-session state on WorkspacePolicy execution semantics — rejected, conflates
  session identity with workspace config. Record why each was rejected.
- §Invariants: `allowed_tools=None` ⇒ unrestricted (backward compat); `allowed_tools=[]` ⇒ deny
  all; tool-name gate fires before path/command checks.
- Link the three ledger gaps this closes; note gap 3 deferred to COORD-02.

## 2. Done criteria (whole spec)

- [ ] ADR-017 written with alternatives and invariants.
- [ ] `agent_lib` changes in one commit; existing `agent_lib` suite green (backward compat proven).
- [ ] All Stage 1/2/3 deterministic assertions pass, in `computer_helper`.
- [ ] The two composition assertions pass: routed agent can't exceed grant (Stage 2); coordinator
      with `[]` denies all (Stage 3).
- [ ] `python -m compileall -q` clean both repos; `git diff --check` clean both repos.
- [ ] Probe commit (computer_helper) and library commit (ai_tools) are separate.
- [ ] `COORD_GAP_LEDGER.md` updated: gaps 1, 2, 4 marked closed with the closing commit; gap 3
      still open, pointing to COORD-02.

## 3. Report-back

- Per-stage assertion results.
- Confirm backward compat: did any existing `agent_lib` test change behavior? (Must be no.)
- The two composition assertions verbatim — these are the real result; the per-stage ones are
  scaffolding.
- Any place the empty-list-vs-None distinction was fragile during implementation.

## 4. Explicitly out of scope

- Enforced reservations (gap 3) — COORD-02.
- Multiple-capability-match disambiguation in routing — noted, not built.
- Any live-model run — COORD-01 is deterministic. A live multi-agent run waits until the control
  plane is verified deterministically end to end.
