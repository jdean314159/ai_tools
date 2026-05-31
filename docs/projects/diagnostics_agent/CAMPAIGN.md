# Project: Read-Only Diagnostics Agent

**Date:** 2026-05-29
**Status:** Proposed (Phases 0–2 committed; Phases 3–5 gated on validation)
**Deciders:** Jeff Dean
**Related:** ADR-011 (agent execution isolation), `docs/design/AGENT_BUILD_NOTES.md` §0 (co-evolution rule), course Modules 3/6/8 (sandboxed execution requirement), `llm_engines`, `engram`, `llm_inspector`

---

## Goal

A locally-hosted assistant that inspects the host system — logs first, later other
read-only diagnostics and security checks — and reports what it finds in plain
language. It correlates events across sources, explains cryptic messages,
prioritizes by actual risk, and remembers across sessions which findings the user
has already judged benign.

This is the first slice of a broader "computer helper" concept. Diagnostics was
chosen as the entry point because a read-only workload **cannot damage the system
it inspects**, which lets the isolation boundary be built and validated before any
action-taking capability exists.

## Scope

**In scope:** read-only inspection of host logs and system state; deterministic
triage; LLM interpretation of triaged output; later, LLM-driven exploratory
querying (RLM); cross-session memory of user judgments; an audit trail of every
command executed.

**Out of scope (this project):** any write, modify, delete, or remediation action;
network egress from the sandbox; multi-agent coordination; GPU access inside the
sandbox.

## Design principles

1. **Front-load the safety boundary.** The sandbox is the spine, built and proven
   empty before any intelligence is added.
2. **Add the dangerous capability last.** The LLM does not execute generated code
   until Phase 3, on top of an already-validated boundary.
3. **Every phase is independently runnable.** Friction from a real run drives the
   next phase, rather than designing the whole agent up front (AGENT_BUILD_NOTES §0).
