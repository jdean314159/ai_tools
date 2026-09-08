# Ornith adaptive staged-assessment v2 preregistration — 2026-09-07

Status: frozen before the first live v1-control or v2-development assessment
request. This document governs Phase 1 of the
[adaptive staged v2 plan](ORNITH-ADAPTIVE-STAGED-V2-PLAN-2026-09-07.md).

## Scope and interpretation

This is a paired harness-development experiment on a known target, not a new
estimate of model capability. The target, grader, earlier runs, and failure
trajectories were available while v2 was designed. Consequently, recall is a
descriptive development result and cannot establish generalization. A recall
claim requires Phase 2 on independently prepared blinded targets.

The comparison asks whether the frozen v2 controller improves investigation
allocation and evidence discipline over fresh executions of staged v1, while
preserving the same model, target, seeds, endpoint, masking, and 45 executed
shell-call ceiling.

## Predictions frozen before execution

1. Every v2 run will satisfy all seven mechanical gates below. A failure is a
   harness defect or protocol failure, not negative model evidence.
2. V2 median substantive package coverage will be at least 7/9 and no lower
   than the paired v1 median.
3. V2 median maximum package-call concentration will be no more than 25%.
4. V2 median cumulative input tokens will remain below 25% of the autonomous
   baseline median of 1,648,791. No directional prediction against staged v1
   is made because v2 adds nine dossier-based selection calls and deeper
   verification.
5. Critic-accepted false positives will be no more frequent under v2 than
   under paired v1.
6. Known-defect median recall may remain 0/3. Any improvement is exploratory
   on this development target and must not be described as model
   generalization.

Report every seed, not only medians. A prediction is supported only by its
literal threshold; do not substitute post-hoc metrics.

## Frozen identities

- Target commit:
  `83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532`.
- Target archive SHA-256:
  `e4bac3a08e16a0d4644e658b93d1bcd5ce5a77d7af4c49e0a63a3a07e52206d2`.
- Corrected reference: current ai_tools HEAD at campaign start, recorded with
  the grader result.
- Model label: `Ornith-1.5-35B-Q4_K_M.gguf`.
- llama.cpp build: `b10679-50f068fff`.
- User-reported launch boundary: Q4_0 key and value caches, flash attention,
  Jinja templates, `--spec-type draft-mtp`, and
  `--spec-draft-n-max 3`.
- Endpoint-observed boundary: four 262,144-token slots with speculative MTP
  active.
- Seeds: 17, 31, and 47; temperature zero; thinking off.
- Conditions and source SHA-256:
  - staged v1 control: `run_staged_assessment.py`,
    `9eef019e6517da9dce7e1e72ff0f44638af6bff7a2fa9f8f5c2f63d631456b43`;
  - adaptive staged v2: `run_adaptive_staged_assessment.py`,
    `891bc024c8883e12b21f342e91981937e6ae3ef4fedd916b640792d21090d681`;
  - endpoint snapshotter: `capture_llamacpp_endpoint.py`,
    `948397b46e054e2e36ef89b8306e482d3b26eb34d4966467d3be3c25ef0b265b`;
  - external grader: `test_known_defects_at_83e1d09.py`,
    `e02288e330e84014298ae4c8420aa4f2a88223cbe11ddef1b4e3c0e9f5079bcb`.

The unavailable model-file digest and independently inspected remote process
argv remain explicit identity limitations.

Pre-execution amendment: the first endpoint-only capture showed that this
llama.cpp build nests `speculative.types` in each slot's `params` object. No
assessment request had been sent. The snapshotter was corrected to retain
that scalar while continuing to discard all other slot parameters, and to
refuse output overwrite; its frozen hash above is the corrected hash. The
superseded endpoint-only snapshot is retained as an invalid instrumentation
artifact.

## Fixed execution order

Run one campaign at a time in this exact order:

1. v1 seed 17;
2. v2 seed 17;
3. v2 seed 31;
4. v1 seed 31;
5. v1 seed 47; and
6. v2 seed 47.

