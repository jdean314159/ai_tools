# Ornith adaptive staged assessment v2 plan — 2026-09-07

Status: accepted implementation and experiment plan. Phase 1 was authorized
by the repository owner on 2026-09-07. The frozen execution rules and
predictions are recorded separately in
`ORNITH-ADAPTIVE-STAGED-V2-PREREGISTRATION-2026-09-07.md`.

## Decision to test

Test whether deterministic orientation, evidence-linked hypotheses, and a
deeper verification pool improve repository-defect judgment without restoring
the context growth or package fixation seen in the autonomous baseline.

The work has two distinct phases:

1. a development round on the already-known `83e1d09` target to establish that
   the new harness works as designed; and
2. a confirmatory round on new blinded targets to test generalization.

The first phase cannot support a general recall claim. The harness design now
benefits from knowledge of the old trajectories and grader defects, making
`83e1d09` a development set. The second phase is the evidence-bearing result.

## Lessons carried forward

The first staged treatment established four useful facts:

- fresh package contexts reduced median cumulative input by 94.6%;
- deterministic package scopes reduced median maximum concentration from
  62.2% to 11.1%;
- median substantive coverage rose from 1/9 to 7/9; and
- hidden-defect recall remained 0/3 in every seed.

All 27 scouts and both selected verifiers used their complete three-call
budgets before the controller requested structured output. Most scouts spent
those calls on inventory, README, or initializer reads. Two proposed defects
were both false and were removed by the verifier/critic pipeline.

The next treatment therefore retains fresh contexts, isolation, and evidence
gates, while moving generic orientation out of the model's empirical budget
and concentrating the remaining budget on concrete hypotheses.

## Experimental conditions

### Condition A — staged v1 control

Run the existing staged harness unchanged. Do not substitute the already-run
v1 artifacts for the development comparison: run new paired controls against
the same live endpoint so endpoint drift and sequential timing do not become
unrecorded condition differences.

### Condition B — adaptive staged v2

Use the same model, target, endpoint configuration, seed, temperature, thinking
setting, sandbox, masked document paths, and 45-shell-call ceiling. Change only
the following treatment bundle.

#### 1. Deterministic package dossier

Before any model request, build one bounded dossier per package directly from
the frozen target. The generator must be syntax-driven and use the same rules
for every package. Each dossier contains:

- production module paths;
- module-level functions, classes, and class methods from Python ASTs,
  including private implementation symbols but excluding dunder methods;
- explicit package exports;
- test paths and literal references to production symbols;
- README headings; and
- package metadata paths.

It contains no defect labels, risk scores, historical findings, source-code
excerpts, grader information, or hand-authored package hints. Sort every list,
cap each category by a frozen rule, retain the exact JSON, and hash it. Dossier
generation is part of the treatment and does not consume model shell calls;
that information advantage must be stated in every comparison.

#### 2. Hypothesis selection gate

Each of nine fresh-context scouts receives only its package dossier and must
first call `select_hypothesis`, before shell access is enabled. The structured
selection names:

- one production symbol;
- one falsifiable invariant;
- one expected-behavior source path or an explicit `invariant_derived` label;
  and
- one disconfirmation plan.

Reject selections that name only a package, directory, glob, README, or
ordinary `__init__.py` export. A selected production path and symbol must occur
in the dossier. Rejection does not consume a shell call but is recorded and is
limited to two retries; failure after two retries yields `no_valid_hypothesis`.

#### 3. Shallow scout budget

Each valid scout receives at most two shell calls, for a campaign maximum of
18 breadth calls. The prompt assigns the calls distinct purposes:

1. inspect the selected implementation and the strongest available contract,
   caller, or test; and
2. trace or reproduce the behavior while actively looking for a guard or fact
   that disproves the hypothesis.

The scout then submits `supported`, `unresolved`, or `disproved`. It must
provide scalar evidence references: contract call ID and quote, behavior call
ID and quote, and disconfirmation call ID and result. A quote is accepted only
if it is an exact substring of output retained for that stage and the call ID
belongs to that scout. Invalid evidence downgrades the result to `unresolved`;
it does not become a candidate merely because its prose sounds confident.

#### 4. Deterministic promotion

Order hypotheses by disposition—`supported`, then `unresolved`—and break ties
using the seed-shuffled package order. Promote the first three. Do not use
severity, a model ranking call, grader-package knowledge, or post-run human
choice. `Disproved` and invalid hypotheses are retained but not promoted.

If fewer than three promotable hypotheses exist, the unused verifier budget
remains unused. Do not promote a disproved hypothesis merely to fill the
budget.

#### 5. Deep verifier budget