4. **Enforced isolation, not advisory.** Python path checks are defense-in-depth;
   the real boundary is an OS mechanism (per ADR-011's recommended direction).

## Architecture

The model runs **outside** the sandbox. The sandbox executes only read-only
log/system commands, which need neither GPU nor network. This sidesteps the
GPU-passthrough wrinkle ADR-011 flags for worker models that run inference inside
the boundary — here, inference (`llm_engines` → qwen3) stays on the host and only
the inspection commands are confined.

```
host (untrusted target)                 sandbox (rootless Podman)
  /var/log, journal  ──ro mount──▶  [ read-only command exec ]
                                          │ stdout/stderr
                                          ▼
  llm_engines (qwen3:27b) ◀──── triaged / observed output
        │
        ▼
  interpretation ──▶ engram (session memory) ──▶ llm_inspector (audit trace)
```

## Phased build plan

### Phase 0 — Sandbox spine (no LLM) — **committed**
Prove the isolation boundary works empty. A function that starts a locked-down
container, runs one fixed read-only command against host logs, captures output,
tears the container down.

- Runtime: rootless Podman (no root daemon; stronger posture for a security tool;
  clean on Ubuntu 24.04). Docker acceptable as fallback.
- Flags: `--network none`, `--read-only` rootfs, `--cap-drop ALL`,
  `--security-opt no-new-privileges`, non-root user, `--memory`/`--cpus`/`--pids-limit`,
  `--rm`.
- Mount: `/var/log:ro` directly to start. Tighter alternative (deferred):
  host exports `journalctl` to a staging dir, sandbox sees only the export.
- **Validates:** ADR-011 filesystem + process boundaries in their simplest form.
- **Test:** deterministic; assert command runs, output captured, no write path,
  container removed.

### Phase 1 — Deterministic triage (no LLM) — **committed**
Reduce log volume before any model sees it. Parse, deduplicate (collapse
"repeated N×" to one fact), severity-filter, count, flag known-bad patterns
(failed sudo, OOM kills, disk errors, unexpected listeners, auth anomalies).
Output: a structured salient-events summary.

- Most of the real engineering lives here; all standard Python.
- The reduction stage's blind spots become the system's blind spots — what it
  discards as noise never reaches the model. Document what it filters.
- **Test:** fixture log files; no model needed.

### Phase 2 — LLM interpretation (no code generation) — **committed**
Hand the Phase 1 summary to qwen3:27b via `llm_engines`. Single-shot
interpretation: correlation across sources, plain-language explanation,
risk-ordered prioritization.

- The LLM reads structured output only. It never touches the sandbox and never
  generates code. This is a usable, fully safe stopping point.
- **Test:** stub engine for unit tests (pattern exists in `language_tutor`);
  real model for integration.

> **Decision gate after Phase 2.** Phases 0–2 deliver a working tool with zero
> code-generation risk. Evaluate real output before committing to Phase 3 and the
> RLM-vs-allowlist decision below.

### Phase 3 — RLM exploration (gated)
Let the LLM write follow-up read-only queries that execute in the Phase 0 sandbox
("auth failures cluster on one IP → pull everything from that IP"). Bounded
iteration count.

- First point a generated command actually runs; the sandbox earns its keep here.
- Forces the **RLM vs allowlist** decision (see below). Defer until Phase 2 output
  is in hand.

### Phase 4 — Memory (gated)
`engram` so user judgments ("the Bluetooth errors are expected, ignore them")
persist across sessions.

- Expect the documented contradiction-bleed limitation (~18% under stress,
  `pattern_only=True`) to surface when a correction is re-flagged next session.
  This is the place to evaluate whether `pattern_only=False` (Gemma extractor) is
  warranted — recorded as its own ADR if so.
- Sensitive log content (auth data, key material) must stay local; never route it
  to a cloud judge. Reuse the `_sanitise_for_cloud()` posture from `llm_engines`.

### Phase 5 — Accountability trace (gated)
`llm_inspector` records every command run, every observation, every conclusion.
For a system that touches the computer, this is the audit record, not a debug aid.

## Key trade-offs

| Decision | Options | Resolution |
|---|---|---|
| Sandbox mount scope | direct `/var/log:ro` vs host-export staging dir | Start direct; staging is a Phase 0+ refinement |
| Code execution model | full RLM (arbitrary read-only code) vs allowlist (fixed parameterized tools) | **Deferred to Phase 3**, decided with triage output in hand |
| Isolation vs reach | tight mounts (safe, blind to the unexpected) vs broader read (capable, harder to reason about) | Start tight; the security use case eventually pulls toward broader read — revisit per run |
| Memory extraction | `pattern_only=True` (lightweight) vs `False` (Gemma, semantic contradiction) | Default lightweight; escalate only if Phase 4 shows contradiction bleed hurts |

## Package placement & ADR relationship

The sandbox built in Phase 0 is the **first real implementation of ADR-011**
(currently Proposed). This project is its forcing function and will move ADR-011
toward Accepted by revealing which boundary bites first.

Keep the sandbox and agent loop **project-local** initially. They graduate into
`agent_lib` only when a second consumer needs them (co-evolution rule) — do not
build the shared isolation library on spec. When extracted, the sandbox becomes
the enforced backbone of `WorkspacePolicy`'s process/network fields described in
ADR-011's consequences.

## Backup boundary (precondition, already in place)

The recovery path sits outside the blast radius on the assumption the sandbox can
fail. Current state: repo on GitHub plus a manual copy on an older machine that is
normally powered off (a power-state air gap; no standing credential or route from
the workstation). Sufficient for the read-only phases. Revisit toward an automated
pull-based scheme (old machine wakes on a timer, pulls, suspends; never push from
the workstation) before any action-taking helper graduates from this project.

## Open questions (resolve per run)

- Which boundary bites first in practice — likely process or filesystem — and
  therefore which to harden first beyond the Phase 0 baseline.
- Whether journalctl-in-container friction pushes Phase 0 to the host-export
  pattern sooner than planned.
- Whether the Phase 1 triage filter set is the right starting allowlist of
  "known-bad" patterns for a security-oriented first pass.

## Non-goals

- No remediation or write actions in this project. The moment that changes, the
  propose → confirm → execute protocol and the backup automation above become
  hard prerequisites, not options.
- No reliance on the model as a log parser. Parsing and reduction are
  deterministic; the model interprets, it does not extract structure from raw logs.
