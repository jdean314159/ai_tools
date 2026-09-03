# NAV-TEST-00 action-trajectory-loop-guard validation

**Date:** 2026-07-22  
**Result:** The declared four-run detector gate and deterministic control-hook gate passed;
the integration remains experimental.

## Detector policy

The v2 detector consumes serialized or live `AgentStep` objects. It ignores
reasoning text and examines tool name, normalized arguments, returned evidence,
and action order.

An intervention requires:

- at least eight tool actions of warmup;
- two consecutive low-novelty actions that either duplicate one another or are
  each near-duplicates of recent actions;
- no more than 10% novel returned evidence on either confirming action;
- comparison only against the trailing 12 tool actions.

For `read_file`, near-duplicate means the same canonical path and at least 50%
range overlap. Evidence is tracked as `(path, line)` coordinates. `grep` and
`list_files` use normalized arguments plus evidence coordinates or returned
paths. Result-limit arguments do not make an otherwise identical search novel.

The eight-action warmup prevents a known false positive: successful sampled
seed2 makes repeated oversized-read attempts at steps 3–5, then recovers and
finishes. This is a calibration assumption that needs more negative controls.

## Replay results

| Run | Recorded outcome | First intervention | Loop boundary | Result |
|---|---:|---:|---:|---:|
| seed0 schema-v2 | token budget at 107,280 | step 18 / 107,280 tokens | step 17 | pass |
| sampled seed1 | token budget at 119,165 | step 11 / 49,765 tokens | step 10 | pass |
| sampled seed3 | token budget at 110,976 | step 15 / 61,614 tokens | step 14 | pass |
| sampled seed2 | completed at 53,494 | none | none | pass |

All failure interventions occur before the 120K cumulative limit. The
successful control does not fire. Replay is reproducible with
`action_trajectory_loop_guard/scripts/replay_nav_test_00.py`.

## Runtime integration gate

`build_navigation_harness` now installs an `ActionTrajectoryGuardHook` after
each completed tool step. On detection, `AgentRuntime`:

1. retains every original `AgentStep` for audit;
2. builds separate full and prefix-only contexts with empty tool specs;
3. calls `BudgetedNavigationPlanner.finalize()` at most once;
4. uses a final-only system prompt and JSON schema;
5. rejects malformed, message, or tool-seeking responses without invoking a tool;
6. skips the model call when prompt plus minimum output reserve cannot fit;
7. records the discarded half-open step range, exact tokenizer prompt counts,
   token savings, budget availability, and outcome in `run.meta["action_guard"]`.

Deterministic tests cover successful finalization, a non-final response, and
budget-unavailable preflight with zero engine calls. The stored run records can
replay detection and discarded-step boundaries, but cannot establish the
quality of an answer that was never generated. A live NAV rerun is required to
measure final-answer quality and realized end-to-end token savings.

The runner exposes and records three modes: `off`, `shadow`, and `enforce`.
Shadow mode records a would-fire boundary while leaving the planner trajectory
unchanged; it is the default and the required mode for broader false-positive
calibration.

## Live enforcement smoke test — failed

The first live deterministic seed-0 validation against candidate `9668ec8`
did not reproduce the historical trajectory. The guard did not fire and the
run exhausted its budget at 116,227 tokens with 11/12 evidence recall and no
answer. The loop returned to earlier reads outside the detector's trailing
12-action comparison window.

A follow-up candidate (`869c46d`) treated a failed whole-file read followed by
a bounded line-1 retry as a near-duplicate. It fired at step 11 and finalized at
32,526 tokens, but this was a false positive on legitimate result-size recovery:
only 7/12 evidence regions had surfaced, evidence recall was 0.583, and answer
correctness was 0.667 (8/12), below the predeclared 11/12 floor. Its supposedly
truncated finalization prompt was also 96 tokens larger after context rebuilding
(`5302` versus `5206`), exposing that step truncation does not guarantee prompt
token savings under the current compaction policy. That detector change was
reverted in `3981e40`.

The remaining sampled enforcement runs were not launched after the smoke gate
failed. Active enforcement is therefore not validated and must remain opt-in.
Replay-fidelity instrumentation is now the first gate. Each guarded live run
records the exact canonical action supplied to the detector plus its comparison
window, duplicate matches, evidence atom counts, novelty, redundancy decision,
and proposed intervention under `run.meta.action_guard.detector_trace`. The
replay utility consumes this captured stream directly and reports any decision
mismatch. Older run records without this field still use reconstructed steps,
but that path is explicitly labeled and is not considered fidelity evidence.

Interpret the next shadow runs in this order:

1. Verify that direct replay of captured detector input reproduces every live
   decision.
