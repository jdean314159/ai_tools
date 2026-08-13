# RUN-RECORD-00 Phase 3 — generation/agent cross-kind validation

**Status:** Complete, 2026-08-13.
**Decision:** The ADR-021 common-envelope hypothesis survives the first
cross-kind proof. Generation and agent-run artifacts share useful envelope
semantics without sharing or flattening their bodies.

## Implemented scope

`llm_engines.generation_artifacts` now wraps one existing `ChatModel.generate()`
call and returns both its ordinary `GenerationResponse` and a durable
`generation` artifact. It does not replace the runtime request/response types or
modify backend implementations.

The recorder captures:

- normalized request and response bodies;
- final versus aborted lifecycle;
- requested and reported model labels and backend;
- measured execution and artifact timestamps;
- usage, finish reason, tool calls, structured-output request, optimization,
  and cache fields when reported;
- explicit omissions for unavailable telemetry and protected payloads;
- conservative privacy declarations and scoped validation evidence; and
- optional semantic relationships to agent runs.

Raw provider payloads and error messages are default-off. Recording failures
raise `RecordedGenerationError` containing the original exception and an
immutable aborted-attempt artifact. The engine executes once in both success
and failure paths.

## Falsification result

The common reader validated and summarized both:

- a NAV-v1-derived `agent_run`, profile `agent_lib.nav`, body version 1; and
- a MockEngine-derived `generation`, body version 1.

Both expose identity, lifecycle, versions, lineage, actors, time, privacy, and
omissions through the same envelope. Their bodies remain different:

- agent body: task, status, trajectory steps, model roles, evaluation, and
  profile data;
- generation body: request, response, outcome, model identity, and field-level
  provenance.

No kind-specific conditional was added to `RecordEnvelope`. The cross-kind
implementation therefore did not falsify the small-envelope hypothesis.

Generation-to-agent membership is represented as a semantic relationship. A
generation copied without its parent retains the relationship but does not
invent a missing attachment. Attachments remain reserved for separately
addressable bytes.

## Deterministic fixture coverage

Mock and constructed contract fixtures cover:

- ordinary completion and JSON round trip;
- structured-output request and truncated response;
- tool-call response;
- partial usage telemetry;
- reported cache and optimization metadata;
- raw provider payload omitted and explicitly included;
- failed attempt with default-off error text;
- scoped privacy evidence;
- one-call recording and semantic lineage; and
- common-reader agent/generation dispatch without body homogenization.

The fixtures test recording semantics rather than model behavior. They require
no GPU or live service.

## Live local-engine acceptance

Maintainer acceptance used the already-installed Ollama `qwen3:8b` model on
2026-08-13 with a fixed synthetic prompt:

```text
Reply with exactly: RUN_RECORD_LIVE_OK
```

Observed result:

| Field | Value |
|---|---|
| output | `RUN_RECORD_LIVE_OK` |
| finish reason | `stop` |
| input/output/total tokens | 25 / 6 / 31 |
| measured latency | 179.76 ms |
| backend/model labels | `ollama` / `qwen3:8b` |
| raw provider payload recorded | no |
| privacy evidence | validated for fixed request, response, and raw-payload omission |
| artifact SHA-256 | `6ab7330856b39b4ddbc12e34d35ce7963ca63ad7292b6554c692bde9b0d6e235` |

The full artifact was written to `/tmp/run-record-phase3-live.json`, validated
with the common reader, and intentionally not committed. It contains only the
fixed prompt and returned sentinel, but timestamps and a random record ID make
it a maintainer acceptance result rather than a deterministic fixture.

## Mock-versus-live gaps

The real Ollama adapter populated measured token usage and latency, whereas
MockEngine estimates both. Neither path reported usable cache statistics. The
live path did not expose:

- model artifact digest;
- quantization;
- backend/runtime build;
- tokenizer or chat-template identity;
- queue or prefill timing; or
- cache hit/miss telemetry.

These remain explicitly unavailable rather than becoming required ceremonial
fields. Requested and reported labels matched, but ADR-021 correctly forbids
treating label equality as proof of identical model artifacts.

## Validation gates

```text
llm_engines:                         209 passed, 12 skipped
cross-kind integration fixtures:      2 passed
llm_harness_core + agent_lib:        170 passed (Phase 2 regression gate)
```

The `llm_engines` run under disabled plugin autoload emitted the existing
`asyncio_mode` unknown-option warning because pytest-asyncio was deliberately
not loaded; it did not affect results.

## Gate assessment and next boundary

Phase 3 is complete. The format now has evidence from two agent producers, a
deterministic generation producer, and one real local generation producer.

Next work may add inspector loading and kind-specific summaries. Experiment
records, campaign migration, RAG traces, photo artifacts, course fixtures,
bundle storage, and redaction tooling remain separate later decisions.
