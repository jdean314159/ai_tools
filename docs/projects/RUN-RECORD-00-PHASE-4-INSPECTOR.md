# RUN-RECORD-00 Phase 4 — Inspector consumption slice

**Status:** Complete, 2026-08-13.
**Scope:** Library/CLI loading, kind-specific summaries, unsupported-version
behavior, and conservative common comparison. No UI or producer migration.

## Result

`llm_inspector` can now load unified run-artifact JSON through
`llm_harness_core`, expose envelope metadata, and dispatch supported bodies to
separate generation and agent-run summarizers. It does not convert artifacts
into inspector `Trace` objects and does not flatten distinct bodies into one
report shape.

Supported contracts:

- `generation`, body version 1;
- `agent_run`, body version 1, `agent_lib.nav` profile version 1;
- `agent_run`, body version 1, `agent_lib.asc` profile version 1.

Unknown body/profile versions remain envelope-readable. The Inspector reports
them as unsupported, returns no body summary, and labels body-dependent privacy
claims unvalidated.

## Public surface

Library entry points:

- `inspect_artifact()` / `inspect_artifact_file()`;
- `compare_artifacts()` / `compare_artifact_files()`;
- dictionary conversions and text renderers for inspection/comparison output.

CLI entry points:

```text
llm-inspect artifact show RECORD [--format text|json]
llm-inspect artifact compare LEFT RIGHT [--format text|json]
```

The CLI was exercised against the Phase 3 privacy-safe live Ollama artifact.
It surfaced the supported generation summary and all nine declared omissions.

## Summaries

Common output includes:

- record identity, kind/profile, lifecycle, and versions;
- actors and semantic relationships;
- privacy categories, sensitivity, validation status, and scope;
- omissions and capability claims; and
- execution-environment declarations.

Generation summaries expose outcome, finish reason, requested/reported model
labels, backend, usage, output presence, tool-call count, and whether structured
output was requested.

Agent summaries expose profile, task identity, status/termination, elapsed
time, step count, final-output presence, evaluation presence, and model-role
names. Trajectory content, prompts, outputs, reasoning, and raw payloads are not
printed by the summary.

## Comparison boundary

Comparison is intentionally limited to defensible common facts: kind/body
contract, lifecycle, declared sensitivity, and reported model/backend labels.

Matching requested/reported labels produce `model_labels_equal: true` but
always produce:

```text
model_identity_equal: not_determined
```

The output explains that digest, quantization, runtime, tokenizer, and template
facts are required for a stronger conclusion. Cross-kind comparisons remain
common-facts-only.

## Fixtures and validation

Tests cover:

- generation and agent dispatch to different summaries;
- unsupported profile behavior;
- unvalidated privacy and omission visibility;
- matching-label comparison without identity overclaim;
- cross-kind comparison;
- text rendering and CLI JSON/text paths; and
- real MockEngine, NAV-v1, and ASC adapter integration.

Validation:

```text
focused Inspector artifact/public API:       10 passed
cross-package artifact integration:           3 passed
root public/import plus artifact tests:       16 passed
Inspector suite excluding known golden:      58 passed
```

The complete Inspector suite has one unrelated environment-sensitive failure:
`test_engram_trace_sections_order_golden` expects token count 9, while the
optional-`tiktoken`-absent word-count fallback produces 7. The artifact tests do
not touch Engram trace construction or token accounting.

## Gate assessment

The slice gate is satisfied: Inspector loads and explains generation, NAV, and
ASC artifacts while preserving kind-specific semantics and clearly surfacing
unsupported versions, omitted telemetry, and unvalidated legacy privacy.

UI work, campaign/experiment records, RAG traces, photo artifacts, course
fixtures, bundle storage, and redaction tooling remain deferred.
