# RUN-RECORD-00 Phase 0 inventory and crosswalk

**Status:** Complete; reviewed as the evidence base for ADR-021 and ADR-022.
**Prepared:** 2026-08-13
**Scope:** Durable run/evaluation artifacts. Runtime state stores, caches, source
datasets, and application databases are listed only where needed to distinguish
them from run records.

## Result

The repository has no common durable artifact contract. It has one substantial
versioned agent-run artifact (NAV), a second unversioned agent-run artifact
(ASC), serializable but non-durable generation contracts, inspector exports,
and several campaign/report formats. A common envelope remains plausible, but
the current artifacts do not share stable identity, lineage, privacy,
environment, or version semantics.

Phase 0 did not itself authorize a `RunRecord` class, package, producer
migration, or schema. ADR-021 and ADR-022 subsequently accepted the layered
semantics and ownership used by the completed Phase 2 compatibility slice.

## Inventory method and boundary

The inventory searched production and example Python writers for JSON, JSONL,
and CSV outputs, then read the representative producer and consumer call paths.
Detailed field analysis is bounded to NAV, ASC, generation request/response,
inspector `Trace`, and the NAV paired campaign. Other durable outputs are
catalogued by family and disposition rather than decomposed field by field.

The following are not run artifacts for this project:

- Engram episodes, sessions, semantic graphs, schemas, neural state, and
  telemetry are application/runtime persistence.
- RAG BM25 JSON and embedding caches are derived caches.
- agent workspace allocations, leases, and programming-task state are mutable
  coordination/checkpoint state.
- synthetic corpora, answer keys, task sets, candidate pools, and ground truth
  are datasets or immutable input manifests.
- mail state and application configuration are application state.

## Durable producer and consumer catalogue

| Family | Producer and output | Consumer | Artifact role | Phase 0 disposition |
|---|---|---|---|---|
| NAV environment | `build_environment_manifest()` in `agent_lib/src/agent_lib/eval/repo_navigation.py:1601-1643`; CLI writes `environment-manifest.json` in `agent_lib/examples/repo_navigation_eval.py:276` | NAV record links it only by `manifest_sha256`; external audit | Manifest | Detailed representative |
| NAV agent run | `render_run_record()` at `repo_navigation.py:1672-1713`; CLI writes `run-record.json` at `repo_navigation_eval.py:266-277`; paired campaign also writes one per arm at `agent_lib/examples/nav_verifiable_campaign.py:329-347` | Counterfactual continuation reads steps and usage at `agent_lib/examples/nav_counterfactual_finalize.py:176-209`; campaign aggregation | Versioned agent-run record | Detailed representative and compatibility anchor |
| NAV counterfactual | `nav_counterfactual_finalize.py:200-209` | Human/report analysis | Derived evaluation record containing prompts and raw responses | Catalogue; privacy stress case |
| ASC task run | `examples/asc_probe/live_probe.py:417-452` writes per-workspace `record.json` | Resume loader and aggregator at `live_probe.py:548-577` | Unversioned agent-run/evaluation hybrid | Detailed representative |
| ASC campaign | `live_probe.py:567-577` writes `live_probe_results.json`; `run_probe.py:48-50` writes `probe_results.json` | Human analysis | Campaign report embedding records | Catalogue; later experiment adapter candidate |
| Generation | `GenerationRequest`/`GenerationResponse` at `llm_engines/src/llm_engines/contracts/engine.py:250-279`; backends return responses but no general recorder writes them | Callers and interop conversion | Runtime contract, not a durable artifact | Detailed paper sketch; machinery must be built |
| Inspector trace | `Trace` at `llm_inspector/src/llm_inspector/core/trace.py:127-160`; generic serializer at `core/serialize.py:8-29`; golden fixture in `llm_inspector/tests/golden_trace.json` | Inspector render/export/compare paths | Inspection trace/export | Detailed representative; not lossless replay |
| Inspector reports | JSON exporters and CLI writes in `llm_inspector/src/llm_inspector/export/*.py` and `cli.py:106-151`; UI compare bundle download at `llm_inspector_ui/.../compare_panel.py:133-134` | Humans and inspector CLI | Report, diff, or bundle | Catalogue; later loader/compare work |
| NAV paired campaign | manifests and per-arm records at `nav_verifiable_campaign.py:127-235`; summary logic at `agent_lib/src/agent_lib/eval/verifiable_campaign.py:358-443`; committed safe summary at `agent_lib/eval_manifests/nav_verifiable_campaign_v1/live-result-summary.json` | Decision function, validation report, humans | Experiment manifest, child agent records, aggregate summary, decision | Detailed experiment representative |
| Neural-memory eval | `tests/integration_tests/eval/trial_runner.py:20-80` writes trial JSON and `all_trials.json`; sweep scripts write further results | Resume logic, metrics, reports | Experiment trials/dataset | Catalogue only |
| RAG benchmark | `rag_lib/scripts/benchmark.py:245-266` | Humans | Evaluation report with raw runs | Catalogue only |
| Diagnostics eval | `examples/diagnostics_agent/scripts/run_fp_eval.py:26-50` | Humans/CI gate | Evaluation report | Catalogue only |
| Agent teaching coordination | `examples/agent_coordination_teaching/run_demo.py:120` and `exchange.py:107-119` write manifest, exchanges, and trace events | Teaching tests at `test_demo.py:73-114` | Manifest plus event logs | Catalogue only |
| Knowledge/adjudication campaigns | `scripts/normalize_conversation_corpus.py`, `extract_knowledge_candidates.py`, `review_knowledge_candidates.py`, `compare_adjudication_strategies.py`, and `adjudicate_neural_memory_probe.py` | Later pipeline stages and reports | Dataset, manifest, decisions, experiment result | Out of first implementation |
| Application evaluations | diagnostics, language tutor, mail assistant, and answer-uplift scripts | Humans/CI | Application-specific reports | Out of first implementation |

