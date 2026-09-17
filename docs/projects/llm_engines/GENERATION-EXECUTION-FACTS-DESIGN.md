# Proposed generation execution-facts contract

**Status:** design only; not an implemented or accepted public contract.

**Date:** 2026-09-17

**Scope:** generation-run identity and execution facts needed to decide whether
two retained calls are meaningfully comparable. This document does not select a
learner runtime, add backend capture, change `seed_status`, change the cache
contract, or declare two executions equivalent.

## 1. Problem

Generation artifacts currently preserve the normalized request, normalized
response, requested and reported model labels, backend, and engine class. They
do not capture model bytes, quantization, runtime build, tokenizer, chat
template, queue timing, or prompt-processing timing
(`llm_engines/src/llm_engines/generation_artifacts.py:179-255`). The recorder
now truthfully labels those seven fields `unsupported_by_recorder`; this is a
temporary recorder boundary, not a statement that a backend cannot expose the
facts (`generation_artifacts.py:28-39`).

The retained Ollama 0.33.3 and llama.cpp b10679 feasibility audits show that
the same fact can arrive through different evidence paths:

| Fact | Ollama audit | llama.cpp server audit |
|---|---|---|
| Model digest | adjacent `/api/ps` query | operator hashes the GGUF |
| Quantization | adjacent `/api/show` or `/api/ps` | adjacent `/props` query |
| Runtime build | adjacent `/api/version` query | response fingerprint and adjacent `/props` query; operator may also hash the binary |
| Tokenizer | adjacent verbose `/api/show` material | not completely exposed over HTTP; operator may bind it through the GGUF digest |
| Chat template | adjacent `/api/show` query | adjacent `/props` query |
| Prompt-cache count | generation response | generation response |
| Queue duration | unavailable as a measurement | unavailable as a measurement |
| Prompt-processing duration | generation response | generation response |

The source location and binding assumption are therefore part of the fact.
Flattening all of these into unqualified scalar values would recreate the defect
this design is meant to correct.

## 2. Confirmed reusable surfaces

The following are confirmed from the current call path:

- ADR-021 already separates actor, epistemic method, and omission reason and
  defines model identity as independently sourced facts
  (`adr/ADR-021-run-artifact-envelope-semantics.md:132-159` and `:189-196`).
- The common envelope already carries open execution-environment metadata and
  explicit omissions (`llm_harness_core/src/llm_harness_core/run_artifacts.py:104-120`
  and `:198-215`).
- The generation body already has `model_identity` and a provenance map
  (`llm_engines/src/llm_engines/generation_artifacts.py:218-242`).
- `record_generation` owns the execution boundary and calls the engine once;
  the pure artifact builder consumes the already-normalized result
  (`generation_artifacts.py:313-358`).
- `GenerationResponse.seed_status` means that the adapter forwarded the seed
  and the provider completed the request; it explicitly does not claim
  deterministic output
  (`llm_engines/src/llm_engines/contracts/engine.py:312-328`).
- `CacheStats` currently uses a zero-valued object to mean both an observed zero
  and unreported cache information
  (`llm_engines/src/llm_engines/contracts/engine.py:185-207` and `:320-324`).
- Inspector supports only generation body version 1, summarizes labels rather
  than exact identity facts, and deliberately leaves model identity
  undetermined (`llm_inspector/src/llm_inspector/artifacts.py:22-24`,
  `:138-159`, and `:432-473`).

These surfaces are reusable only within those limits. In particular, the open
`provenance` mapping does not itself capture or bind a fact, and the current
Inspector does not compare model digests or execution facts.

The recorder actor's current `version` is the recorder contract constant
`"1"`, not an identity for the installed `ai_tools` code or wheel
(`generation_artifacts.py:26` and `:154-165`). Exact backend identity would
therefore still leave the normalization and omission-producing code itself
unidentified. A versioned learner installation must bind the record to a
separately verified distribution or source build; package version `0.1.0`
alone is not sufficient.

## 3. Proposed artifact representation

Adopt a new generation body version rather than changing the meaning of body
version 1. Keep fact values at their semantic locations and add a parallel
`fact_evidence` map keyed by absolute artifact JSON Pointer.

