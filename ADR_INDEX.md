# ai_tools — ADR Index

<!-- AI_TOOLS_CLEANUP_CHECKPOINT_START -->
## Current cleanup checkpoint

Packaging/import/test stabilization is green.

Latest broad package-local gate:

    833 passed, 37 skipped in 34.90s

Validated under:

    unset PYTHONPATH
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    PYTHONDONTWRITEBYTECODE=1
    -W error

Completed since the previous transfer update:

- `llm_inspector_ui` import/namespace blocker resolved.
- Editable-install model validated from outside the repo root.
- Package-local import bootstraps removed.
- Import provenance is guarded by `tests/test_import_provenance.py`.
- Root `conftest.py` remains as the single centralized transitional pytest bootstrap.
- Publication hygiene checker now rejects transient artifacts such as `.pytest_cache/`, `*.egg-info/`, `*.bak`, `*.orig`, `*.rej`, `*.patch`, `local_artifacts/`, `test_reports/`, and `test_survey_results/`.
- Transient hygiene artifacts were removed.
- `engram` embedding compatibility modules now behave as facade re-exports over `engram`.
- `llm_inspector` normalizes delegated `engram` trace events back to the `engram` adapter boundary while preserving upstream provenance.

Current policy:

- Do not reintroduce package-local `sys.path`, `PYTHONPATH`, `sys.modules`, manual package loaders, or import reload logic.
- Keep root `conftest.py` as the permanent anchoring guard (deliberate compensating control; ADR-008 decision closed — do not remove).
- Keep source/layout changes in small, separately validated commits.

ADR-014 complete: `llm_engines` converted to `src/` layout; editable install validated.
<!-- AI_TOOLS_CLEANUP_CHECKPOINT_END -->

## Purpose

This file maps architectural decisions across the `ai_tools` monorepo.

Use it to answer:

- which decisions are already settled
- where the authoritative decision record lives
- which areas still need explicit ADR coverage

`docs/design/VISION.md` is the architecture baseline. `ADR_INDEX.md` is the decision map.

## Existing ADRs

### ADR-001 — Engine Capability Model

- File: `adr/ADR-001-engine-capability-model.md`
- Status: Accepted
- Scope: `llm_engines`
- Decision: engine capabilities should be explicit rather than assumed.

### ADR-002 — Engine Response Schema

- File: `adr/ADR-002-engine-response-schema.md`
- Status: Accepted
- Scope: `llm_engines`, downstream consumers
- Decision: engine calls should return structured responses rather than plain strings only.

### ADR-004 — Engram Retrieval Policy

- File: `adr/ADR-004-engram-retrieval-policy.md`
- Status: Accepted
- Scope: `engram`
- Decision: retrieval across memory layers needs explicit policy.

### ADR-005 — Persistence & Migration

- File: `adr/ADR-005-persistence-migration.md`
- Status: Accepted
- Scope: `engram`
- Decision: persistence strategy should reflect backend realities.

### ADR-006 — Interoperability Core for the LLM Harness Suite

- File: `adr/ADR-006-interoperability-core.md`
- Status: Accepted
- Scope: suite-wide
- Decision: use a dependency-light shared core, `llm_harness_core`, for cross-package schemas.

### ADR-007 — `engram_lite` as a Facade Over `engram` (SUPERSEDED)

- File: `adr/ADR-007-engram-lite-as-engram-facade.md`
- Status: **Superseded by ADR-009**
- Scope: historical only
- Summary: ADR-009 dissolved engram_lite and renamed the standalone implementation
  to `engram`. The facade question is resolved; do not act on this ADR.

### ADR-008 — Monorepo Packaging and Import Policy

- File: `adr/ADR-008-monorepo-packaging-policy.md`
- Status: Accepted
- Scope: suite-wide
- Decision: standardize package layout and validation around src layout, editable installs, and minimal path shims.

## Missing number

There is currently no `ADR-003` in the repo snapshot. Do not assume one exists unless it is actually added.

## Settled decisions

Treat these as settled unless a new ADR explicitly reverses them:

1. Engine capabilities are explicit.
2. Engine responses are structured.
3. Engram retrieval policy is explicit.
4. Persistence strategy must match backend realities.
5. `llm_harness_core` is the shared interop layer.
6. `engram` is a standalone implementation (ADR-009); ADR-007 facade direction superseded.
7. Packaging/import behavior should be standardized rather than repaired with growing path hacks.

## ADRs that may still be needed

### Inspector / observability event taxonomy

Needed to define shared event categories, required fields, severity semantics, provenance, and compatibility policy.