## Privacy-safe representative sample set

No private or live model artifact is required for Phase 0.

1. **NAV:** construct the existing synthetic record used by
   `agent_lib/tests/test_repo_navigation_eval.py:810-829`. It exercises steps,
   telemetry, scoring, and read-only verification without a real repository.
2. **ASC:** use a synthetic task/record shaped by
   `examples/asc_probe/live_probe.py:417-450`, replacing workspace, reasoning,
   observations, and held-out detail with inert fixture text. No committed safe
   per-run fixture currently exists.
3. **Generation:** use a `MockEngine` request/response. The mock exercises the
   real contract at `llm_engines/src/llm_engines/backends/mock.py:73-105`, but
   estimates token usage and does not exercise provider payloads, tool calls,
   cache statistics, optimization metadata, or failures.
4. **Inspector:** use committed `llm_inspector/tests/golden_trace.json`, built
   by `test_golden_trace.py:11-42`.
5. **Campaign:** use committed
   `agent_lib/eval_manifests/nav_verifiable_campaign_v1/live-result-summary.json`.
   It contains aggregate results and hashes of external detailed artifacts,
   not private prompts or trajectories.

Golden record files should be added only after the ADR defines what they claim
to validate. The Phase 0 sample selection is not a schema commitment.

## Multi-axis field crosswalk

Legend: obligation describes the current producer, not a future requirement.
Sensitivity is conservative. Replay means the strongest operation the current
field can support without inventing missing data.

