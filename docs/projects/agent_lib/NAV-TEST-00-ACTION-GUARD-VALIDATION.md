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
unchanged; it is the required mode for broader false-positive calibration.

## Scope and remaining risk

This result supersedes the text n-gram detector for NAV-class failures. It does
not validate the detector for arbitrary tools or long-running agents. In
particular, the warmup, range-overlap, novelty, and confirmation defaults were
selected against only four trajectories. The detector therefore remains an
experimental control. Broader successful-run shadow calibration remains
required before general runtime adoption outside NAV.