### Package import side-effect policy

May be folded into ADR-008 or added later. Should define what may and may not happen at top-level import time.

## ADR-009 — Freeze engram, dissolve engram_lite, rename to engram
**File:** `adr/ADR-009-engram-freeze-and-rename.md`
**Status:** Accepted
**Summary:** Heavy engram archived at github.com/jdean314159/engram. Original
standalone engram_lite implementation restored and renamed to `engram`. ADR-007
superseded. engram_ui engine migration deferred to follow-on ADR.

## ADR-010 — Archive engram_ui, add chat panel to llm_inspector_ui
**File:** `adr/ADR-010-archive-engram-ui-add-chat-panel.md`
**Status:** Accepted
**Summary:** `engram_ui` deleted as redundant with `llm_inspector_ui`. Streamlit
dependency dropped from the active package set. No package broken as a result.

## ADR-011 — Agent execution isolation model
**File:** `adr/ADR-011-agent-execution-isolation.md`
**Status:** Proposed
**Summary:** Frames the filesystem/process/network/worktree boundary decisions
needed before serious `agent_lib` expansion. Recommends enforced (container,
network-default-deny) over advisory confinement. Left Proposed pending the first
real ASC-build run, per the co-evolution rule in AGENT_BUILD_NOTES.

## ADR-016 — Additive memory-layer extension seam
**File:** `adr/ADR-016-memory-layer-extension-seam.md`
**Status:** Accepted
**Summary:** Adds an optional `MemoryLayer` protocol and explicit registration
at Engram's observe, recall, prompt, and teardown seams. Existing memory layers
remain authoritative and unchanged; extension failures cannot break core flows.
NEURAL-02b records the default-off RTRL/TITANS adapter as the first
implementation, using intrinsic prediction error and a generic candidate
embedding resolver. NEURAL-07 records the failed output-path experiments and
isolates neural reranking, prompt guidance, and episode-importance influence
from default recall behavior.

## ADR-017 — Coordination permission model
**File:** `adr/ADR-017-coordination-permission-model.md`
**Status:** Accepted
**Summary:** Coordination routes by declared capability, scopes each session's tool grant,
and gives coordinator runtimes an explicit deny-all grant.

## ADR-018 — Unified path ownership
**File:** `adr/ADR-018-path-ownership-target-and-debt.md`
**Status:** Accepted; unification promoted
**Summary:** Manager-backed sessions use one atomic, enforced lease authority; reservations
are a derived human-readable view. The legacy mailbox fallback remains advisory-only.

## ADR-019 — Lease lifecycle: minimal recovery contract
**File:** `adr/ADR-019-lease-lifecycle-recovery-contract.md`
**Status:** Implemented (narrow v1: release lifecycle only)
**Summary:** ADR-018 promotion-trigger #3 fired in-tree: the FX-CONTENTION fixture
(`computer_helper` 7cb5192) deadlocks a legitimate contender because a held lease is never released.
v1 (Accepted) integrates explicit release into the lease lifecycle: `release_patch_lease` exists in
the manager but is unreachable from the loop and unobligated, so v1 makes it reachable, defines when
a no-op/failed holder releases, adds release ownership/idempotence, and stamps `released_at`. Gated
by FX-RELEASE (the deadlock completes). Explicitly NOT built: owner-death detection, PID tracking,
heartbeat, TTL, automatic reclaim, exclusive/shared. FX-CONTENTION had both workers live — it forced
the consequence of an unreleased lease, not a dead-owner detector — and the lease model carries only
a logical owner_id (no liveness signal; cross-process file-backed store), so reclaim is a
separately-designed capability with no forcing run yet. Owner-death is a recorded backlog trigger,
NOT an xfail test (an xfail would manufacture a speculative implementation obligation). TTL is
explicitly not a liveness stand-in. created_at persisted/displayed but unused for lifecycle.
Predicate D kept out of the evidence line (single-sourced from termination, Finding 1 /
SPEC-LIVE-01). OPCOM Lesson 1 is design input for a future reclaim build, not a spec to copy.