| Concept | NAV | ASC | Generation request/response | Inspector trace | Campaign | Axis findings |
|---|---|---|---|---|---|---|
| Schema/version | Required integer `schema_version=1` | Absent | Pydantic runtime model only; no artifact version | Python dataclass shape; no artifact version | Mixed: some manifests/child NAV records versioned, summary unversioned | Scope: envelope/body unresolved. Origin: producer-declared. Stability: only NAV has an explicit durable claim. |
| Record identity | Absent | Composite `(mode, seed, task_id)` used for resume | `session_id` is optional and is not record identity | turn/session plus random event IDs; no trace ID | task/pair IDs and manifest hashes | Identity is fragmented and sometimes adapter-derived. Stable IDs must be distinguished from resume keys and session IDs. |
| Kind | Implicit from filename/shape | Implicit | Python type | Python type/export shape | Implicit from filename | Reader dispatch cannot be reliable without out-of-band knowledge. |
| Time | Run elapsed time only | Run elapsed; campaign `generated_at` | Usage latency only | turn/event timestamps optional; metrics latency | Campaign output has no common started/finished pair | Wall-clock occurrence, duration, and generation latency are different semantic scopes. |
| Producer identity | Function names appear only inside NAV manifest measurement | Absent | backend name, not recorder identity | event source package/component | Track/protocol note only | Runtime backend is not artifact producer/version. |
| Model/backend | Usually free-form `config.model_label` | Worker/mentor backend, model, quantization, think | Response model/backend; request omits requested model because engine owns it | metrics engine/model | Top-level model/seed/temperature in committed summary | Mostly declared labels; exact model digest, runtime version, and quantization are inconsistently available. |
| Request/task | NAV task is not top-level; question may survive in run metadata/steps | task ID and tier, not full goal/source fixture | Full messages and generation controls in request | turn text and assembled context | Manifest identifies tasks/config | Prompts/goals are high sensitivity and may be required for re-execution but not safe export. |
| Output | Final output plus every step action/observation | Outcomes, reasoning trace, observations; not a normalized final answer | Assistant message, tool calls, finish reason | Trace focuses on input/context and events, not necessarily final model output | Metrics/decision only | Kind-specific bodies must remain distinct. |
| Usage/resources | Planner usage, tool telemetry, elapsed and score resources | Step/escalation counts and elapsed | token usage, latency, cache/optimization data | token accounting plus run metrics | Aggregate tokens/rates | Missing telemetry must not be represented as measured zero; current `CacheStats` explicitly has zero/unknown ambiguity. |
| Environment/provenance | Separate manifest hash, git state, source hashes, policy, pre/post tree digests | Workspace path only | Absent beyond backend/model | Evidence provenance and event sources; no host/runtime manifest | Input manifests and external artifact hashes | NAV is strongest but includes sensitive absolute paths and dirty-tree text. Environment should likely be referenced, scoped, and privacy classified. |
| Lineage | Manifest hash only | Embedded by campaign report; no parent ID | Session hint only | span relationships exist in memory | Pair manifests and external hashes | Serializer drops inspector event/span IDs at `core/serialize.py:12-16`, so current JSON cannot preserve trace lineage losslessly. |
| Evaluation | Arbitrary `score` dictionary | Visible/held-out booleans, classification, tamper flags | None | Signals/evidence flow, not a pass/fail evaluator result | Frozen aggregate and decision | Evaluator/scorer identity and version are generally absent. Derived outcomes must be marked as derived rather than observations. |
| Privacy/redaction | No declaration; can contain paths, prompts, observations, tool results, git status | No declaration; workspace, reasoning, held-out detail, observations | Raw messages/tool calls and optional raw provider payload | Full context/evidence/event payloads | Detailed children external, but no declared privacy policy | All representative artifacts can contain sensitive data. None states policy, transformations, or omitted fields. |
| Storage/cardinality | One JSON plus large embedded steps/telemetry; manifest separate | One JSON per run; aggregate embeds records | No storage convention | Inline lists; generic JSON export | Manifests, child files, pairs, summary, decision | Large child collections favor references, but portable-copy behavior is unresolved. |
| Replay | Counterfactual continuation from stored steps and usage; not deterministic model replay | Resume skips completed composite keys; cannot reconstruct task/workspace from record alone | Re-execution possible only if engine/config/environment are separately known | Inspection reconstruction; serializer loses IDs | Statistical recomputation possible from detailed external pairs, not summary alone | “Replay” must be split into parse/inspect, aggregate recomputation, structural continuation, tool replay, and model re-execution. |

## Agent-general versus producer-specific fields

Confirmed agent-general candidates because both NAV and ASC have equivalents:

- status, stop reason, elapsed duration, step count;
- model/role configuration, although represented differently;
- step/action or observation evidence;
- tool/policy activity;
- task identity;
- evaluation outcomes derived after execution.

NAV-specific or currently NAV-only:

- environment-manifest hash and repository source inventory;
- pre/post tree digests and `read_only_verified`;
- navigation pruning/denied-byte telemetry;
- planner token budget accounting;
- arbitrary navigation score payload;
- counterfactual finalization's dependence on exact step/tool-call shape.

ASC-specific or currently ASC-only:

- gaming/escalation tier and worker/reviewer mode;
- visible versus held-out oracle details;
- tamper attempts, special-casing, and verbalized intent;
- worker/mentor role configuration;
- explicit quantization and thinking-mode declarations;
- timeout records whose shape omits fields present on completed records.

These lists are evidence for an agent body design; they are not proposed field
requirements. In particular, ASC reasoning traces and NAV observations require
an explicit privacy decision before persistence or export.

## Non-normative generation-record sketch

This sketch exists only to test cross-kind coherence in the ADR.

- Common candidate metadata: artifact schema identity/version, record ID, kind
  and body version, created/started/finished times, producer identity/version,
  parent/child references, environment reference, privacy declaration.
- Generation body candidates: normalized `GenerationRequest`, normalized
  `GenerationResponse`, requested and reported model/backend identities,
  measured/estimated/unavailable telemetry provenance, error or termination,
  and an optional separately protected raw-provider artifact.
