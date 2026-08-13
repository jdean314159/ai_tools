# ADR-022 — Run-Artifact Ownership and Public API

**Status:** Accepted for RUN-RECORD-00 Phase 2.
**Date:** 2026-08-13.
**Depends on:** ADR-021 and
[`docs/projects/RUN-RECORD-00-PHASE-0-INVENTORY.md`](../docs/projects/RUN-RECORD-00-PHASE-0-INVENTORY.md).

## Context

The common artifact envelope must be readable without importing a producer.
Current dependencies point from `llm_harness_core` to no other runtime package,
from `llm_engines` and `llm_inspector` to core, and from `agent_lib` to all
three. NAV and ASC formats are agent-specific; generation contracts belong to
`llm_engines`; inspection behavior belongs to `llm_inspector`.

ADR-006 already assigns dependency-light cross-package schemas to
`llm_harness_core`. Creating another package would duplicate that role without
a forcing dependency or release boundary.

## Decision

`llm_harness_core` owns dependency-free artifact primitives and generic JSON
reading, validation, and envelope summarization. The Phase 2 public surface is
dataclass-based and uses only the standard library. It does not import producer
bodies or Pydantic.

Producer packages own adapters and profile-specific interpretation:

- `agent_lib` owns NAV-v1 and ASC mapping into the shared `agent_run` body;
- a later `llm_engines` phase will own generation recording;
- `llm_inspector` may consume the core reader later but does not own runtime
  artifact contracts.

The common reader dispatches by envelope and body/profile versions. It exposes
common metadata for an unknown body version but reports that body as
unsupported; it does not homogenize producer-specific bodies.

Legacy artifacts remain authoritative and unchanged. Phase 2 adapters read
them into new immutable representations; existing NAV consumers continue to
read NAV-v1 directly. No producer migration or file-shape rewrite is implied.

The initial public API includes:

- immutable envelope and declaration types;
- a generic `RunArtifact` carrying an opaque mapping body;
- parse/load/dump/validate helpers;
- generic summary output;
- agent-package adapter functions for NAV-v1 and ASC records.

JSON Schema generation, Pydantic models, inspector integration, generation
recording, and automatic redaction are not part of Phase 2.

## Compatibility policy

- Envelope version 1 is accepted; unknown envelope versions fail validation
  because even common metadata cannot be trusted.
- Unknown kind body/profile versions retain readable envelope metadata and are
  reported as unsupported by a dispatching consumer.
- Unknown JSON fields are preserved in opaque bodies and ignored in envelope
  parsing unless they contradict required invariants.
- Adapter-derived records identify the adapter and source digest and use a
  deterministic adapter identity so repeated adaptation of identical bytes is
  stable.
- Privacy defaults are conservative: legacy adapters declare unknown content
  categories/sensitivity and no validation rather than inferring export safety.

## Consequences

The core package gains schemas and serialization behavior but no heavy runtime
dependency. Producer knowledge stays above the dependency boundary. The first
slice proves two agent producers, not cross-kind generality; Phase 3 remains
responsible for the generation proof.
