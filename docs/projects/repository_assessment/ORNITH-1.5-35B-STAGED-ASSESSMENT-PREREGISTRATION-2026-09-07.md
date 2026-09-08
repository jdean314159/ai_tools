# Ornith 1.5 35B staged-assessment preregistration — 2026-09-07

Status: frozen before the first live staged-assessment request; campaign now
complete. See the
[result](ORNITH-1.5-35B-STAGED-ASSESSMENT-2026-09-07.md).

## Research question

On the same frozen target, model endpoint, seeds, hidden three-defect grader,
and 45-shell-call ceiling as the completed Ornith baseline, does a staged
prompt-and-controller treatment improve search coverage, evidence discipline,
calibration, or hidden-defect recall?

This is a treatment rerun against the three already-completed baseline seeds,
not a new model comparison. Historical internal status and project experiment
documents are masked from the model-visible sandbox so that disclosed defect
leads cannot substitute for independent discovery.

## Predictions recorded before execution

1. Median hidden-defect recall will remain 0/3. The treatment structures search
   and verification but does not supply the judgment needed to recognize the
   three grader defects.
2. Independently scored median substantive coverage will improve from the
   baseline's 1/9 to at least 8/9 because every package receives a fresh-context
   scout.
3. All three runs will complete the staged protocol without a shell-call cap
   binding, and median maximum package concentration will be no more than 1/3.
4. Median cumulative model input tokens will be less than half the baseline
   median of 1,648,791 because evidence is carried between short fresh contexts
   instead of repeatedly replaying one growing transcript.
5. Evidence precision and uncertainty calibration will improve, but no
   directional precision threshold is preregistered because the baseline has
   only four claims and two were supplied by an internal handoff now masked.

A staged median recall of at least 1/3, strictly greater than the paired
baseline median, contradicts prediction 1. Report the complete per-seed
distribution and adjudicate each prediction separately.

## Frozen constants

- Target commit:
  `83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532`.
- Target archive SHA-256:
  `e4bac3a08e16a0d4644e658b93d1bcd5ce5a77d7af4c49e0a63a3a07e52206d2`.
- Model label: `Ornith-1.5-35B-Q4_K_M.gguf`.
- llama.cpp build: `b10679-50f068fff`.
- User-reported endpoint boundary: Q4_0 key and value caches, flash attention,
  Jinja templates, `--spec-type draft-mtp`, and `--spec-draft-n-max 3`.
- Endpoint-observed boundary: four 262,144-token slots with speculative MTP
  active.
- Thinking off, temperature zero, and seeds 17, 31, then 47.
- The 45-unit investigation ceiling is preserved as 45 executed shell calls,
  because shell calls are the scarce empirical-work unit shared by the
  baseline and treatment. Model-only critic and synthesis calls are recorded
  separately and do not consume this ceiling.
- The defect identities, grader source and outcomes, prior model findings,
  prior trajectories, internal handoffs, and repository-assessment project
  documents are withheld from every model context until all reports are final.
- Complete all three valid runs. Do not tune prompts, stage budgets, selection,
  scoring, seeds, or endpoint parameters after the first live request.

## Treatment

### Scout stage

The controller assigns all nine package scopes in a seed-shuffled order. Each
scope starts with a fresh context and receives the same prompt template naming
only that scope. It may execute at most three shell calls and must submit either
one falsifiable candidate or `no_candidate` through a structured tool.

The scout must inspect production code and a distinct test, caller, README, or
package contract; trace a behavior end to end; state expected and observed
behavior; and attempt to disprove its own hypothesis. A scout may not emit more
than one candidate. Three calls across nine scopes reserve 27 of the 45 shell
calls.

### Candidate selection and verifier stage

The controller considers candidates in the already-seeded scope order and
selects the first six at most. There is no model-based ranking step and no
post-run selection discretion. Each selected candidate receives a fresh
verifier context, the structured scout claim, and at most three shell calls.
The verifier must return `confirmed`, `rejected`, or `insufficient_evidence`,
including direct evidence and a disconfirmation attempt. This reserves at most
18 shell calls and therefore keeps total executed shell calls at or below 45.