## ADR-020 — Data-only model & artifact loading
**File:** `adr/ADR-020-data-only-model-loading.md`
**Status:** Accepted (documents existing invariant + BM25 pickle-removal enforcement commit; no new subsystem)
**Summary:** Records the controls ai_tools already relies on against model-supply-chain
compromise, made explicit as invariants: (1) no in-process weight deserialization — model
access is HTTP to a local inference server (llama.cpp/Ollama/vLLM), weights deserialized by the
trusted engine not by ai_tools, so the process boundary is the control; (2) GGUF/safetensors
only, no pickle-format checkpoints; (3) no trust_remote_code (grep-verified in active Python paths); (4) no
pickle in data caches (BM25 cache converted to JSON, chroma.py dead import removed). Scopes the
concern into three layers — load-time compromise (controlled here), poisoned behavior (process
review loop), provenance/policy (institutional, not code). Explicitly out of scope: origin
allowlists, weight scanning, signature verification — no forcing exposure. Open follow-on:
agentic-execution boundary audit (expected no-gap given COORD-01 + ADR-017).

## ADR-021 — Run-artifact envelope and semantics
**File:** `adr/ADR-021-run-artifact-envelope-semantics.md`
**Status:** Accepted; validated by RUN-RECORD-00 Phase 2
**Summary:** Defines a small common envelope over distinct generation,
agent-run, and experiment bodies. Separates semantic kind from producer
profile, immutable snapshots from replaceable checkpoints, relationships from
attachments, body from profile versions, durable attachment declarations from
reader resolution, and provenance/privacy/capability claims from downstream
policy. ADR-022 resolves package ownership.

## ADR-022 — Run-artifact ownership and public API
**File:** `adr/ADR-022-run-artifact-ownership-and-public-api.md`
**Status:** Accepted for RUN-RECORD-00 Phase 2
**Summary:** Places dependency-free envelope types and generic JSON
read/validate/summary helpers in `llm_harness_core`, while producer packages
retain their adapters and profile semantics. Phase 2 adds NAV-v1 and ASC
adapters in `agent_lib` without rewriting either legacy artifact or its current
consumers.

## ADR-023 — Split repository licensing
**File:** `adr/ADR-023-split-repository-licensing.md`
**Status:** Accepted
**Summary:** Selects Apache-2.0 for reusable `ai_tools` infrastructure and
retains MIT for the extracted `llm-failure-lab` teaching repository. Records
the rejected single-license alternatives, keeps `THIRD_PARTY_NOTICES.md`
distinct from an Apache `NOTICE`, and records closure of the whole-tree
ownership audit.

## ADR-024 — Request-level thinking control
**File:** `adr/ADR-024-request-level-thinking-control.md`
**Status:** Accepted
**Summary:** Adds the three-state `GenerationRequest.thinking` preference:
inherit the server default, request thinking, or request suppression. vLLM maps
it to Qwen's request-level chat-template option, and tool loops preserve it.
Reasoning text remains transient and excluded from responses and memory.

## ADR-025 — Validated streamed tool-call events
**File:** `adr/ADR-025-validated-streamed-tool-calls.md`
**Status:** Accepted
**Summary:** Adds a separate async tool-streaming protocol with typed text,
complete-tool-call, and finish events. Provider argument fragments remain
internal until strict JSON parsing succeeds; incomplete or malformed calls
fail closed and never become executable events or replayable history.

## ADR-026 — Model characterization boundary
**File:** `adr/ADR-026-model-characterization-boundary.md`
**Status:** Accepted
**Summary:** Places version-2 fixed synthetic endpoint probes in `llm_engines`, keeps
`llm_inspector` inference-free, and records results through the shared
experiment envelope. Reports distinguish adapter declarations from observed
failures, retain tri-state thinking and bounded scalars, and omit raw prompts,
responses, host paths, endpoint URLs, secrets, and exception text.

## ADR-027 — Observable tool-decision probes
**File:** `adr/ADR-027-observable-tool-decision-probes.md`
**Status:** Accepted
**Summary:** Defines a version-2 fixed synthetic campaign for required tool use, relevant
tool choice, avoiding unnecessary tools, and typed arguments. Tools are not
executed, the requested thinking setting is retained, raw content is omitted,
and observed decisions are not presented as
access to hidden reasoning or general application reliability.

## ADR-028 — Request-level seed control
**File:** `adr/ADR-028-request-level-seed-control.md`
**Status:** Accepted
**Summary:** Adds a portable seed preference and separately records whether a
backend forwarded and received a successful response to it. Seed acceptance
does not upgrade best-effort generation into a determinism claim.

## ADR-029 — Multi-turn tool-recovery experiment
**File:** `adr/ADR-029-multi-turn-tool-recovery-experiment.md`
**Status:** Accepted
**Summary:** Defines a separate, privacy-bounded recovery profile for adverse
tool results, with a frozen evaluation split, baseline-headroom stop rule, and
predeclared improvement criteria before any live comparison.