The adjacent same-seed executions form a pair. Capture a privacy-bounded
endpoint snapshot immediately before the first half and after the second half
of each pair. Both snapshots must have the same configuration fingerprint and
show a healthy endpoint. If they differ, retain both runs as invalid and rerun
the complete pair only after restoring the frozen configuration. Do not run
pairs concurrently.

Do not change prompts, schemas, caps, promotion rules, source, endpoint
parameters, or adjudication rules after the first assessment request. A
mechanical bug requires retaining the invalid campaign, versioning the fix,
and restarting all six runs.

## V2 treatment and budgets

The controller constructs the same syntax-derived bounded dossier for every
package. The implementation and category caps are fixed at
`tools/run_adaptive_staged_assessment.py:297` and
`tools/run_adaptive_staged_assessment.py:332`. The frozen target produced
stable regenerated hashes for all nine dossiers before this document was
frozen.

Every scout selects an exact dossier path and symbol before shell access. The
selection is rejected after three unsuccessful attempts; validation is fixed
at `tools/run_adaptive_staged_assessment.py:379`. Each valid scout receives at
most two shell calls. Evidence quotes must resolve exactly within the same
stage at `tools/run_adaptive_staged_assessment.py:435`.

Promotion is deterministic: `supported`, then `unresolved`, tied by seeded
package order, first three (`tools/run_adaptive_staged_assessment.py:800`).
Each promoted hypothesis receives a fresh verifier with at most nine shell
calls. Only controller-validated verifier confirmations reach the existing
fresh-context critic. Only critic accepts appear in the deterministic report
renderer at `tools/run_adaptive_staged_assessment.py:823`.

The maximum is 18 scout calls plus 27 verifier calls: 45 executed shell calls.
Selection and critic requests are metered but do not consume this empirical
budget. Rejected shell attempts are protocol violations and do not count as
executed calls.

## Mechanical gates

All three v2 runs must satisfy all of these:

1. nine retained dossiers reproduce their canonical SHA-256 values;
2. every valid scout selection names a concrete dossier production symbol
   before shell access;
3. every controller-accepted evidence quote resolves to exactly one retained
   same-stage tool output;
4. no run exceeds 18 scout, 27 verifier, or 45 total executed shell calls;
5. every promoted hypothesis receives a structured verifier result;
6. the authoritative report reproduces from controller records without a
   model request; and
7. the external grader fails 3/3 behaviors on the frozen target and passes
   3/3 on the corrected reference.

The pre-live focused suite passed 24 tests, `make test-all` passed, and
`make quality-python` passed. These establish implementation readiness, not
experiment outcomes.

## Measures and adjudication

Primary development measures are mechanical-gate completion, known-defect
recall, accepted false positives, and precision. Secondary measures are
substantive package coverage, maximum package-call concentration, selections
and dispositions, promotion and verifier completion, evidence-reference
validity, natural versus forced structured completion, executed shell calls,
model calls, input/output tokens, elapsed time, controller uncertainty, and
protocol violations.

Known-defect recall is independently mapped to the three frozen behaviors and
requires both the affected behavior and relevant symbol or call path. A vague
thematic resemblance is not a hit. Every non-grader accepted claim is
independently checked against the frozen target before it can be classified as
a true positive; otherwise it is a false positive or insufficient evidence.

Substantive coverage keeps the existing definition: at least one production
source read plus a distinct test, caller, README, or package contract read.
Coverage is scored from retained commands and outputs, not model assertions.

## Invalidations and retention

A run is invalid if the target identity or archive differs, the sandbox is
writable, target imports escape `/workspace`, non-loopback network is
available, masked history is visible, oracle information enters a request,
source hashes differ, endpoint configuration drifts within a pair, a budget is
exceeded, promotion is discretionary, output is overwritten, or any raw
transcript is missing.

Retain raw transcripts, controller reports, dossiers, metadata, endpoint
snapshots, independent grader output, independent adjudication, exact source
copies or hashes, and a campaign SHA-256 manifest. The endpoint snapshotter
retains no endpoint URL, model directory, prompts, or slot task content.