Give each promoted hypothesis a fresh context and at most nine shell calls,
for a campaign maximum of 27 verification calls. The verifier receives a
deterministic dossier slice containing the selected symbol, production module
map, symbol-referencing test paths, README headings, and metadata paths, plus
the structured hypothesis and validated evidence capsule—not the scout's
growing conversation.

The verifier must inspect the complete call path, locate the repository basis
for expected behavior, attempt a focused reproducer when feasible, and make a
strong disconfirmation attempt. Its structured result uses `confirmed`,
`rejected`, or `insufficient_evidence` and the same transcript-linked evidence
references as the scout.

#### 6. Evidence critic and deterministic report

Send each verifier-confirmed finding to the existing fresh-context, no-shell
critic only after the controller validates its evidence references. The critic
may accept, reject, or mark evidence insufficient; it cannot introduce facts.

Generate the authoritative final report deterministically from controller
records. A model-written narrative may be generated and retained as a
non-authoritative attachment, but its formatting failure cannot abort an
otherwise valid experiment and it cannot add findings. Controller-derived
uncertainty remains high below 8/9 coverage, medium at 8/9, and low only at 9/9.

## Fixed shell budget

| Stage | Workers | Calls per worker | Maximum |
|---|---:|---:|---:|
| Scouts | 9 | 2 | 18 |
| Verifiers | at most 3 | 9 | 27 |
| Critics | at most 3 | 0 | 0 |
| Report | 1 deterministic renderer | 0 | 0 |
| **Campaign ceiling** | | | **45** |

Model-only selection, critic, and optional narrative calls are counted and
token-metered separately. Rejected shell attempts do not consume the executed
shell-call ceiling but are reported as protocol violations.

## Phase 1 — development round

### Target and schedule

Use the existing frozen target and grader only as a development benchmark:

- target commit `83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532`;
- seeds 17, 31, and 47; and
- paired run order: v1-17, v2-17, v2-31, v1-31, v1-47, v2-47.

Fingerprint the endpoint before and after each pair. If the model, llama.cpp
build, cache settings, speculative-decoding settings, slot count, or context
boundary changes, invalidate and rerun both halves of that pair. Run no pairs
concurrently.

### Development gates

Phase 1 succeeds mechanically only if all three v2 runs satisfy all of these:

1. nine dossiers are deterministic and reproduce their retained hashes;
2. all valid scouts select a concrete production symbol before shell access;
3. every accepted evidence quote resolves exactly to its referenced tool
   output;
4. no run exceeds 18 scout, 27 verifier, or 45 total shell calls;
5. every promoted hypothesis receives a verifier result;
6. the authoritative report is reproducible without a model call; and
7. the target grader still fails and the corrected checkout still passes.

Behavioral development outcomes are reported but do not gate implementation:

- number and disposition of hypotheses;
- verifier launch rate;
- evidence-reference validity;
- recall against the known three defects;
- accepted false positives and precision;
- coverage, concentration, tokens, and elapsed time; and
- natural versus controller-forced completion at every stage.

Do not tune v2 after looking at seed-level defect recall. If a mechanical gate
fails, fix the harness, version the invalid attempt, reset the development
campaign, and rerun all pairs. If the mechanism works but recall remains zero,
advance unchanged to blinded confirmation rather than tuning against known
defects.

## Phase 2 — blinded confirmation

### Target construction

Before freezing the v2 prompt, an independent evaluator should prepare at
least two new historical targets with at least three objectively reproducible
defects each. Prefer defects that existed and were fixed independently of this
harness. For every target:

- freeze the commit and complete source-tree digest;
- write an external grader that fails every behavior on the target and passes
  every behavior on its corrected reference;
- retain exact target and reference outcomes;
- record defect identities in an evaluator-only artifact; and
- expose to the harness author only target identity, package list, defect
  count, and validation status until all model reports are final.

No target may be selected because its defects match the v2 prompts or dossier
output. Historical documentation, fix messages, project experiment reports,
and grader sources remain masked from the model.

### Confirmatory design

Run v1 and frozen v2 for seeds 17, 31, and 47 on both targets: twelve valid
runs total. Counterbalance condition order within each target and seed. Keep
the same endpoint configuration and invalidate complete pairs after material
server changes.

The primary outcome is known-defect recall, macro-averaged first within target
and then across targets. Report raw per-defect, per-seed values as well.
Secondary outcomes are precision, accepted false positives, evidence validity,
coverage, concentration, stage completion, shell calls, input/output tokens,
and elapsed time.

Freeze exact success thresholds in the Phase 2 preregistration after target
counts are known. The recommended directional rule is that v2 must improve
macro recall over v1 without increasing accepted false positives. Coverage or
token reduction alone cannot satisfy the task-success claim.

### Proposed predictions to freeze later

These predictions are drafts until the target set and preregistration are
sealed:

1. v2 will preserve median coverage of at least 6/9 and median maximum package
   concentration below 25%;
