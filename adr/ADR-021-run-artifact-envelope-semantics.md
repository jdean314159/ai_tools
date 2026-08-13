# ADR-021 — Run-Artifact Envelope and Semantics

**Status:** Accepted. The RUN-RECORD-00 Phase 2 NAV/ASC compatibility slice
validated these distinctions without requiring a new package or producer
rewrite. Later phases may refine field representation, but must not collapse
the semantics without revising this ADR.
**Date:** 2026-08-13.
**Scope:** Artifact semantics only: kinds, identity and lifecycle, lineage,
versioning, attachments, provenance, availability, time, privacy, model and
environment declarations, and executable capability claims. Package ownership
and public API are deferred to ADR 1B.
**Evidence:**
[`docs/projects/RUN-RECORD-00-PHASE-0-INVENTORY.md`](../docs/projects/RUN-RECORD-00-PHASE-0-INVENTORY.md).

## Decision hypothesis

A small common envelope can support discovery, identity, lineage, privacy
decisions, version dispatch, validation, and basic comparison across generation
and agent artifacts while preserving kind-specific semantics and avoiding false
replay or reproducibility claims.

The current artifacts do not satisfy that envelope. Privacy declaration is
absent from every representative format. Phase 2 tests whether NAV and ASC can
populate the design without disproportionate adapter machinery; Phase 3 tests
the cross-kind claim with generation artifacts. Envelope size remains a
falsifiable implementation concern, not an assertion made by this ADR.

## Semantic layers

The artifact model keeps four concerns distinct:

```text
semantic record kind
    ├── relationships and immutable identity
    ├── kind-specific body and optional profile extension
    ├── separately addressable attachments and bundle declarations
    └── declarations: provenance, availability, time, privacy,
        model/environment facts, and executable capabilities
```

### Kind, profile, and versions

`kind` is a small controlled set initially containing `agent_run`, `generation`,
and `experiment`. `profile` is an optional namespaced extension identifier
within a kind, such as a NAV or ASC profile; it is not a global envelope enum.

Version fields have separate authorities:

- `envelope_schema_version` versions the common wrapper;
- `body_version` versions the shared kind contract, such as `agent_run`;
- `profile_version` versions governed profile additions and is absent when a
  profile adds no governed structure.

This prevents NAV and ASC from assigning incompatible meanings to the same
agent-body version. Unknown body or profile versions do not prevent a reader
from exposing declared envelope metadata, but the reader must label the
unrecognized body and any body-dependent declarations as unvalidated.

### Lifecycle and identity

Writing bytes does not by itself publish a final record. Artifact lifecycle is
explicit:

- `checkpoint` is a durable, replaceable progress representation;
- `final` is an immutable published snapshot;
- `aborted` is an immutable terminal snapshot of incomplete work.

This distinction reflects current producers: individual NAV and completed ASC
records are written once, while ASC `live_probe_results.json` and NAV campaign
`pairs.json` are durable aggregates rewritten as work completes.

Each immutable snapshot has a stable `record_id`; copying preserves it.
Continuing, retrying, adapting, or finalizing a checkpoint produces a new
snapshot identity and a typed semantic relationship to the source. A producer
may additionally retain a stable logical execution or campaign ID across
checkpoints. UUID selection is an implementation detail. Digests establish
byte integrity, not record identity.

Adaptation is idempotent only when the adapter has a documented deterministic
identity rule. Otherwise repeated adaptations are distinct artifacts with the
same source-digest relationship; consumers must not silently infer that they
are identical.

Relationships are semantic pointers only:

```text
relation_type, target_kind, target_id
```

Initial relationship meanings include `derived_from`, `continues`, `retries`,
and experiment membership. Storage information does not live in relationships.

### Kind-specific bodies

Generation, agent-run, and experiment bodies remain distinct contracts. Profile
extensions contain producer-specific fields without redefining the shared body.
NAV steps remain inline during Phase 2 because the counterfactual finalizer and
both loop-guard replay scripts directly consume the current flat step and usage
shape. Compatibility adapters must preserve that behavior.

Ordinary inline body data, including scores and steps, is not an attachment.

### Attachments and resolution

Attachments are separately addressable material, such as a raw provider
payload or environment manifest. Durable declarations and reader observations
are distinct:

```text
attachment:
  attachment_id
  logical_role
  locator:
    type: bundled-file | content-uri | resolver-key | digest-only
    value: required except for digest-only
    digest
    digest_algorithm
  declared_inclusion: bundled | detached
  requirement: required | optional

reader result:
  resolution: resolved | unresolved | digest_mismatch
```

Bundle file locators are relative to the bundle. Raw absolute paths are not
portable locators and may themselves disclose sensitive information. Locator
and digest values are privacy-classified metadata. Phase 2 selects the digest
algorithm and canonical byte scope. If the recorder never had the bytes needed
for a digest, the item is a relationship or declared external dependency, not
an attachment satisfying this contract.

