# Qwen3-Coder KV-cache comparison preregistration — 2026-09-07

Status: frozen design; comparison completed 2026-09-07. See the
[comparison result](QWEN3-CODER-30B-A3B-KV-CACHE-COMPARISON-2026-09-07.md).

## Research question

Does changing only the llama.cpp key/value cache representation from Q4_0 to
Q8_0 materially change Qwen3-Coder's objective repository-assessment result on
the frozen `ai_tools` target?

This experiment reuses all three completed baseline Q4_0 runs from the planner
comparison as a fixed control and adds one matched Q8_0 run for each seed. The
control selection includes every baseline seed from that campaign; no control
run was selected or excluded based on its outcome.

## Prediction recorded before Q8_0

Q8_0 may change individual tokens, tool trajectories, and latency, but median
known-defect recall is predicted to remain 0/3. The evidence so far points to
search allocation and defect judgment as the dominant failures, and increased
KV precision does not directly supply either capability.

Q8_0 will contradict this prediction only if its median recall is at least 1/3
and it improves recall over Q4_0 in at least two of the three paired seeds. A
different transcript or package path without improved scored outcomes is
behavioral sensitivity, not task-quality improvement.

## Frozen constants

- Model file:
  `Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL.gguf`.
- Target commit:
  `83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532`.
- Target archive SHA-256:
  `e4bac3a08e16a0d4644e658b93d1bcd5ce5a77d7af4c49e0a63a3a07e52206d2`.
- llama.cpp build: `b10679-50f068fff`.
- Conditions: Q4_0 for both K and V versus Q8_0 for both K and V.
- Flash attention enabled, Jinja enabled, no speculative decoding.
- Four slots, 262,144-token context reported for each slot.
- Baseline condition only: no planner and no critic.
- Paired seeds: 17, 31, and 47.
- Temperature zero, thinking off, 45 investigation turns.
- Prompt SHA-256:
  `061a04a30f4620082cf0d4ff134cec0369dd8ec77f14b34abe30d682556769cc`.
- Harness SHA-256:
  `8f07bb772896554b37056fb16cf2696c246fcb56971d0ae1549a2da6ebe57972`.
- Same read-only bubblewrap target, private `/tmp`, isolated network namespace,
  package import paths, output clipping, tool schemas, and forced-report rule.

The Q8_0 launch command must differ from the Q4_0 command only in:

```text
--cache-type-k q8_0 --cache-type-v q8_0
```

Cache types are not exposed by the observed `/props`, `/slots`, or `/v1/models`
responses. The Q8_0 fingerprint therefore records them as user-reported launch
arguments and separately records endpoint-observed build, model, context, slot,
and speculation state. The remote model digest and server executable digest
remain unavailable unless newly supplied.

## Frozen Q4_0 control

The selected controls and their hashes are recorded before Q8_0 in
`runs/2026-09-07-qwen3-coder-30b-a3b-kv-cache-comparison/q4-control-selection.json`.
They are the baseline seed-17, seed-31, and seed-47 runs under the completed
planner comparison's `confirmatory/` directory.

Those metadata files independently agree on the model label, target commit,
prompt digest, temperature, thinking setting, turn budget, llama.cpp build, and
Q4_0 K/V launch record. Their report and transcript hashes are already pinned
inside each metadata file.

## Measures and decision rules

Known-defect recall is primary. The same independent scorer maps each report to
the same three external grader defects. A defect counts only when the report
identifies both affected behavior and the relevant symbol or call path. Each
run scores 0–3.

Also report per run and condition:

- validated findings, false positives, and precision, with precision undefined
  when no validated finding exists;
- natural or forced completion and whether the turn cap bound;
- shell calls, turns, cumulative input/output tokens, and elapsed wall time;
- package call distribution and maximum package concentration;
- model-reported remaining uncertainty; and
- substantive package coverage.

Report both the harness-recorded coverage and an independently corrected value.
The existing harness recognizes only package-local tests, README files, and
`pyproject.toml` as corroboration. The frozen preregistered interpretation also
counts a distinct root-level test or caller when its captured content imports
the package or names the inspected symbol/call path. Every correction must list
the production and corroborating paths; do not infer coverage from a test
command alone.

Q8_0 is a material improvement only under the recall threshold above. Secondary
metrics are descriptive and must not be combined into an undeclared composite
score. If recall is unchanged but false positives increase, report a regression
in precision rather than calling the result neutral. If outputs differ while
all adjudicated outcomes remain the same, report sensitivity without measured
quality improvement.

## Confirmed reusable surfaces

- Target identity, turn budget, and seeds are constants in
  `tools/run_planner_assessment.py:34`–`40`.
- The exact prompts and report contract are defined at
  `tools/run_planner_assessment.py:53`–`118`.
- The bubblewrap read-only mount, private temporary directory, environment, and
  isolated namespace are constructed at
  `tools/run_planner_assessment.py:357`–`415`.
- Sandbox validation checks import origins, repository writability, temporary
  storage, and network interfaces at
  `tools/run_planner_assessment.py:453`–`475` and the continuation of that
  function.
- Baseline generation fixes temperature, thinking, seed, and tools at
  `tools/run_planner_assessment.py:699`–`710`.
- Shell results and complete assistant tool calls are appended to the raw
  transcript at `tools/run_planner_assessment.py:714`–`727` and
  `tools/run_planner_assessment.py:803`–`827`.
- Forced reporting remains part of the same aborted run at
  `tools/run_planner_assessment.py:832`–`870`.
- The external grader fixes the three scored behaviors in
  `tools/test_known_defects_at_83e1d09.py`.

## Must be built (does not exist yet)

- A Q8_0 server fingerprint tied to the user-reported launch command.
- Three Q8_0 raw assessment runs.
- The paired independent adjudication and cache-comparison result report.
- A campaign SHA-256 manifest.

No production `repository-assessment/v1` schema work is authorized by this
experiment.

## Invalidation and limits

A Q8_0 run is invalid if the model label, target, prompt, harness digest, build,
context size, slot count, flash-attention setting, Jinja setting, speculative
state, temperature, thinking setting, seed, turn cap, sandbox validation, or
tool contract differs from the frozen control other than the two cache types.
Retain invalid attempts and rerun the affected seed after correction.

The conditions are blocked in time: all Q4_0 controls precede all Q8_0 runs,
and changing cache type requires a server restart. Cache precision is therefore
confounded with block order and restart state. Three paired seeds reduce but do
not eliminate that limitation. This experiment compares Q4_0 with Q8_0 only;
F16, mixed K/V precision, different context size, fewer slots, a larger turn
budget, and planner conditions require separate designs.
