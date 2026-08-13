# RUN-RECORD-00 — Unified, versioned run artifacts

**Status:** Phases 0–5 complete. Accepted ADR-021 semantics and ADR-022
ownership/public API govern the implementation. The common envelope has passed
the NAV/ASC compatibility gate, generation/agent cross-kind gate, first
Inspector consumption gate, and ASC/NAV experiment-campaign gate.
**Prepared:** 2026-08-12

## Purpose

Define a stable public artifact surface for recording, comparing, and replaying
LLM work across `ai_tools`. This is not a proposal for one enormous object that
forces a single generation, an agent trajectory, and a multi-item experiment
into the same sparse schema. The likely shape is a small common envelope plus
typed record kinds and adapters.

## Correction to the project premise

This is not greenfield work. `agent_lib` already has a substantial navigation
run-record prototype:

- `agent_lib/src/agent_lib/eval/repo_navigation.py:1672` defines
  `render_run_record()` and emits schema version 1;
- that record contains configuration, environment identity, repository
  digests, complete agent steps, planner usage, tool telemetry, and scores
  (`repo_navigation.py:1682-1713`);
- `agent_lib/examples/repo_navigation_eval.py:266-277` writes
  `environment-manifest.json` and `run-record.json`;
- `agent_lib/examples/nav_counterfactual_finalize.py:178-202` consumes a stored
  run record for a counterfactual evaluation.

There are also incompatible specialized artifacts:

- `examples/asc_probe/live_probe.py:420-452` writes an ASC-specific
  `record.json`;
- `llm_engines/src/llm_engines/contracts/engine.py:250-279` defines the
  request/response contract for a single generation;
- `llm_inspector/src/llm_inspector/core/trace.py:96-160` defines inspector
  trace objects over the shared event type in
  `llm_harness_core/src/llm_harness_core/events.py:10-22`;
- evaluation campaigns and application-specific harnesses write additional
  JSON, JSONL, and CSV formats.

The problem is therefore incompatible artifact boundaries, not absence of run
records.

## Goals

1. Give new producers one documented, versioned public recording surface.
2. Preserve enough provenance to compare runs and determine what configuration,
   context, model, code, and environment produced an outcome.
3. Keep existing NAV artifacts readable and replayable.
4. Allow inspector tooling to load supported records without knowing each
   producer's private schema.
5. Make redaction and raw-provider-payload handling explicit rather than
   accidentally persisting sensitive data.

## Non-goals for the first project

- Rewriting every producer at once.
- Replacing `GenerationRequest`, `GenerationResponse`, `TraceEvent`, or
  `AgentRun` as runtime contracts.
- Treating a record as an executable command. Programs produce records;
  validators, viewers, and replay adapters consume them.
- Promising deterministic replay when a backend, model, seed, or environment
  cannot provide it.
- Folding large per-item datasets such as photo classification into one giant
  agent-style trajectory.

## Accepted semantic direction

ADR-021 accepts this layered direction, validated by the narrow Phase 2
compatibility slice:

- a common envelope: schema identity/version, record ID and kind, timestamps,
  producer identity/version, parent/child links, environment/provenance,
  privacy/redaction declaration, and extension fields;
- a generation record: request, normalized response, model/backend identity,
  usage, timings, cache/optimization data, and optional protected raw payload;
- an agent-run record: task, steps, actions, observations, tool calls/results,
  traces, cumulative budgets, termination, and final output;
- an experiment record: configuration and immutable manifest plus references
  to child generation/agent/item records, metrics, scorer identity, and frozen
  decision protocol.

The semantic distinctions are accepted; concrete types, serialization, and
package ownership remain to be decided and tested.

## Phase 0 — inventory and samples

Before drafting field-level contracts:

1. Catalogue every current producer and consumer of durable run/evaluation
   artifacts.
2. Select committed or synthetic, privacy-safe examples for at least:
   - one `GenerationResponse`-level call;
   - one NAV `run-record.json`;
   - one ASC `record.json`;
   - one inspector `Trace`;
   - one multi-run campaign summary.
3. Produce a field crosswalk: shared concepts, producer-only data, missing
   provenance, sensitive/raw fields, and replay dependencies.
4. State which artifacts are records, manifests, traces, scores, or datasets;
   do not rename all of them “RunRecord.”

**Gate:** inventory and crosswalk reviewed against real producers and consumers.

## Phase 1 — ADR and compatibility contract

Write an ADR that decides:

- record kinds and ownership package;
- schema identifier and version-evolution rules;
- JSON serialization and validation rules;
- nesting versus references between records;
- required provenance and reproducibility claims;
- redaction, raw payload, path, prompt, and evidence policy;
- adapter and deprecation strategy;
- forward/backward compatibility and unknown-field behavior.

The ADR must explicitly compare extending the NAV schema with introducing a
common envelope. It must not assume a new package is necessary.

**Gate:** representative existing artifacts can be losslessly mapped or their
intentional losses are enumerated and accepted.

## Phase 2 — narrow implementation

Only after the ADR:

1. Implement schema models and JSON validation in the selected existing core
   package unless the ADR proves a new package boundary is needed.
2. Add an adapter for NAV schema v1 and preserve the counterfactual consumer.
3. Convert one second producer (recommended: ASC) to prove the surface is not
   NAV-specific.
4. Add a CLI validator/summary command; do not call the record itself a CLI.
5. Add inspector loading only after the first two producers validate.

**Gate:** golden round trips, NAV replay compatibility, unknown-version
failure, redaction tests, and two producer adapters pass.

## Open decisions

- Whether generation records are embedded in agent steps or stored as child
  records referenced by ID.
- Whether the owning package is `llm_harness_core`, `llm_inspector`, or an
  existing package-specific surface. Dependency direction must decide this,
  not naming preference.
- Minimum environment capture that is useful without making records
  host-specific or leaking paths.
- Whether raw prompts, evidence text, and provider payloads are default-off,
  redacted, encrypted, or stored in a separate restricted artifact.
- Definition of “replay”: structural replay, tool-trajectory replay,
  counterfactual continuation, or model re-execution.

## Current action

Phase 5 experiment/campaign records are complete. Select the next bounded
capability: portable attachment/bundle resolution is the leading architectural
follow-up if copied experiment artifacts must carry their child records.
Alternatively, validate a separate producer or course fixture without bundling
it into this slice. Do not infer authorization for UI, RAG, photo, or broad
course migration from Phase 5 completion.