2. v2 median input will remain below 20% of the autonomous Ornith baseline;
3. evidence-linked verifier/critic gates will accept no more false positives
   than v1; and
4. v2 recall may remain unchanged despite better depth and evidence quality.

Prediction 4 is intentionally conservative. A recall increase on blinded
targets would be the first evidence that the harness improved judgment rather
than only control.

## Reliability-lab export

The experiment is strong course material because it separates three things
that fluent assessment reports commonly blur:

1. **The work can grade itself:** the external reproducers establish whether a
   known defect was recalled.
2. **A process proxy can improve while the outcome does not:** coverage,
   concentration, stopping, calibration, and token use improved while recall
   remained zero.
3. **Evidence gates can prevent shipping a wrong claim without finding the
   right claim:** both staged candidates were filtered, but no hidden defect
   was discovered.

### Export sequence

Do not make the reliability lab depend on an adjacent `ai_tools` checkout.
After the `ai_tools` evidence is committed and has stable Git identities:

1. create a draft course evidence packet, tentatively
   `EP-REPOSITORY-ASSESSMENT-CHECKABILITY`, containing bounded numeric
   observations and `ai_tools` Git source locators;
2. restate metrics rather than copy raw transcripts or source text;
3. include the preregistrations, result reports, adjudications, grader result,
   and manifests as separately identified sources;
4. record that the v1/v2 development target is not generalization evidence;
5. perform disclosure review for paths, endpoint details, prompts, source
   excerpts, and model-generated text;
6. obtain independent verification of source identity, metric transcription,
   packet validation, and digest; and
7. keep the packet `draft` until those checks and the teaching-placement
   decision are complete.

The first learner-facing exercise should reveal the objective recall score
after showing the improved process metrics. The learner's decision is whether
the green proxy metrics justify shipping the assessment. The intended answer
is no: they demonstrate control of the process, not correctness of the
findings.

### Reliability-lab decisions requiring authorization

The following are escalated under that repository's governance and are not
decided by this plan:

- whether this becomes an M0 supplemental case, a later-module anchor, or only
  a draft evidence packet;
- any title, order, status, or governing specification for M1–M8;
- whether a new incident-log entry should name coverage-as-success as a
  false-pass surface; and
- whether the evidence-packet schema needs any new value kind or source
  relationship.

Prefer representing the current measurements with existing `count`,
`count_of_total`, and percentage value kinds. Do not change the packet schema
unless an actual observation cannot be represented faithfully.

## Confirmed reusable surfaces

### `ai_tools`

- The staged harness already imports the frozen target identity, package set,
  and seed set and fixes the current 45-call ceiling at
  `tools/run_staged_assessment.py:33`.
- Its scout, verifier, and synthesis tool contracts demonstrate the available
  scalar `ToolParameterSchema` surface at
  `tools/run_staged_assessment.py:91`.
- `ScopeTrace` and the relative-path normalizer already retain per-scope
  executed commands and derive coverage evidence at
  `tools/run_staged_assessment.py:212` and
  `tools/run_staged_assessment.py:249`.
- The sanitized bubblewrap wrapper masks internal and project documents after
  the read-only target mount at `tools/run_staged_assessment.py:284`; its
  validation checks the base sandbox and both masks at
  `tools/run_staged_assessment.py:329`.
- The generic empirical stage already creates fresh messages, records exact
  prompts/responses/tool results, enforces stage and campaign shell budgets,
  and distinguishes structured output before forcing at
  `tools/run_staged_assessment.py:443`.
- The existing fresh-context critic accepts only supplied evidence and
  downgrades invalid JSON at `tools/run_planner_assessment.py:557`.
- The current deterministic fallback shows that an authoritative report can be
  rendered without model judgment at `tools/run_staged_assessment.py:624`.
- Run metadata already records target identity, endpoint fingerprint, scope
  distribution, coverage, stage records, tokens, completion, prompt hashes,
  transcript/report hashes, and sandbox validation at
  `tools/run_staged_assessment.py:854`.
- `OpenAIEngine.generate_with_tools()` forwards typed tool schemas, temperature,
  seeds, and local thinking preference at
  `../../../llm_engines/src/llm_engines/backends/openai.py:301`.
- The maintained grader provides three objective behavior checks at
  `tools/test_known_defects_at_83e1d09.py:56`,
  `tools/test_known_defects_at_83e1d09.py:75`, and
  `tools/test_known_defects_at_83e1d09.py:107`.
- Existing focused tests cover sandbox overlay order, path normalization,
  deterministic candidate selection, controller uncertainty, and a complete
  no-candidate run at `../../../tests/test_repository_assessment_staged.py:77`.

### `llm-reliability-lab`

