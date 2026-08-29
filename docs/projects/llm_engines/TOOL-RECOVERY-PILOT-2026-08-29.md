# Tool-recovery baseline pilot work order — 2026-08-29

## Purpose

Measure whether the frozen version-1 recovery suite has enough baseline
headroom for a later thinking comparison. This is a pilot, not an intervention
test.

## Frozen execution

- Profile: `llm_engines.tool_recovery_campaign`, version 1
- Endpoint class: OpenAI-compatible llama.cpp server on the DGX Spark
- Model label: provider-reported basename only
- Condition: thinking off
- Requested seed: 7
- Repetitions: 3
- Cases per repetition: 4
- Temperature: 0
- Maximum model turns per case: 2
- Conditions running concurrently against the endpoint: none intentionally
- Condition order label: `baseline_thinking_off_only`
- Artifact destination:
  `docs/projects/llm_engines/runs/2026-08-29-spark-qwen-tool-recovery-baseline-v1.json`

The runner's frozen suite digest identifies the exact prompts, injected tool
results, tool schemas, expected actions, and scorer. Raw interaction content is
not retained in the artifact.

## Predeclared interpretation

The primary outcome is the proportion of cases with correct recovery within
the two-turn budget and no fabricated success. Fabricated-success rate is a
separate guardrail. Latency, token totals, and tool-call counts are descriptive
only.

- If the primary pass rate is `0.0`, the baseline is `zero`: stop.
- If the primary pass rate is `1.0`, the baseline is `ceiling`: stop.
- Otherwise baseline headroom is `present`, and a later matched comparison may
  be designed.

A stop result requires a new development/evaluation split and profile version;
the cases must not be edited in place. A headroom result does not authorize a
thinking-on run. Before a matched comparison, a separate work order must freeze
its repetitions, condition order, and minimum improvement threshold.

## Evidence limits

Seed acceptance means only that the adapter forwarded seed 7 and the provider
completed the request. It does not establish deterministic generation. This
single endpoint and synthetic suite do not estimate application reliability or
expose hidden reasoning.
