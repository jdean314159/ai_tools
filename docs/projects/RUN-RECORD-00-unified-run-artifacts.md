# RUN-RECORD-00 — Unified, versioned run artifacts

**Status:** Phases 0–7 complete under ADR-021 and ADR-022.
**Last updated:** 2026-08-13.

## Outcome

`ai_tools` now has a dependency-free, cross-package artifact surface rather
than one giant schema or a greenfield replacement for existing records.
`llm_harness_core` owns the envelope, serialization, validation, and local
bundle mechanics. Producer packages own body construction and legacy adapters;
`llm_inspector` owns interpretation and comparison.

The implementation supports three distinct body kinds:

- `generation`: normalized request/response, outcome, model/backend facts,
  usage, omissions, and field provenance;
- `agent_run`: task, trajectory, termination, model roles, evaluation, and
  producer-profile data; and
- `experiment`: campaign configuration, compact items, aggregate results,
  decisions, and references to separately published child runs.

The common envelope carries identity, lifecycle, versions, relationships,
actors, time, privacy declarations, omissions, capabilities, attachments, and
execution-environment facts. It is materially richer than either legacy NAV or
ASC headers, but both adapters populate it directly without a supporting
metadata subsystem or new runtime dependency.

## Corrected project premise

This project was never greenfield. NAV already emitted schema-v1
`run-record.json` through `agent_lib.eval.repo_navigation.render_run_record()`
and the counterfactual finalizer consumed that shape. ASC, generation engines,
Inspector traces, and evaluation campaigns used other representations. The
project consolidated artifact boundaries while keeping NAV-v1 authoritative
and readable by its existing consumers.

Programs produce artifacts; artifacts are not commands. Replay and
re-execution are explicit capability claims, never inferred from record kind.

## Completed phases

| Phase | Result | Report |
|---|---|---|
| 0 | Producer/consumer inventory and multi-axis field crosswalk | `RUN-RECORD-00-PHASE-0-INVENTORY.md` |
| 1 | Envelope semantics and ownership decisions | `adr/ADR-021-run-artifact-envelope-semantics.md`, `adr/ADR-022-run-artifact-ownership-and-public-api.md` |
| 2 | Dependency-free core plus lossless NAV-v1 and ASC agent adapters | `RUN-RECORD-00-PHASE-2-COMPATIBILITY.md` |
| 3 | Generation recorder, cross-kind proof, MockEngine fixtures, and live Ollama acceptance | `RUN-RECORD-00-PHASE-3-VALIDATION.md` |
| 4 | Inspector loading, kind-specific summaries, unsupported-version behavior, and conservative comparison | `RUN-RECORD-00-PHASE-4-INSPECTOR.md` |
| 5 | Shared experiment body and ASC/NAV campaign adapters | `RUN-RECORD-00-PHASE-5-EXPERIMENTS.md` |
| 6 | Exact-byte local bundles, confined resolution, tamper detection, and child-run packaging | `RUN-RECORD-00-PHASE-6-BUNDLES.md` |
| 7 | Privacy-safe offline course fixture and resolved-child Inspector diagnosis | `RUN-RECORD-00-PHASE-7-COURSE-FIXTURE.md` |

## Settled decisions

- Ownership: common contracts and generic IO live in `llm_harness_core`;
  producer semantics do not.
- Shape: one common envelope with separate generation, agent-run, and
  experiment bodies; no sparse union body.
- Identity: published artifacts are immutable snapshots. Adaptation and adding
  bundle declarations create new identities with `derived_from` relationships.
- Generation/agent composition: semantic relationships identify membership;
  separately addressable bytes use attachments. A relationship does not
  manufacture a missing attachment.
- Versioning: envelope, body, and optional profile versions are distinct.
- Replay: structured capability claims specify requirements, execution mode,
  effects, determinism evidence, and implementation version. NAV
  counterfactual finalization is a conditional live-model call, not structural
  replay.
- Privacy: artifacts declare content, transformations, reference sensitivity,
  and scoped validation evidence. Export authorization remains downstream.
- Bundles: SHA-256 covers exact stored bytes. Resolution is reader-computed and
  never persisted. Local paths are confined and omitted from Inspector output.
- Model identity: labels are comparable facts but never proof of identical
  model artifacts.

## Compatibility and scope boundaries

- NAV-v1 and ASC legacy records remain authoritative; adapters do not rewrite
  source files.
- Unknown envelope versions fail. Unknown body/profile versions retain common
  envelope visibility but are not interpreted.
- Raw provider payloads and error text remain default-off for generation
  recording.
- ASC timeout rows remain experiment items, not fabricated standalone runs.
- Local bundles are directories, not zip/tar archives, signed exports, remote
  resolver registries, encrypted containers, or redaction machinery.
- Photo, RAG, UI, and broad course migrations were not pulled into this work.

## Remaining decisions

- Model digest scope when a backend actually exposes one: model file,
  provider-reported manifest, deployment composite, or another typed scope.
- The minimum portable execution-environment facts for backends that expose
  tokenizer/template/runtime identity without leaking host-specific details.
- Whether a concrete exchange boundary requires signing, encryption, export
  policy, archive packaging, or remote attachment resolution.
- Which additional concrete consumer, if any, should validate the format after
  the successful single-fixture course pilot.

## Current action

The bounded course-fixture pilot passes. Select the next project or capability
from a concrete consumer need. Do not reopen
the settled ownership, layering, identity, replay, or local-bundle decisions
without a forcing failure from a real producer or consumer.
