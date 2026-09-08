# Qwen3-Coder planner rerun preregistration — 2026-09-06

Status: frozen design; confirmatory campaign completed 2026-09-07. See the
[comparison result](QWEN3-CODER-30B-A3B-PLANNER-COMPARISON-2026-09-07.md).

## Research question

Does deterministic coverage planning plus a separate critic improve repository
coverage, natural termination, or known-defect recall for the same model,
target, tools, and investigation budget?

The completed seed-7 baseline is a development observation and is excluded
from the confirmatory comparison. The comparison consists of six new runs:
three baseline runs and three planner runs, paired by seed.

## Prediction recorded before the run

1. Coverage will improve because a controller assigns package scopes and
   records their completion.
2. Natural termination will improve because the ledger supplies a finishing
   condition outside the investigator's unaided judgment.
3. Median known-defect recall will remain 0/3 because the scaffold controls
   search and stopping but does not itself supply defect judgment.

A planner median of at least 2/3 recalled defects, strictly greater than the
baseline median, will contradict prediction 3. Better coverage with unchanged
recall will replicate the earlier NAV result in a second domain with an
objective defect grader.

## Frozen constants

- Target commit:
  `83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532`.
- Model label:
  `Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf`.
- Thinking: off. Temperature: zero. Investigation budget: 45 turns.
- Server cache boundary: Q4_0 key cache, Q4_0 value cache, flash attention
  enabled, Jinja templates enabled, and no speculative-decoding flags. Hold
  this constant for all six runs.
- Paired seeds: 17, 31, and 47.
- Run order: baseline-17, planner-17, planner-31, baseline-31,
  baseline-47, planner-47.
- Base assessment prompt, shell contract, report requirements, read-only
  bubblewrap boundary, private `/tmp`, network isolation, and no-host-fallback
  policy remain unchanged.
- The three defect identities and grader results are withheld from every model
  context, planner message, and critic context until each report is final.
- No 90-turn condition is part of this campaign. Changing the turn cap is a
  separate experiment.
- Changing the KV cache type is also a separate experiment. A later matched
  Q4_0 versus Q8_0 or F16 campaign may test cache effects, but these six runs
  cannot support that causal claim.

Before the first run, retain the model file digest, `llama-server` build
identity, complete launch arguments, endpoint-reported model metadata, and
target-tree digest. If any cannot be captured, record an explicit omission.
Restarted or materially reconfigured server state invalidates the unmatched
half of a seed pair; rerun both halves and retain the invalid attempts.

## Conditions

### Baseline

Use the archived harness behavior without search guidance. Add only a required
structured `remaining_uncertainty` value (`low`, `medium`, or `high`) to the
report tool. This addition is applied identically to both conditions and does
not expose grader information.

### Planner

Use the same base prompt and tools, with a deterministic controller that:

1. assigns all nine package scopes listed by the root README: `agent_lib`,
   `llm_engines`, `llm_harness_core`, `llm_inspector`, `engram`, `rag_lib`,
   `llm_inspector_ui`, `action_trajectory_loop_guard`, and `mail_lib`;
2. maintains a controller-owned coverage ledger not editable by the model;
3. marks a scope substantively covered only after the transcript shows one
   production source read and one distinct caller, test, or contract read;
4. permits at most five shell calls on one hypothesis before requesting an
   explicit keep, reject, or defer decision;
5. reserves enough turns to expose at least eight package scopes before allowing
   a low-uncertainty report; and
6. sends every proposed finding to a fresh-context critic using the same served
   model. The critic receives the claim and gathered evidence, has no shell
   tool, and returns `accept`, `reject`, or `insufficient_evidence` with a short
   rationale. The investigator may report only critic-accepted findings.

Critic calls do not consume the 45 investigation turns, but their count and
tokens are recorded separately. A maximum of three critic calls is allowed per
run. The controller must not mention defect names, affected packages, fix
commits, grader behavior, or any other oracle information.

## Measures and decision rules

Known-defect recall is the primary outcome. After a report is final, an
independent scorer maps its validated findings to the three frozen grader
defects. A defect counts only when the report identifies the affected behavior
and relevant symbol or call path; vague package-level suspicion does not count.
Each run scores 0–3. False positives and precision are also reported; precision
is undefined when the report has zero validated findings.

Secondary process outcomes are:

- substantive package coverage out of nine;
- maximum concentration of shell calls in one package scope;
- natural versus forced completion;
- investigation shell calls and critic calls;
- model-reported remaining uncertainty; and
- whether the 45-turn cap bound.

The coverage prediction passes only if all three planner runs cover at least
8/9 scopes, no planner run assigns more than 40% of shell calls to one scope,
and planner median coverage exceeds baseline median coverage. The termination
prediction passes only if at least two planner runs submit naturally and the
planner natural-completion count exceeds baseline. A `low` uncertainty claim
with coverage below 8/9 is scored as an overconfidence event regardless of
recall.

Report all per-run values and medians. Do not collapse a mixed result into a
single planner-wins label. The recall prediction, coverage prediction, and
termination prediction are adjudicated separately.

## Confirmed reusable surfaces

- The archived harness already defines the frozen prompt and shell/report tool
  schemas at
  `runs/2026-09-06-qwen3-coder-30b-a3b/assessment-harness.py.raw:23` and
  `runs/2026-09-06-qwen3-coder-30b-a3b/assessment-harness.py.raw:54`.
- Its bubblewrap argument construction enforces the target mount, private
  temporary directory, network namespace, and environment at
  `runs/2026-09-06-qwen3-coder-30b-a3b/assessment-harness.py.raw:105`.
- It already records every assistant response, shell result, usage value, and
  completion mode at
  `runs/2026-09-06-qwen3-coder-30b-a3b/assessment-harness.py.raw:285` and
  `runs/2026-09-06-qwen3-coder-30b-a3b/assessment-harness.py.raw:372`.
- `OpenAIEngine.generate_with_tools()` accepts the typed request and tool list
  required by the harness at
  `../../../llm_engines/src/llm_engines/backends/openai.py:301`.
- The external grader fixes the three scored behaviors in executable tests at
  `tools/test_known_defects_at_83e1d09.py:56`,
  `tools/test_known_defects_at_83e1d09.py:75`, and
  `tools/test_known_defects_at_83e1d09.py:107`.

## Must be built (does not exist yet)

- The deterministic scope scheduler and controller-owned coverage ledger.
- Transcript labeling that supports unambiguous per-scope call counts.
- The five-call hypothesis budget and keep/reject/defer transition.
- The isolated critic request, response validator, and separate usage record.
- The shared structured uncertainty field for both conditions.
- The independent finding-to-defect adjudication record and campaign summary.
- The eventual `repository-assessment/v1` recorder. This campaign must not
  invent that production schema before its explicit profile draft is accepted.

## Invalidations and stopping

A run is invalid if the target is writable, host fallback occurs, network is
available inside the shell, target imports resolve outside `/workspace`, grader
information reaches a model context, the wrong commit is mounted, the served
model or launch configuration changes within an unmatched pair, or a required
raw transcript is missing. Retain invalid attempts with the reason.

Complete all six valid runs. Do not stop early for a favorable or unfavorable
result. Do not tune controller rules, scoring mappings, prompts, seeds, or the
defect list after the first run.