Illustrative shape, not an installed schema:

```json
{
  "model_identity": {
    "requested_label": "model-tag",
    "reported_label": "model-tag",
    "backend": "ollama",
    "digest": {
      "algorithm": "sha256",
      "value": "lowercase-hex",
      "scope": "ollama-model-manifest"
    },
    "quantization": "Q3_K_S"
  },
  "fact_evidence": {
    "/body/model_identity/digest": {
      "source": "adjacent_query",
      "method": "measured",
      "mechanism": "GET /api/ps",
      "observed_at": "2026-09-17T12:00:01Z",
      "binding": {
        "status": "assumption_bound",
        "assumptions": [
          "the named loaded model served the adjacent generation"
        ]
      }
    }
  }
}
```

### 3.1 Fact-evidence fields

Each captured execution fact has exactly one evidence entry:

| Field | Contract |
|---|---|
| `source` | `in_response` · `adjacent_query` · `operator_supplied` |
| `method` | Existing ADR-021 vocabulary: `measured` · `estimated` · `derived_post_hoc` · `declared` · `copied` |
| `mechanism` | Backend field, endpoint, or operator procedure that supplied the value; no credentials or absolute host paths |
| `observed_at` | UTC timestamp for the evidence observation |
| `binding.status` | `direct` only when the evidence is carried by the generation response; otherwise `assumption_bound` |
| `binding.assumptions` | Non-empty for `assumption_bound`; describes what connects the separately observed fact to this call |

An adjacent query may be strong evidence without being direct evidence. Time
adjacency, a matching model label, or an unchanged endpoint does not turn it
into a generation-response fact.

### 3.2 Typed digests and large values

A digest always carries `algorithm`, lowercase `value`, and `scope`. The scope
names the bytes covered: examples include `gguf-file`,
`ollama-model-manifest`, `server-executable`, `chat-template-utf8`, or a
specified canonical tokenizer representation. Digests with different scopes
are not directly comparable even when their values happen to match.

Raw tokenizer vocabularies, chat templates, `/props`, `/api/show`, and model
paths are not retained by default. The recorder retains an allowlisted digest
and safe scalar metadata. This prevents the absolute-path disclosure already
observed in llama.cpp `/props` and avoids turning a provenance feature into a
bulk metadata export.

### 3.3 Timing facts

`prefill_ms` must carry its backend meaning in the evidence mechanism. Ollama's
`prompt_eval_duration` and llama.cpp's `timings.prompt_ms` are useful observed
measurements, but this design does not assert that they delimit identical work.
A comparison may show their values while marking the metric semantics
non-comparable across different mechanisms.

No timing residual is recorded as `queue_ms`. Queue time remains omitted until
the backend supplies a field whose documented meaning is queue or wait time.

Usage evidence is per field, not one assertion for the whole `usage` object.
Provider-reported token counts and client-measured latency can coexist in one
response, so `/body/response/usage` with one `method` cannot truthfully describe
all of its children. Each retained usage fact receives its own evidence entry.

### 3.4 Recorder implementation identity

Backend execution facts and recorder implementation identity are separate
questions. The artifact should retain a reference to an installation/build
record that identifies the recorder distribution used to create it. For a
published learner installation that record includes the package name and
version plus the verified wheel digest. For a source execution it includes a
source revision and dirty-state declaration. The generation artifact binds to
that record by digest rather than copying host paths or a complete environment.

This does not redefine the envelope actor's recorder-contract version. It adds
the missing evidence for which implementation applied that contract.

## 4. Capture boundary

The artifact builder remains pure and performs no network or filesystem
discovery. New machinery supplies a typed, already-sanitized execution-facts
object to it.

The proposed flow is:

1. `record_generation` captures start time.
2. A backend-specific facts provider may collect a pre-call observation when
   needed.
3. The engine performs exactly one generation call.
4. The provider extracts in-response facts and may collect a bounded post-call
   observation.
5. The provider returns values, evidence records, and explicit per-field
   failures to `record_generation`.
6. The builder serializes only the supplied facts and emits omissions for the
   rest.

