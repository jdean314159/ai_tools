# Ornith empirical-probe-obligation screen result — 2026-09-09

The one-pair screen did not trigger escalation. The probe-required treatment
did not execute a probe: it exhausted all 45 investigation actions as shell
calls and ended in the preregistered structural non-completion state. The
probe-optional control also exhausted 45 shell actions, then produced a forced
report. The treatment therefore has no evaluable final report and must not be
reported as 0/3 recall.

This is a screen result, not evidence that probe obligation cannot improve
recall. It is one Ornith model, one target, one seed, and a controller-side
intervention designed and adjudicated under consolidated owner authority.

## Frozen protocol and authority

The protocol was frozen before either model request in commit `33b83db`.
It held constant the single-context harness, target, seed 31, model, endpoint,
tools, 45-action budget, 60-turn fail-safe, sandbox, and report schema. Both
arms received the same instrumented `run_probe` tool. Only the treatment
received the generic obligation message and submission gate.

Codex designed, implemented, validated, operated, adjudicated, documented, and
committed the screen under the repository owner's consolidated authorization.
No independent-verification claim is made. All outputs and failed validation
attempts are retained for later review.

## Results

| Arm | Completion | Actions | Shell | Probe | Gate result | Recall status | Adjudicated findings |
| --- | --- | ---: | ---: | ---: | --- | --- | ---: |
| probe optional | forced valid submission | 45 | 45 | 0 | not required | 0/3 evaluable | 2 false positives, 0 known defects |
| probe required | structural non-completion | 45 | 45 | 0 | unsatisfied | not evaluable | no final report |

The control ran for 151.0 seconds, used 869,535 input and 4,652 output tokens,
and made 46 model calls including forced reporting. Its report claimed missing
run-artifact fixtures and a Git-metadata hygiene problem; post-run adjudication
classified both as environmental false positives for this intentionally masked
export target. Neither matched a graded defect.

The treatment ran for 151.0 seconds, used 1,518,414 input and 3,194 output
tokens, and made 45 model calls. It never called `run_probe`, so the mechanical
predicate was never satisfied. The controller ended the run structurally rather
than forcing a report without the required observation.

## External grader

The frozen target export failed all three known-defect tests; corrected
reference `8e2e9e5` passed all three:

| Export | Failed | Passed |
| --- | ---: | ---: |
| target `7d37920` | 3 | 0 |
| corrected reference `8e2e9e5` | 0 | 3 |

The grader ran only after both model runs were final, with `-c /dev/null`,
`--noconftest`, plugin autoload disabled, bytecode writing disabled, and
export-only package paths. The grader was not mounted in either model sandbox.

## Endpoint and sandbox validity

The before/after endpoint fingerprints retained the same model label, build,
launch metadata, context, slot count, and speculative enablement. Slots 1–3
changed only nullable `speculative_types` telemetry from `null` to
`none,draft-mtp`; this is the preregistered compatible telemetry transition.
The read-only target, masked historical documents, private temporary storage,
loopback-only network, and no-host-fallback checks passed before each run.

The probe gate itself passed its pre-run controls. An output-producing script
that imported no repository module was rejected; a script importing
`llm_harness_core` was accepted with its `/workspace` origin recorded.

## Interpretation

The treatment did not demonstrate a recall benefit. More specifically, the
model did not select the newly available probe tool despite being told that a
probe was required, and the obligation consumed the entire action budget
without reaching a valid final report. This is consistent with either a
probe-selection failure or budget displacement; the one pair cannot separate
those explanations.

The screen decision is therefore `screen_did_not_trigger`, not a negative claim
about behavioral probes. No full multi-seed comparison is selected from this
result, and the target remains closed to further tuning.

## Evidence

- [Frozen preregistration](ORNITH-PROBE-OBLIGATION-SCREEN-PREREGISTRATION-2026-09-09.md)
- [Freeze manifest](runs/2026-09-09-ornith-probe-obligation-screen/freeze-manifest.json)
- [Control run](runs/2026-09-09-ornith-probe-obligation-screen/01-probe-optional-seed31/)
- [Treatment run](runs/2026-09-09-ornith-probe-obligation-screen/02-probe-required-seed31/)
- [External grader results](runs/2026-09-09-ornith-probe-obligation-screen/external-grader-results.json)
- [Post-run adjudication](runs/2026-09-09-ornith-probe-obligation-screen/post-run-adjudication.json)
- [Validated campaign record](runs/2026-09-09-ornith-probe-obligation-screen/independent-validation.json)