2. Diff captured input against reconstruction from the general run record.
3. Only if direct replay is exact, attribute cross-run trajectory differences
   to model/runtime nondeterminism and begin detector calibration.

After that fidelity gate, run shadow mode over broader trajectories and
separate legitimate size-recovery retries from true evidence-free cycles.
Prompt selection also needs an evidence-centric budget representation before
token savings can be claimed.

### Captured-input shadow result

A deterministic seed0 shadow run at `9badf67` reached the same live outcome as
the earlier `9668ec8` smoke run: 20 tool calls, 116,227 cumulative tokens,
11/12 evidence regions, no final answer, and no detector intervention. Direct
replay reproduced all 20 detector decisions, and reconstruction from the
general run-record steps reproduced all 20 captured canonical actions.

The first capture attempt exposed a schema-v1 instrumentation defect: dropping
non-tool steps from the captured stream renumbered later sequence offsets, so
direct replay disagreed from check 4 onward even though reconstructed actions
matched. Schema v2 retains `_detector_sequence_offset`; the corrected run has
zero decision or reconstruction mismatches. This is why captured-input replay
must itself be gated before its results are trusted.

For the corrected run, the replay adapter is not the source of the historical
seed0/live disagreement. The historical and current live trajectories differ:
after ignoring an explicit `full=false`, their first tool-argument divergence
is action 10 (`pipeline.py`, 150 historical lines versus 200 live lines), and
the historical trace has 17 tool actions versus 20 live actions. Historical
replay therefore remains useful as a frozen regression fixture, but it cannot
predict detector behavior on a newly generated trajectory, even with the same
decoding seed. Calibration data must come from live shadow runs captured under
the code and environment being evaluated.

Two additional seed0 shadow runs on the exact same `fdac861` commit and pinned
server configuration produced identical canonical action streams, semantic
planner outputs, per-call input/output token counts, final outputs, and guard
decisions. Only latency metadata differed. Under this configuration, seed0 does
pin the observed trajectory across repeated runs. The historical divergence
therefore demonstrates input/environment drift across repository versions, not
run-to-run sampling nondeterminism. Per-seed validation is meaningful only when
the repository snapshot, prompt construction, model/server build, and decoding
configuration are all held fixed.

Prefix evidence scoring explains the live detector miss. Coverage reached
7/12 regions at action 7, 9/12 at action 14, and 11/12 at action 17 (84,403
cumulative tokens). Actions 18–20 added no ground-truth region while consuming
31,824 more tokens. The missing region was `pipeline.py:766–794`, beyond the
last successful read ending near line 696. Actions 10–17 were mostly genuinely
high-novelty progressive reads, while the final three actions were heterogeneous:
a zero-novelty listing, a failed whole-file read, and a zero-novelty bounded
read. They never formed the two consecutive low-novelty near-duplicate actions
required by the detector.

This establishes live detection recall of 0/1 for the current failure and
shows that threshold tuning alone cannot cover it. The current signal detects
repetitive action loops; this trajectory instead exhibits continued heterogeneous
navigation after evidence saturation. A separate experimental signal should
model sustained evidence-coverage plateau plus budget consumption, without
assuming that a loop signal alone proves evidence sufficiency.

## Counterfactual evidence-centric finalization

The recorded trajectory was finalized without tools at two cutoffs using the
same deterministic evidence compactor and final-only schema:

- action 17, the forced 70%-budget baseline: 84,403 tokens consumed and 35,597
  remaining;
- action 19, after two zero-novelty actions: 106,361 consumed and 13,639
  remaining.

The final evidence prompt was 5,130 tokens, so both cutoffs safely allowed the
same 2,048-token output cap. Both produced the same deterministic answer. The
novelty gate therefore suppressed the productive action 17 without making
finalization budget-infeasible at action 19.

Context construction materially affected the result. A first compact prompt
omitted enclosing symbol headers and recovered 8/11 surfaced regions. Retaining
observable enclosing class/function headers improved this to 10/11. One final
prompt-only checklist recovered all 11 surfaced regions (evidence-conditioned
recall 1.0), 11/12 full recall, and no unsupported path.

The strict intervention gate nevertheless failed. The answer still included
the explicitly excluded retrieval-only `get_collection` operation and inferred
an unobserved `self._store.add` call site. Those are semantic precision failures
that the path/required-term scorer does not capture. Prompt search stopped at
this predeclared point rather than tuning further against the answer key.

Conclusion: compact evidence-centric finalization is budget-feasible and can
recover the surfaced answer set, but trustworthy claim precision is not yet
validated. Detector enforcement must remain disabled. A future attempt would
need structured, evidence-linked claims with deterministic validation, not
another free-form prompt revision. Until then, forced budget-fraction
finalization can only be described as experimental harness assistance.

