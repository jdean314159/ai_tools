# Repository-assessment artifact handoff — 2026-09-02

## Objective

Create the minimal durable recording path for controlled repository-assessment
experiments. Claude drafts an unambiguous `repository-assessment/v1` body
profile; Codex validates it against the existing run-artifact call path and
implements the recorder and honest backfill for the completed GLM/Qwen runs.

This is profile and recorder work, not another repository cleanup campaign and
not authorization to fix every issue discovered by the model comparison.

## Settled decisions

1. Use the existing `llm_harness_core.RunArtifact` common envelope. The
   implemented public type is `RunArtifact`, not `RunRecord`.
2. A model run that fails to submit within its natural turn budget uses
   `lifecycle="aborted"` even if a later report-only request succeeds.
3. The producer body records `completion_mode: "natural" | "forced"`.
4. Forced completion is a property of the original run. Do not create a second
   run artifact merely for the forced report.
5. Preserve three distinct evidence layers:
   - raw model claim;
   - evidence gathered by the model, including commands and reproducers;
   - independent adjudication and final disposition.
6. Version 1 is intentionally narrow. Include only the fields needed to make
   this comparison reproducible and interpretable: model identity,
   quantization, model digest when known, server/build configuration when
   known, repository commit and dirty-tree fingerprint, tool-call count,
   valid/rejected findings, and completion mode.
7. Backfilled fields that were not captured at execution time must be explicit
   omissions. Do not reconstruct them from conversational memory.
8. Defer checkpoint writing, a broad metrics framework, and a separate
   comparison profile until a later concrete experiment needs them.

## Grounded reusable surfaces

- `RecordEnvelope` already provides `kind`, `lifecycle`, profile/version,
  relationships, attachments, actors, time, privacy, omissions, capabilities,
  and execution environment:
  `llm_harness_core/src/llm_harness_core/run_artifacts.py`.
- `RunArtifact` already combines the common envelope with a producer-owned
  mapping body in that same module.
- `SupportedBodyContract` and `body_support_status()` already provide strict
  kind/body/profile-version matching for consumers.
- `write_artifact_bundle()` already writes a previously absent directory,
  confines attachment paths, validates exact SHA-256 bytes, rejects duplicate
  attachment IDs/paths, enforces privacy-reference coverage, and refuses
  overwrite.
- `load_artifact_bundle()` and `resolve_artifact_attachments()` already provide
  non-mutating attachment resolution and digest status.

Read those call paths and their tests directly before turning any item above
into a specification reuse claim. Symbol names alone are not proof.

## Must be built (does not exist yet)

- A producer-owned `repository-assessment/v1` body contract.
- Validation for the profile's required fields and three evidence layers.
- A recorder/adapter from the assessment harness transcript to `RunArtifact`.
- Focused tests for natural and forced completion, honest omissions, evidence
  adjudication, attachment sensitivity, and backfill behavior.
- Backfilled bundles for the GLM and Qwen runs, if the local `/tmp` inputs are
  still present and their digests can be computed from the exact retained
  bytes.

## Experiment evidence to preserve

The focused runs used the same prompt, read-only command policy, temperature,
seed, 45-turn budget, and forced report-only continuation.

| Observation | GLM-4.7-Flash Q8 | Qwen3.8-27B Q4_K_M |
|---|---:|---:|
| Model turns before forced reporting | 45 | 45 |
| Shell tool calls | 45 | 55 |
| Completion/reasoning tokens including report | 6,798 | 20,620 |
| Independently validated new defects | 0 | At least 3 grounded follow-ups |
| Natural report submission | No | No |

Qwen executed four test commands totaling 1,147 passed and 47 skipped. It also
executed a batch-ingestion reproducer and a direct ChromaDB duplicate-ID probe.
The latter disproved active corruption under installed ChromaDB 1.5.9 and led
the model to downgrade its own claim. That correction is the motivating example
for keeping claim, evidence, and adjudication separate.

If still present, the source artifacts are:

- `/tmp/glm47_repo_assessment_focused_transcript.jsonl`
- `/tmp/glm47_repo_assessment_focused_final.md`
- `/tmp/glm47_repo_assessment_qwen38_27b_focused_transcript.jsonl`
- `/tmp/glm47_repo_assessment_qwen38_27b_focused_final.md`

Treat these paths as ephemeral inputs, not durable documentation references.

## Grounded follow-ups from the Qwen run

These are leads for independent correction work, not automatically accepted
scope for the profile implementation:

1. `engram/src/engram/project_memory.py::store_episodes_batch` redundantly
   performs a batch add after `store_episode()` already indexes each accepted
   episode. Its positional slice can become misaligned after an earlier input is
   rejected, and its `indexed` statistic depends on duplicate-add behavior.
2. `engram/src/engram/concurrency.py::WriterLock` unlinks the lock pathname when
   clearing stale state, which can break inode-based `flock` mutual exclusion
   under unlink/recreate races.
3. `rag_lib/src/rag_lib/retrieval/retriever.py::_get_bm25_index` claims to
   rebuild when ChromaDB is newer but performs no staleness comparison.
4. `scripts/clean_review_bundle.py::_validated_target` does not reject package
   subdirectories inside the live checkout when they contain `pyproject.toml`.

The user selected these fixes on 2026-09-03. They are now corrected in separate
reviewable changes with regression coverage: batch episode storage delegates
indexing exactly once per accepted episode; `WriterLock` never unlinks its lock
inode; Chroma-backed collection mutations persist a marker used to invalidate
same-count BM25 caches; and review cleanup rejects the live checkout, its
ancestors, and its descendants. The recorder remains a separate future task.

## Working-tree and verification warning

The checkout was already dirty before this documentation update. It contains
the user's cleanup/hardening work, including Engram, tutor, CI, OpenAI backend,
and review-cleanup changes plus untracked files. Preserve all of it and inspect
overlap before editing.

The Qwen assessment actually ran and reported:

- `engram/tests`: 245 passed;
- `llm_engines/tests`, `rag_lib/tests`, `llm_harness_core/tests`, and
  `action_trajectory_loop_guard/tests`: 443 passed, 12 skipped;
- root `tests`: 113 passed;
- Inspector UI, language-tutor reference app, and diagnostics-agent tests:
  346 passed, 35 skipped.

It did not successfully run `agent_lib/tests` or `llm_inspector/tests`; do not
claim otherwise. This documentation-only update does not rerun those tests.

## Pasteable next-thread message

> Continue the `repository-assessment/v1` artifact work in `ai_tools`. Read
> `AGENTS.md`, `docs/design/VISION.md`, `docs/internal/STATUS.md`,
> `docs/internal/ROADMAP.md`, and
> `docs/internal/REPOSITORY_ASSESSMENT_HANDOFF_2026-09-02.md` first. Claude owns
> the initial profile draft; do not invent or implement a schema until that
> draft is supplied. Then trace every proposed reuse claim through
> `llm_harness_core.run_artifacts` and its tests, identify confirmed reuse versus
> machinery that must be built, and implement only the minimal profile
> validation, recorder, focused tests, and honest GLM/Qwen backfill. Preserve
> `lifecycle="aborted"` for runs that did not submit naturally and record
> `completion_mode="forced"` in the same body. Keep raw claims,
> model-gathered evidence, and independent adjudication separate. Do not add
> checkpointing, a general metrics framework, a separate comparison profile, or
> fixes for assessment-discovered repository issues without explicit scope.