The provider protocol must be optional so existing `ChatModel` implementations
remain usable. Capture failure must not trigger a second generation or silently
drop the generation result. It produces `capture_failed` for the affected fact
and preserves a bounded, non-sensitive diagnostic outside student-facing
artifacts.

An operator-supplied fact enters through an explicit recording context, not
through backend guessing. Its binding assumptions must name the relationship
between the inspected file or process and the serving deployment.

## 5. Cache availability and seed evidence

### 5.1 Cache statistics

The eventual contract must distinguish these states:

- cache telemetry not reported;
- cache telemetry reported with zero hits; and
- cache telemetry reported with non-zero hits.

The least disruptive candidate is an explicit availability field on
`CacheStats`, defaulting to `not_reported`, with numeric zero interpreted as a
measurement only when availability is `reported`. This is a public response
contract change and is not authorized by this design. Generation body version 1
continues to require its omission entry for the all-zero sentinel.

### 5.2 Seed application

Do not change `seed_status`. Add a separate future
`seed_application_evidence` fact only when a provider echoes the seed or
otherwise reports its application. Its states should distinguish no evidence,
provider echo, and provider-reported application, and should use the same
evidence/binding representation as other execution facts. Forwarding a seed is
not evidence of deterministic output.

## 6. Inspector comparison

Inspector should eventually compare each fact independently. The proposed
per-field `status` vocabulary is:

- `equal` — comparable scopes and semantics, equal values, both directly bound;
- `different` — comparable scopes and semantics, different values, both
  directly bound;
- `not_comparable` — missing fact, different digest scope, or incompatible
  metric semantics; and
- `assumption_bound` — a value relation can be computed, but at least one side
  depends on a stated binding assumption.

For `assumption_bound`, also report `observed_relation: equal | different` so
the binding caveat does not hide the observed value difference.

`model_identity_equal` and whole-execution equivalence remain
`not_determined` unless a later accepted contract defines a sufficient fact set.
Matching labels, or even matching model bytes, do not establish equal runtime,
template, tokenizer, effective request rendering, or decoding conditions.

## 7. Backend design inputs

Design the provider interface against both retained audits even though only the
eventually selected learner runtime is implemented first:

- Ollama requires adjacent-query evidence for most identity facts and
  in-response evidence for cache and prompt evaluation.
- llama.cpp server requires a mix of in-response, adjacent-query, and
  operator-supplied facts. Its HTTP shape is reached through the local
  OpenAI-compatible adapter, not the in-process `LlamaCppEngine`; those are
  distinct deployment paths.

No vLLM coverage is inferred. It remains an unaudited production-serving gap.

## 8. Must be built (does not exist yet)

- generation body version 2 and its validation/golden fixtures;
- typed execution-fact, evidence, digest, and binding contracts;
- an optional backend facts-provider protocol;
- the `record_generation` orchestration that brackets one generation with
  bounded evidence capture;
- allowlisted sanitizers for adjacent-query payloads;
- per-field usage provenance rather than one method for the entire usage object;
- a digest-bound recorder installation/build record;
- one selected-runtime provider and its fabricated response tests;
- explicit cache-telemetry availability;
- optional seed-application evidence;
- Inspector body-version support and per-field comparison;
- migration/compatibility tests proving body version 1 remains readable; and
- publication and installation of the required wheels for the learner path.

## 9. Assumptions to verify

- Whether the selected learner runtime exposes stable endpoint semantics at the
  version chosen for M1.
- Whether pre- and post-call adjacent observations are needed for each fact, or
  whether one side plus a stated assumption is adequate.
- The canonical byte representation for Ollama tokenizer metadata.
- Whether a model-file digest is affordable on every learner execution or
  should be computed once and cached with separately validated file identity.
- Whether adding cache availability can remain backward compatible for Python
  callers or requires a new response-contract version.
- How independently published wheels will be pinned and digest-verified by the
  reliability lab.

## 10. Implementation gate

Do not implement extraction until the reliability lab selects its required
learner runtime and delivery path. The first implementation supports that one
runtime. The second audit remains a design forcing case and teaching artifact,
not a promise to support two learner runtimes.

Before implementation, the schema, generation body-version change, cache
availability behavior, and Inspector comparison semantics require explicit
contract authorization.
