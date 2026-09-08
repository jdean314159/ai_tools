# Ornith adaptive staged-assessment v2.1 preregistration — 2026-09-07

Status: frozen before the first live v2.1 assessment request.

This is the mechanical-repair restart required by the
[v2 preregistration](ORNITH-ADAPTIVE-STAGED-V2-PREREGISTRATION-2026-09-07.md).
All target identities, paired controls, predictions, budgets, measures,
adjudication rules, invalidations, and the six-run order from that document
remain unchanged. The entire sequence restarts in a new campaign directory;
the valid v1 half of the invalid pair is not reused.

## Reason for restart

The first v2 seed-17 run completed all nine selections but ended incomplete:
five scouts had no valid structured result, all three promoted records had
invalid evidence references, and lifecycle was `aborted`. The active
llama.cpp Jinja template does not render backend tool-call IDs into model
context. The v2 tool contract therefore required identifiers the model could
not observe. This was a harness-interface defect, not evidence about
repository-defect judgment.

The invalid pair is retained under
`runs/2026-09-07-ornith-adaptive-staged-v2-development/pair-seed17/`.
Its before and after endpoint fingerprints are both
`cd24e9603b33dec026aa531b4011dc834212a68c23a85943744c87bf56e49af1`,
so endpoint drift did not cause the failure.

## Sole treatment repair

For each executed shell call, the controller now adds a deterministic,
stage-local `evidence_id` (`shell-1`, `shell-2`, and so on) to the tool output
visible to the model. Backend tool-call IDs remain retained separately in the
transcript. Evidence validation resolves the model-supplied reference against
the visible stage-local ID and still requires an exact quote from exactly one
same-stage retained output.

No dossier rule, target-selection rule, repository prompt content, shell
budget, promotion rule, verifier budget, critic rule, seed, model setting,
grader, or prediction changed. The run schema is versioned to
`temporary-repository-assessment-adaptive-staged-run/v2` and the condition to
`adaptive_staged_v2_1` so repaired runs cannot be confused with the invalid
attempt.

## Frozen source identities

- staged v1 control SHA-256:
  `9eef019e6517da9dce7e1e72ff0f44638af6bff7a2fa9f8f5c2f63d631456b43`;
- invalid adaptive v2 SHA-256:
  `891bc024c8883e12b21f342e91981937e6ae3ef4fedd916b640792d21090d681`;
- repaired adaptive v2.1 SHA-256:
  `a02cbe5b9ef2d89628c39f6a00e1ec0b9b4231f61301e07c77504f03dcb5e448`;
- endpoint snapshotter SHA-256:
  `948397b46e054e2e36ef89b8306e482d3b26eb34d4966467d3be3c25ef0b265b`;
- external grader SHA-256:
  `e02288e330e84014298ae4c8420aa4f2a88223cbe11ddef1b4e3c0e9f5079bcb`.

The focused v2.1 and endpoint suite passed 10/10. The complete repository test
suite and Python quality gates passed immediately before the version-label
change; the version-label change and evidence-ID behavior passed the focused
suite afterward. No live v2.1 request had been made when this document was
frozen.
