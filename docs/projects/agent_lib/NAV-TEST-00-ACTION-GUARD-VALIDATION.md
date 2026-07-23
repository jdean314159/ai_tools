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

The first live deterministic seed-0 validation against candidate `c6c726a`
did not reproduce the historical trajectory. The guard did not fire and the
run exhausted its budget at 116,227 tokens with 11/12 evidence recall and no
answer. The loop returned to earlier reads outside the detector's trailing
12-action comparison window.

A follow-up candidate (`f7b9cf7`) treated a failed whole-file read followed by
a bounded line-1 retry as a near-duplicate. It fired at step 11 and finalized at
32,526 tokens, but this was a false positive on legitimate result-size recovery:
only 7/12 evidence regions had surfaced, evidence recall was 0.583, and answer
correctness was 0.667 (8/12), below the predeclared 11/12 floor. Its supposedly
truncated finalization prompt was also 96 tokens larger after context rebuilding
(`5302` versus `5206`), exposing that step truncation does not guarantee prompt
token savings under the current compaction policy. That detector change was
reverted in `8d66406`.

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

A deterministic seed0 shadow run at `fe06e04` reached the same live outcome as
the earlier `c6c726a` smoke run: 20 tool calls, 116,227 cumulative tokens,
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

Two additional seed0 shadow runs on the exact same `b201b6c` commit and pinned
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

## Scope and remaining risk

This result supersedes the text n-gram detector for NAV-class failures. It does
not validate the detector for arbitrary tools or long-running agents. In
particular, the warmup, range-overlap, novelty, and confirmation defaults were
selected against only four trajectories. The detector therefore remains an
experimental control. Broader successful-run shadow calibration remains
required before general runtime adoption outside NAV.