### Critic and synthesis stages

Every verifier-confirmed candidate goes to a fresh-context, no-shell evidence
critic. The critic sees only the structured claim and evidence and returns
`accept`, `reject`, or `insufficient_evidence`. It cannot add repository facts.

A final fresh-context synthesizer sees controller-owned coverage summaries and
critic decisions. It may narrate only critic-accepted findings and cannot add
findings. Independent scoring uses the structured accepted-finding records,
not any unsupported statement introduced by the narrative. The controller,
not the model, assigns final uncertainty: `high` below 8/9 substantive
coverage, `medium` at 8/9, and `low` only at 9/9.

## Measures and decision rules

Known-defect recall remains primary. Independent adjudication maps only
critic-accepted findings to the three frozen behaviors, requiring both the
affected behavior and relevant symbol or call path. Scores range from 0–3.

Secondary measures are validated false positives and precision, independently
normalized substantive coverage, maximum package shell-call concentration,
per-stage structured completion, whether the 45-call ceiling bound, executed
shell calls, model-only calls, input/output tokens, rejected and insufficient
candidates, protocol violations, and controller-assigned uncertainty.

Substantive coverage retains the baseline definition: at least one production
source read plus a distinct test, caller, README, or package contract read.
Coverage is adjudicated from exact commands and outputs; a scout's assertion
that it covered a scope is not sufficient.

The coverage prediction passes only if the staged median is at least 8/9 and
strictly greater than the paired baseline median. The completion prediction
passes only if all nine scouts return structured results and every selected
candidate receives a structured verifier result in all three runs, without 45
executed shell calls. The token prediction compares total tokens from scouts,
verifiers, critics, and synthesis against half the paired baseline median.

## Confirmed reusable surfaces

- The maintained experiment harness fixes the target identity, seed set, and
  nine package names at `tools/run_planner_assessment.py:34`.
- It defines the existing typed shell contract at
  `tools/run_planner_assessment.py:88`.
- Its output clipping implementation is reusable at
  `tools/run_planner_assessment.py:329`.
- Its bubblewrap construction already provides a read-only target, private
  temporary directory, unshared network, and target-first Python path at
  `tools/run_planner_assessment.py:343`.
- Its shell execution path enforces a 120-second command timeout and records
  exact command, output, clipping, return code, and latency at
  `tools/run_planner_assessment.py:419`.
- Its critic uses a fresh request, deterministic sampling, a strict JSON
  schema, and invalid-response downgrade at
  `tools/run_planner_assessment.py:557`.
- The external grader freezes the three objective behaviors at
  `tools/test_known_defects_at_83e1d09.py:56`,
  `tools/test_known_defects_at_83e1d09.py:75`, and
  `tools/test_known_defects_at_83e1d09.py:107`.

## Must be built (does not exist yet)

- The staged scout, verifier, critic, and synthesis orchestrator.
- Structured scout and verifier contracts plus deterministic candidate
  selection.
- Fresh-context lifecycle and per-stage budget enforcement.
- Sandbox overlays masking `docs/internal` and `docs/projects`, plus validation
  proving those overlays are empty while the target remains read-only.
- Relative-path normalization and treatment-specific coverage accounting.
- Exact stage transcripts, structured finding records, usage aggregation,
  independent adjudication, comparison summary, and campaign manifest.
- The eventual production `repository-assessment/v1` recorder remains deferred;
  this experiment must not define it implicitly.

## Invalidations

A run is invalid if the wrong target is mounted, the target is writable,
target imports resolve outside `/workspace`, the shell has non-loopback network
access, host fallback occurs, a masked historical document is visible, oracle
information reaches a model request, the endpoint configuration changes, a
stage exceeds its frozen shell budget, candidate selection is discretionary,
or any raw transcript is missing. Retain invalid attempts with their reasons.

The unavailable model-file digest and independently inspected remote process
argv remain explicit fingerprint omissions. They limit identity verification
but do not invalidate this matched rerun under the frozen design.
