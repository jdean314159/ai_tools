# Ornith 1.5 35B known-defect preregistration — 2026-09-07

Status: frozen before the first repository-assessment run.

## Research question

On the same frozen repository, prompt, tools, seeds, turn budget, and objective
three-defect grader used for Qwen3-Coder, does the Ornith endpoint show better
known-defect recall, substantive coverage, or report precision?

The unchanged synthetic prerequisite suites passed 44/44 observations for
Ornith, including 12/12 multi-turn recoveries versus Qwen3-Coder's 6/12. This
campaign tests whether that difference transfers to autonomous repository
assessment; it does not assume that it will.

## Predictions recorded before execution

1. Median known-defect recall will remain 0/3. Synthetic recovery success does
   not directly supply defect judgment or broad repository search.
2. All three runs will submit naturally because Ornith followed every frozen
   multi-turn recovery protocol, although the repository task is materially
   harder and this prediction may fail.
3. Median substantive coverage will remain 1/9. The baseline condition has no
   external coverage controller, so the model still decides where to search
   and when it has enough evidence.

Any median recall of at least 1/3, strictly greater than the matched
Qwen3-Coder Q4_0 baseline median, contradicts prediction 1 and counts as a
measured improvement on this target. Report the full per-seed distribution;
do not substitute a best-run score for the median.

## Frozen constants

- Target commit:
  `83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532`.
- Target archive SHA-256:
  `e4bac3a08e16a0d4644e658b93d1bcd5ce5a77d7af4c49e0a63a3a07e52206d2`.
- Model label: `Ornith-1.5-35B-Q4_K_M.gguf`.
- llama.cpp build: `b10679-50f068fff`.
- User-reported launch boundary: Q4_0 key and value caches, flash attention,
  Jinja templates, `--spec-type draft-mtp`, and `--spec-draft-n-max 3`.
- Endpoint-observed boundary: four 262,144-token slots; slot records report
  `speculative: true` and `speculative.types: none,draft-mtp`.
- Condition: baseline only. The failed Qwen planner is not introduced into
  this model comparison.
- Thinking: off. Temperature: zero. Turn budget: 45.
- Seeds and run order: 17, 31, then 47.
- Base prompt, `shell` and `submit_report` contracts, report requirements,
  read-only bubblewrap boundary, private `/tmp`, network isolation, output
  clipping, and no-host-fallback policy are unchanged in
  `tools/run_planner_assessment.py`.
- The defect identities, grader source, target/HEAD grader outcomes, prior
  models' findings, and prior search trajectories are withheld from every
  model request until its report is final.
- Complete all three valid runs. Do not stop early, change the turn budget, or
  tune the prompt, scorer, seeds, or model parameters after the first run.

The Qwen3-Coder comparison baseline used no speculative decoding, whereas MTP
is active for Ornith. Consequently this is a matched endpoint-configuration
comparison, not an isolated causal estimate of model weights. Any outcome
difference may arise from the model, MTP, or their interaction.

## Measures and decision rules

Known-defect recall is primary. After each final report, an independent scorer
maps validated findings to the three frozen grader behaviors. A defect counts
only when the report identifies the affected behavior and relevant symbol or
call path; vague package suspicion does not count. Each run scores 0–3.

Secondary measures are validated false positives and precision, substantive
package coverage out of nine, maximum package-specific shell-call
concentration, natural versus forced completion, turn-cap binding, shell-call
count, turns, token usage, and stated remaining uncertainty. Precision is
undefined when a report contains no validated findings.

Substantive coverage uses the already frozen definition: one production-source
read plus a distinct test, caller, README, or package contract read. The
harness is known to omit relevant root-level tests and callers from its passive
coverage field. Independent adjudication will therefore score those paths from
the exact transcript using the preregistered definition, as it did for the
Qwen baseline; the harness will not be changed mid-comparison.

The three graded defects remain:

1. redundant embedding and Chroma insertion in
   `ProjectMemory.store_episodes_batch`;
2. dead-PID inode replacement in `WriterLock`; and
3. acceptance of a stale same-count disk cache in
   `HybridRetriever._get_bm25_index`.

This list is recorded in the human-only preregistration and external grader,
never in the model context.

## Invalidations

A run is invalid if the wrong target is mounted, the target is writable,
target imports resolve outside `/workspace`, the shell has non-loopback
network access, host fallback occurs, oracle information reaches the model,
the endpoint model or launch configuration changes, or any raw transcript is
missing. Retain invalid attempts with their reason. If server state changes,
rerun every affected seed rather than silently mixing conditions.

The model file digest and independently inspected remote process argv are
unavailable and are explicit omissions in the campaign fingerprint. Those
omissions limit identity and launch verification but do not invalidate the
run under this frozen design.

## Durable evidence

Each run retains the exact JSONL transcript, raw report, and metadata. The
campaign also retains the preregistration, server fingerprint, independent
adjudication, and SHA-256 manifest. These use the existing temporary experiment
schema; they do not implement or modify the deferred production
`repository-assessment/v1` profile.