### Provenance, method, and availability

Actor identity and epistemic method are separate. Actor entries identify the
original producer, recorder, adapter, and—where applicable—a user. Section or
field provenance refers to an actor entry rather than an unqualified role.

Method applies only to observations and derived claims for which it is
meaningful:

```text
measured | estimated | derived_post_hoc | declared | copied
```

Availability is represented by omissions because a missing field cannot label
itself. Each omission records a field path and one of:

```text
not_reported_by_backend | redacted | not_applicable |
absent_in_source_format | capture_failed | intentionally_not_recorded |
unsupported_by_recorder
```

The serialization contract will select the field-path syntax. Incomplete or
estimated telemetry summaries are computed by readers rather than persisted as
redundant booleans.

At least one recorder or adapter identity is required. A legacy adapter need
not invent an original producer it cannot establish.

### Time

Execution and artifact times are not interchangeable. The declaration may
contain `execution_started_at`, `execution_finished_at`,
`artifact_created_at`, and `adapted_at`, each with source and precision.
Artifact creation or adaptation time is required. Execution times must contain
a value, explicit `unknown`, or `not_applicable`; adapters must not promote
filesystem modification or adaptation time to execution time.

### Privacy declarations

The record supplies evidence for policy; it never declares itself exportable.
The privacy declaration distinguishes:

- declared content categories using an open vocabulary;
- transformations, with policy identity and version;
- sensitivity of bytes in the envelope/body;
- sensitivity of each visible attachment reference; and
- scoped validation evidence.

Validation evidence states status, validator identity, policy identity and
version, validation time, and the exact checks or byte scope covered. An
unsupported body version invalidates only checks that required understanding
that body. Digest and transformation-log checks may remain valid independently.
Privacy declarations, paths, relationship identifiers, and digests can
themselves be sensitive and must be handled accordingly. Export authorization
remains a downstream policy decision.

### Model and execution-environment facts

Model identity is a set of independently sourced facts, not a label equality
claim. Candidate facts include requested and reported labels, a typed digest
with algorithm and scope, and quantization. Runtime build and available
hardware facts belong to a separate execution-environment declaration. Missing
facts remain explicitly unavailable; label equality alone never proves model
identity.

### Executable capability claims

Reading and inspecting a record is not replay and requires no capability
claim. Executable claims are structured and include:

```text
operation
requirements:
  - type: attachment | body_path | external_service |
          implementation | configuration
    ref: ...
execution_mode: recorded | local_compute | live_external
effect_class: none | read_only | state_changing | unknown
determinism:
  claim: not_claimed | deterministic | best_effort
  conditions: [...]
  evidence_basis: declared | statically_validated | exercised
implementation_version
```

The requirements distinguish incomplete bundles from unavailable live
services. External interaction and state-changing effects are separate safety
facts. Determinism claims are meaningful only with their conditions,
implementation version, and evidence basis.

The grounded NAV operation is `counterfactual_finalization`: it performs a
live model invocation when its token-budget guard permits and otherwise emits
`budget_unavailable`. It therefore uses `execution_mode: live_external`, makes
no determinism claim, and requires stored steps and usage plus the external
question/answer-key material, model service, prompt implementation, and budget
configuration. Its effect class remains `unknown` unless the backend contract
establishes a stronger guarantee.

## Compatibility forcing cases

Phase 2 must exercise at least these cases:

1. A NAV-v1 final snapshot remains usable by the counterfactual finalizer and
   both loop-guard replay scripts.
2. A required bundled attachment that cannot be resolved produces an explicit
   unresolved or digest-mismatch reader result.
3. An intentionally detached optional attachment is not reported as corrupt.
4. An unknown body/profile version still exposes declared envelope identity,
   lineage, and privacy metadata while labeling body-dependent claims
   unvalidated.
5. Missing backend telemetry is recorded as unavailable, never measured zero.
6. An ASC standalone record and its campaign representation are either the
   same referenced record identity or explicitly different summary and record
   objects. An embedded summary is not silently treated as a complete record.
7. Adapting a legacy artifact records adapter identity, source digest, and an
   explicit derivation relationship without fabricating original execution
   facts.

## Consequences and deferred work

The envelope is richer than any current format. Phase 2 must report adapter
population burden and may simplify representation if all distinctions above
remain observable.

Deferred:

- package ownership and public API (ADR 1B);
- concrete Python types, JSON Schema, canonical serialization, digest
  algorithm, and field-path syntax (Phase 2);
- the complete capability-operation vocabulary;
- generation recording and live-engine acceptance (Phase 3);
- inspector comparison, broader campaigns, RAG, photo artifacts, and course
  fixtures (Phase 4+).
