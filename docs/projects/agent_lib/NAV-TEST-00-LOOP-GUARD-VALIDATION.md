# NAV-TEST-00 reasoning-loop-guard validation

**Date:** 2026-07-22  
**Result:** Stage A failed; do not integrate the v1 detector into the runtime.

## Integration finding

The motivating NAV-TEST-00 runs do not contain a model reasoning stream.
Their recorded configuration has `thinking_disabled=true`. Each model call
returns a short JSON action, while the control loop occurs across successive
agent tool calls. The 120K limit is cumulative prompt plus output usage across
calls, not one unbounded reasoning completion.

`llm_engines` currently streams plain text and has no typed reasoning-block
event contract. Building that contract now would not fix this failure: for
these runs it would emit no reasoning blocks. The decision for this track is:

> Do not add a typed reasoning event stream to `llm_engines` as part of the
> NAV loop fix. Keep the detector package experimental and unintegrated. A
> NAV fix must observe the typed action/tool trajectory in `agent_lib`.

The string/mapping fallback is therefore an adapter convenience, not the
approved NAV integration path.

## Replay method

The four schema-v2/sampled run records were replayed incrementally with the v1
defaults (4-grams, 96-token window, 24-token stride, 35% threshold, three
confirmations). Two candidate streams were checked:

1. exact decoded `planner_usage.calls[].response_text` values;
2. parsed action message + tool name + sorted tool arguments.

The replay is reproducible with
`reasoning_loop_guard/scripts/replay_nav_test_00.py`.

## Results

| Run | Outcome | Actual loop onset (manual trace review) | Decoded JSON first fire | Parsed action first fire |
|---|---:|---:|---:|---:|
| seed0 schema-v2 | token budget, 107,280 tokens | step 17 | step 12 / 34,098 tokens (**5 steps early**) | step 8 / 10,716 tokens (**9 steps early**) |
| sampled seed1 | token budget, 119,165 tokens | step 11 | step 12 / 55,994 tokens (**1 step late**) | step 10 / 43,595 tokens (**1 step early**) |
| sampled seed3 | token budget, 110,976 tokens | step 15 | step 8 / 15,862 tokens (**7 steps early**) | step 7 / 10,245 tokens (**8 steps early**) |
| sampled seed2 | **completed**, 53,494 tokens | none | step 9 / 15,716 tokens | step 7 / 7,079 tokens |

Manual onset means the first redundant return to already-inspected evidence,
not merely an overlapping but forward-moving file slice. This is necessarily a
human label; the run records contain no pre-existing loop annotation.

## Interpretation

The v1 defaults do fire before the budget wall, but that fact is not useful:

- all three failure runs fire prematurely on at least one candidate stream;
- the successful run also fires, yielding a 100% false-positive rate on the
  one available negative control;
- decoded JSON repeats schema keys and punctuation;
- parsed actions repeat normal tool names, paths, and argument structure while
  the agent is still moving through new line ranges.

Changing only the 35% threshold cannot repair the signal mismatch reliably.
The successful run crosses the same repetition band as failed runs.

## Required next design

The next candidate should live at the `agent_lib` control boundary and operate
on typed trajectory events, including at minimum:

- canonical tool name and normalized arguments;
- whether a read overlaps or duplicates an earlier read;
- whether a search/read added new evidence;
- repeated action signatures across steps;
- an explicit evidence-sufficiency/finalization signal.

It should be validated against these four records before runtime integration.
The text n-gram detector may remain useful for genuine long within-call
reasoning streams, but NAV-TEST-00 does not validate that use case.