### Production-builder revalidation — failed

The task-specific counterfactual compactor was not promoted into runtime. A
de-oracled production candidate instead built a lossless ledger of every unique
successful `(path, line, text)` observation, plus path-only evidence. It used no
task keywords, answer-key fields, relevance ranking, or trajectory-prefix
reconstruction. Overlapping reads collapsed to 1,061 unique observed source
lines.

At action 17 the exact prompt was 14,183 tokens. It fit within the remaining
35,597-token cumulative budget and 40K context window, but the generated answer
recovered only 10/11 surfaced regions (0.909 evidence-conditioned recall) and
10/12 overall. It omitted the observed pipeline `ChromaStorage` construction
and still described indirect `_embed_and_store` calls as mutation call sites.
The finalization consumed 15,209 tokens, yielding approximately 16,615 tokens
(14.3%) savings relative to the 116,227-token failed run.

At action 19 the same 14,183-token prompt exceeded the 13,639 tokens remaining
before even reserving output, so finalization correctly failed budget preflight.
This also confirms that a novelty delay cannot safely accompany the lossless
builder.

Per the predeclared gate, the production port stopped before runtime-hook
integration: answer quality materially regressed from the task-specific
counterfactual's 11/11 surfaced recall, and semantic precision remained
unvalidated. No `BudgetFractionFinalizationHook` was installed. The lossless
ledger and counterfactual evaluator remain experimental research artifacts;
NAV runtime defaults and enforcement behavior are unchanged.

## Structured-claim measurement correction

The original NAV answer scorer is retired as a trusted correctness instrument.
It searched each region's required terms across the entire free-form answer, so
terms from unrelated paragraphs could validate a region and a fabricated symbol
such as `RAGPipeline.ingest_file` could escape detection.

NAV now defines structured `NavigationClaim` and `EvidenceRef` contracts. The
claim-aware scorer requires, per claim:

- an exact expected path and symbol;
- non-empty operation and classification;
- line references wholly contained in successful observed tool evidence;
- region overlap at those referenced lines;
- required answer terms within that claim only, not elsewhere in the answer;
- exactly one matched ground-truth region and no duplicate claims.

Unsupported, duplicate, malformed, and unobserved-evidence claims are reported
separately. A run without structured claims receives a
`missing structured navigation claims` validation error and cannot pass, though
its legacy prose remains stored and readable. This intentionally means existing
historical run scores are legacy measurements, not retroactively trusted claim
scores.

This change corrects measurement only. The planner still emits free-form final
answers, so no autonomous run can yet pass the structured-claim gate. Planner
output-schema adoption and live validation are a separate next stage; per-step
information-goal tracking remains later work.

### Structured planner-output adoption — contract passed, live gate failed

NAV planner and constrained-finalizer schemas now require
`navigation_claims`. Claims survive payload conversion in final-action metadata,
and malformed claim arrays fail validation. Deterministic contract tests pass.

The first sampled seed2 live control demonstrated why exact evidence references
matter. It completed at 40,462 tokens with 11/12 evidence recall, but only 7/12
claims validated. Three claims cited whole method ranges after observing only
sparse grep hits, and one used the fabricated symbol
`RAGPipeline._store.add call site`. The scorer correctly rejected all four.

The protocol was corrected once to require minimal exact references
(single-line references for grep hits), exact visible enclosing symbols, and
additional inspection rather than symbol invention. A second sampled seed2
control emitted six clean, supported claims with no validation errors or
unsupported claims, but prematurely finalized after inspecting only
`chroma.py`: evidence recall was 7/12, claim correctness 6/12, 20,864 tokens,
and all pipeline information goals remained unresolved. It also omitted the
observed `ChromaStorage.__init__` initialization claim.

Because these are sampled runs, their trajectories are not direct quality
comparisons. Together they establish that the structured-output contract works
and the corrected scorer detects the intended defect classes. They do not
establish complete navigation. The live gate therefore fails at the next
architectural boundary: the planner has no explicit required/open/resolved
information-goal state and can terminate with entire requested categories
unexamined. Further final-answer prompt tuning is stopped. Per-step goal-ledger
work requires a separate structured-navigation specification and evaluation
track; autonomous NAV-TEST-00 remains failed.

## Scope and remaining risk

This result supersedes the text n-gram detector for NAV-class failures. It does
not validate the detector for arbitrary tools or long-running agents. In
particular, the warmup, range-overlap, novelty, and confirmation defaults were
selected against only four trajectories. The detector therefore remains an
experimental control. Broader successful-run shadow calibration remains
required before general runtime adoption outside NAV.