- Data absent from current runtime contracts: durable record identity,
  recorder version, timestamps around the call, exact runtime/model artifact
  provenance, privacy declaration, and explicit telemetry availability.

The current `GenerationResponse` must not be renamed or treated as the durable
record: the project document explicitly excludes replacing runtime contracts.

## Dependency and ownership constraints

Current dependency direction is:

`llm_harness_core` <- `llm_engines` / `llm_inspector` <- `agent_lib`

- `llm_harness_core` has no runtime dependencies
  (`llm_harness_core/pyproject.toml:6-13`) and already owns the package-neutral
  `TraceEvent` contract (`llm_harness_core/src/llm_harness_core/events.py:10-22`).
- `llm_engines` depends on Pydantic and `llm-harness-core`; it owns generation
  runtime contracts (`llm_engines/pyproject.toml:12-18`).
- `llm_inspector` depends only on `llm-harness-core` and owns inspection/export
  behavior (`llm_inspector/pyproject.toml:12`).
- `agent_lib` depends on all three plus Engram and the trajectory guard
  (`agent_lib/pyproject.toml:12-19`).

Therefore:

- A package-neutral envelope in `llm_harness_core` is possible only if it stays
  dependency-free and does not import Pydantic or producer bodies.
- Generation bodies can depend on a lower-level envelope, but a core package
  cannot depend on `llm_engines` to learn their shape.
- Inspector loading can depend on core contracts but should not own producer
  runtime models merely because it renders them.
- Agent adapters must live at or above `agent_lib`; lower packages cannot
  import NAV/ASC types.

Inventory constrains ownership but does not decide it.

## Missing machinery (does not exist yet)

- Public artifact envelope and kind/body version policy.
- Durable generation recorder around request and response.
- Privacy declaration, redaction-policy vocabulary, and composition rules for
  referenced children.
- Common reader with version dispatch and kind-specific summarizer routing.
- Validator and unknown-kind/version behavior.
- Stable record identity and lineage/reference integrity rules.
- NAV-v1 adapter and an ASC adapter.
- Environment capture contract that distinguishes observed, declared, derived,
  unavailable, and redacted facts.
- Defined replay vocabulary and capability declaration.

## ADR questions and forcing cases

1. Is envelope version independent from body version, and which component
   governs JSON compatibility?
2. What common operations must work for an unknown but well-formed body:
   discovery, privacy decision, lineage traversal, validation, or summary?
3. Are children embedded, referenced by ID/hash, or both? What does a portable
   partial bundle promise when children are missing?
4. Does privacy status compose monotonically from children, and can a parent be
   shareable when a referenced child is restricted?
5. How are raw prompts, reasoning, evidence text, paths, tool results, git
   status, and provider payloads omitted or protected?
6. How are measured zero, unavailable, unreported, estimated, declared, and
   redacted telemetry represented?
7. Can a NAV-v1 record be adapted losslessly, including counterfactual
   continuation? If not, which original artifact remains authoritative?
8. Should ASC timeout and completed records share one body with explicit
   conditional fields, or be distinct outcomes?
9. Which model identity is comparable: requested label, provider-reported
   label, digest, quantization, tokenizer/template, runtime build, or a set of
   independently sourced facts?
10. Which replay capability is claimed per record: inspection, aggregate
    recomputation, continuation, tool replay, or model re-execution?
11. Is JSON Schema, Python models, or both normative, and how are extensions
    namespaced?
12. Does ownership belong in `llm_harness_core`, producer packages, or a split
    where core owns only dependency-free envelope primitives?

## Assumptions to verify in Phase 1 or implementation

- No committed privacy-safe ASC per-run fixture was found; confirm before
  adding a new synthetic golden.
- NAV schema version 1 has no separate published JSON Schema; confirm whether
  any external consumer beyond the counterfactual script exists.
- The committed NAV campaign summary hashes external detailed artifacts that
  are not present in the repository; confirm their retention policy before
  defining portable experiment bundles.
- A live engine may not expose exact model digest, quantization, tokenizer,
  template, queue time, prefill time, or cache statistics. Do not promote these
  from desired to required without backend evidence.

## Phase 0 gate assessment

The bounded inventory, representative sample selection, crosswalk, ownership
constraints, missing machinery, and ADR questions were reviewed. Phase 0 is
complete. ADR-021 and ADR-022 record the resulting decisions; Phase 2 is
documented in `RUN-RECORD-00-PHASE-2-COMPATIBILITY.md`.