- Course evidence packets already define stable sources, typed observations,
  bounded summaries, limitations, disclosure review, and digests in
  `../../../../llm-reliability-lab/docs/planning/ADR-001-course-durable-artifacts.md:111`.
- Git sources require an exact 40-character commit plus path, so the export must
  wait for committed `ai_tools` evidence:
  `../../../../llm-reliability-lab/docs/planning/ADR-001-course-durable-artifacts.md:151`.
- Existing packet machinery supports `count`, `count_of_total`, percentages,
  and labels at
  `../../../../llm-reliability-lab/scripts/evidence_packets.py:15`.
- Student-facing content must be standalone and cannot resolve an adjacent
  `ai_tools` checkout:
  `../../../../llm-reliability-lab/AGENTS.md:56`.
- Evidence claims must distinguish measurement, inference, forecasts, and
  causal attribution, and public run evidence requires disclosure review:
  `../../../../llm-reliability-lab/AGENTS.md:67` and
  `../../../../llm-reliability-lab/AGENTS.md:109`.
- The course authoring rule requires translating the experiment into the
  learner's decision rather than its implementation history:
  `../../../../llm-reliability-lab/docs/AUTHORING.md:7`.

## Must be built (does not exist yet)

- A deterministic AST/package-dossier generator, schema, hash, and fixture
  tests.
- The pre-shell `select_hypothesis` state and two-retry validator.
- A scout result contract with `supported`, `unresolved`, and `disproved`.
- Transcript-linked evidence references and exact-substring validation.
- Deterministic promotion across supported and unresolved hypotheses.
- A nine-call verifier stage that preserves the global 45-call ceiling.
- A deterministic authoritative report renderer separated from optional model
  narrative.
- Condition-versioned metadata so v1 and v2 cannot be silently mixed.
- Endpoint before/after-pair fingerprint comparison and invalidation logic.
- Phase 1 paired-run orchestration and independent adjudication.
- Independently selected Phase 2 targets, graders, blind oracle handling,
  counterbalanced orchestration, and macro-recall scoring.
- A disclosure-reviewed, independently verified reliability-lab evidence
  packet after the source evidence has immutable Git identities.
- Any learner-facing case, module-spec change, or incident entry, all of which
  require separate reliability-lab authorization.

The deferred production `repository-assessment/v1` profile is not required for
either phase and must not be introduced implicitly by this experiment.

## Assumptions to verify before preregistration

- The Ornith endpoint can remain unchanged and idle for six paired development
  runs; otherwise pair invalidation may make the schedule impractical.
- Python AST extraction covers the syntax used in every frozen package and can
  enforce deterministic size caps without manual exceptions.
- Exact output-substring references remain viable after the harness's 24,000
  character clipping policy; if not, evidence must reference retained full
  bytes rather than silently accepting clipped-away text.
- Three nine-call verifiers fit the model endpoint's practical context and
  timeout limits.
- An independent evaluator can supply at least two new target/reference/grader
  sets without revealing defect identities to the harness author.
- The reliability-lab packet can faithfully represent every selected metric
  with its existing value kinds; no schema change is assumed.

## Implementation order

1. Write dossier schema/generator tests, then implement deterministic dossier
   generation.
2. Add hypothesis-selection and evidence-reference validators with fake-engine
   tests for rejection, retry, clipping, and cross-stage call-ID misuse.
3. Add the 18/27 adaptive scheduler and test every budget boundary.
4. Replace authoritative model synthesis with deterministic rendering; retain
   optional narrative separately.
5. Add condition versioning, pair fingerprint checks, invalid-attempt
   retention, and campaign summaries.
6. Run focused tests, full `make test-all`, Python quality, documentation-link,
   decision-history, publication-hygiene, JSON/JSONL, and manifest checks.
7. Write and freeze the Phase 1 preregistration; only then contact Ornith.
8. Complete and adjudicate all six development runs without tuning.
9. Freeze the v2 implementation, obtain blinded targets, and write a separate
   Phase 2 preregistration.
10. After confirmatory evidence is final and committed, prepare the draft
    reliability-lab packet and request the required independent verification
    and curriculum-placement decision.

## Stop rules

- Stop before live execution if dossier hashes are nondeterministic, evidence
  references can cross stage boundaries, any budget path can exceed 45 calls,
  or masked documents are visible.
- Retain and invalidate—not overwrite—any run affected by target, sandbox,
  endpoint, oracle, or artifact failure.
- Complete every valid paired run once a phase begins; do not stop on a
  favorable recall result.
- Do not modify v2 between paired Phase 1 runs or between Phase 2 targets.
- If Phase 1 mechanical gates fail, return to implementation. If mechanics pass
  and recall remains zero, advance the unchanged treatment to blinded
  confirmation or stop the research line; do not tune further on `83e1d09`.
