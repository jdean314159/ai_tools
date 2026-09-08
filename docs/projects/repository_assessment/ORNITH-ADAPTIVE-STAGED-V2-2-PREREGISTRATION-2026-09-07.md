# Ornith adaptive staged-assessment v2.2 preregistration — 2026-09-07

Status: frozen before the first live v2.2 assessment request.

This is the second and final mechanical-repair restart of Phase 1. It inherits
the target, paired v1 controls, predictions, budgets, measures, adjudication,
invalidations, and six-run order from the
[v2 preregistration](ORNITH-ADAPTIVE-STAGED-V2-PREREGISTRATION-2026-09-07.md),
plus the visible stage-local evidence IDs introduced by the
[v2.1 preregistration](ORNITH-ADAPTIVE-STAGED-V2-1-PREREGISTRATION-2026-09-07.md).
The complete sequence restarts in a new campaign directory.

## Reason for restart

V2.1 made evidence IDs visible and all three promoted verifiers used valid
stage-local IDs. However, two of nine seed-17 scouts submitted complete
structured reports after disproving their hypotheses but changed the repeated
`expected_behavior_source` field to `invariant_derived`. The controller had
silently made exact repetition an acceptance precondition and discarded both
reports, causing `completion_mode: incomplete` and `lifecycle: aborted`.

That field is a controller-owned selection binding already retained in the
selection record. Allowing a repeated model string to abort the run adds no
evidentiary protection. The invalid v2.1 pair is retained under
`runs/2026-09-08-ornith-adaptive-staged-v2-1-development/pair-seed17/`.
Its before and after endpoint fingerprints are both
`cd24e9603b33dec026aa531b4011dc834212a68c23a85943744c87bf56e49af1`.

## Sole additional repair

V2.2 treats selected path, symbol, and expected-behavior source as
controller-owned. A report's repeated values are retained as
`reported_symbols` and `reported_expected_behavior_source`; the authoritative
fields are copied from the frozen selection. Any mismatch is explicitly
recorded in `selection_binding`. A positive `supported` or `confirmed` result
with a binding mismatch is conservatively downgraded to `unresolved` or
`insufficient_evidence`, but the structured stage is retained.

The controller likewise applies evidence failure only to positive claims, as
the original plan specified: invalid evidence downgrades `supported` and
`confirmed`, while `disproved` and `rejected` remain negative and cannot be
promoted accidentally. No repository-facing selection, prompt target, budget,
promotion, grader, seed, or prediction changed. No defect-recall result from
either invalid attempt was examined or used for tuning.

The run schema is
`temporary-repository-assessment-adaptive-staged-run/v3`; the condition is
`adaptive_staged_v2_2`.

## Frozen source identities and readiness

- staged v1 control SHA-256:
  `9eef019e6517da9dce7e1e72ff0f44638af6bff7a2fa9f8f5c2f63d631456b43`;
- invalid adaptive v2.1 SHA-256:
  `a02cbe5b9ef2d89628c39f6a00e1ec0b9b4231f61301e07c77504f03dcb5e448`;
- frozen adaptive v2.2 SHA-256:
  `e2412893eb3b9abb9eb3c75dde36c348632f61e7a8b8c991b1111a2e0d5fe312`;
- endpoint snapshotter SHA-256:
  `948397b46e054e2e36ef89b8306e482d3b26eb34d4966467d3be3c25ef0b265b`;
- external grader SHA-256:
  `e02288e330e84014298ae4c8420aa4f2a88223cbe11ddef1b4e3c0e9f5079bcb`.

The post-repair focused suite passed 26/26. `make test-all` and
`make quality-python` both passed against the exact frozen source. No live
v2.2 request had been made when this document was frozen.
