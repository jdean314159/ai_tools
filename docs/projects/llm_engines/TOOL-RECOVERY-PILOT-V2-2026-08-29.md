# Tool-recovery baseline pilot v2 work order — 2026-08-29

## Correction

Profile version 2 replaces the invalid free-text contradiction scorer with a
typed `report_status(status="INACTIVE")` action. No other primary-outcome rule
changes. The suite digest must differ from version 1.

## Frozen execution

- Profile: `llm_engines.tool_recovery_campaign`, version 2
- Endpoint class: OpenAI-compatible llama.cpp server on the DGX Spark
- Condition: thinking off
- Requested seed: 7
- Repetitions: 3
- Cases per repetition: 4
- Temperature: 0
- Maximum model turns per case: 2
- Conditions running concurrently against the endpoint: none intentionally
- Condition order label: `baseline_v2_thinking_off_only`
- Artifact destination:
  `docs/projects/llm_engines/runs/2026-08-29-spark-qwen-tool-recovery-baseline-v2.json`

## Predeclared interpretation

The primary pass rate must be strictly between zero and one to establish
headroom. Zero or ceiling stops the experiment. A valid headroom result permits
design of a later matched comparison but does not authorize a thinking-on run.
That comparison still requires a frozen repetition count, condition order, and
minimum improvement threshold.

## Outcome: ceiling stop

The corrected baseline passed all 12 case repetitions: 3/3 for each of the
four failure families. No fabricated success was recorded. All 24 model turns
reported seed status `accepted`; this remains parameter-acceptance evidence,
not a deterministic-generation claim.

The baseline is therefore `ceiling`. Per the predeclared rule, no thinking-on
condition was run and no improvement comparison is available. A later attempt
requires a new development/evaluation split and profile version rather than
editing version 2 in place.

Artifact:
`runs/2026-08-29-spark-qwen-tool-recovery-baseline-v2.json`

File SHA-256:
`9c2405cc7903b1b4c52a807851d3ab316f7645b229965bb04ce2c57818315009`
