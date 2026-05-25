# ADR-011: Agent execution isolation model

**Date:** 2026-05-24
**Status:** Proposed
**Deciders:** Jeff Dean
**Related:** `docs/design/AGENT_BUILD_NOTES.md`, `agent_lib/AGENT.md` (safety invariants), ADR-008 (monorepo packaging policy)

---

## Context

`ADR_INDEX.md` flags an agent execution isolation model as needed before serious
`agent_lib` expansion. The planned worker/mentor ASC rebuild (see
`AGENT_BUILD_NOTES.md`) makes this concrete: an autonomous loop where a local
worker model proposes and executes actions — including running commands and
editing files — is exactly the case where weak isolation becomes a real hazard,
not a theoretical one. A doom-looping or mis-aligned worker that can write
outside its workspace or run arbitrary commands is a liability regardless of the
mentor layer above it.

`agent_lib/AGENT.md` already states partial invariants:

- Empty `WorkspacePolicy.writable_paths` means no write permission.
- `runnable_commands` is an exact allowlist unless a typed command policy replaces it.
- Approval gates are not sandboxing.
- Sandbox fallback must be reported as degraded execution, not clean success.
- Path resolution must remain confined to the configured workspace root.

These are necessary but not a complete isolation model. They do not yet define
process, network, or worktree boundaries, nor the enforcement mechanism, nor
what "sandbox" concretely means on Jeff's local-first hardware.

This ADR is **Proposed**, not Accepted. Per the co-evolution rule in
`AGENT_BUILD_NOTES.md` (§0), the binding decision should follow the first real
ASC-build run, which will reveal which boundaries actually bite. The purpose
here is to frame the decision space so the eventual choice is informed, and to
record a recommended default direction.

## Decision space (to be resolved before serious agent_lib expansion)

Four boundary dimensions, each needing an explicit policy:

1. **Filesystem.** Workspace-root confinement is partly specified. Open
   questions: symlink-escape handling, temp-file location, read scope (can the
   worker read outside `writable_paths`?), and whether confinement is advisory
   (path checks in `agent_lib`) or enforced (container mount, bind-mount,
   overlay).

2. **Process.** Is LLM-generated/selected command execution confined to a
   subprocess with resource limits (CPU, memory, wall-clock, no new privileges),
   and what is the enforcement layer — `subprocess` + rlimits, a container, or a
   microVM? The course already mandates sandboxed execution for LLM-generated
   code (Modules 3, 6, 8); the agent runtime should not be weaker than what the
   course teaches.

3. **Network.** Default-deny is the safe stance for an autonomous worker. Open
   question: how an explicit allowlist is expressed and enforced, and how the
   optional cloud mentor call is exempted (it is the one sanctioned egress) —
   ideally the mentor call routes through `llm_engines`, not through worker-issued
   network access.

4. **Worktree.** For multi-agent/swarm coordination (mailboxes already exist in
   `agent_lib.coordination`), define whether each agent gets an isolated git
   worktree or branch, how reservations (`FileReservation`) interact with write
   confinement, and how concurrent edits are merged or rejected.

## Recommended default direction (pending validation)

- **Confinement must be enforced, not advisory.** Path checks in Python are a
  defense-in-depth layer, not the boundary. The real boundary should be an OS
  mechanism. On Jeff's local-first hardware, a container (rootless Podman or
  Docker) with explicit bind-mounts for the workspace and `--network none` by
  default is the pragmatic baseline; microVM is over-engineering for the use case.
- **Network default-deny**, with the cloud mentor reached only via `llm_engines`
  from outside the worker's execution boundary — never via worker-issued egress.
- **Process limits always on** (memory, wall-clock, no-new-privileges), with any
  fallback-to-unsandboxed path reported as degraded execution per the existing
  invariant — and, for an autonomous loop, treated as a hard stop rather than a
  warning.
- **One git worktree per agent** for the multi-agent case, with `FileReservation`
  as a coordination hint layered above worktree isolation, not a substitute for it.

## Consequences (anticipated)

- `agent_lib`'s `WorkspacePolicy` grows from a path allowlist into a fuller
  isolation policy object (process/network/worktree fields).
- The execution path gains a dependency on a container runtime for the enforced
  baseline; the advisory-only path remains for environments without one but must
  self-report as degraded.
- The course's sandboxing story and the agent runtime's isolation story converge
  on the same mechanism, which is good for the teaching narrative.

## Open questions deferred to first ASC run

- Which boundary is the first to actually bite in practice (likely process or
  filesystem), and therefore which to enforce first.
- Whether rootless Podman vs. Docker matters for Jeff's Ubuntu 24.04 + RTX 3090
  setup (GPU passthrough into the sandbox for a worker that needs local inference
  is a real wrinkle — the worker model itself may need GPU access, which
  complicates `--network none` and device confinement).
- Whether the mentor-escalation path needs its own audit/isolation treatment.

## Alternatives considered

- **Advisory-only path confinement (status quo).** Rejected as the *target* model:
  adequate for trusted manual use, insufficient for an autonomous worker loop.
  Retained as a degraded fallback only.
- **microVM (e.g. Firecracker) isolation.** Deferred: stronger than needed for a
  single-user local lab, and the GPU-passthrough complication makes it costly.
- **No isolation, rely on the mentor/critic to catch bad actions.** Rejected:
  oversight is gated and the worker is capability-limited (per `AGENT_BUILD_NOTES`
  §3–§4); isolation must not depend on a layer that fires rarely and imperfectly.
