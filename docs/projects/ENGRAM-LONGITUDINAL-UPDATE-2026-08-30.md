# Engram longitudinal knowledge-update experiment — 2026-08-30

## Purpose

Test Engram's storage, retrieval, prompt composition, and answer use across
corrections, supersession, historical questions, and retractions without an
oracle model, oracle-selected context, or LLM judge.

## Frozen design

- Profile: `examples.engram_longitudinal_update`, version 1
- Five unrelated project timelines and seven probes
- Every event occurs in a distinct numbered session and has a synthetic ID
- Two historical-state probes, three current corrected-state probes, and two
  post-retraction abstention probes
- Events are persisted before a cold probe session is opened
- Engram alone retrieves and composes memory context
- Expected normalized values and evidence IDs are encoded in the frozen suite
- Exact normalized value and exact evidence-ID scoring; no semantic judge
- Remote llama.cpp generation uses temperature 0, thinking off, and seed 41

The artifact records only synthetic IDs, normalized expected and observed
values, stage booleans, counts, tokens, latency, and the model basename. It
omits the endpoint, host paths, raw prompts, raw responses, and raw memory text.

## Attribution

- Storage passes when every declared event receives a persisted Engram episode.
- Retrieval passes when the pre-registered evidence event enters Engram's final
  prompt.
- Answer-value and evidence-ID checks are scored independently.
- End-to-end passes require retrieval plus both exact answer checks.

This design does not compare against a baseline or an oracle. A retrieval
failure supports extending retrieval. Retrieval success followed by systematic
failures on corrections or retractions supports adding temporal/conflict
resolution before prompt composition. Correct unambiguous composition followed
by answer failure remains attributable to the served model or instructions.

## Stop rule

Run version 1 once. Changed cases, scoring, prompt instructions, model settings,
or any rerun require a new profile version and disclosed work order. Planned
artifact: `docs/projects/runs/2026-08-30-spark-qwen-engram-longitudinal-v1.json`.

## Execution status

The sole version-1 run completed against the DGX Spark llama.cpp endpoint
serving `Qwen3.8-27B-UD-Q4_K_M.gguf`. All seven calls completed and reported
seed acceptance.

- Storage: 7/7
- Expected evidence retrieved into the final prompt: 7/7
- Exact answer value: 7/7
- Exact evidence ID: 7/7
- End to end: 7/7

Every prompt contained the complete two- or three-event timeline for its
project. Thus the result shows that Engram preserved and retrieved the frozen
events and that the served model correctly applied the explicit chronological
correction/retraction instructions. It does not show that Engram itself
represents temporal validity or resolves contradictions before composition,
nor does seven synthetic probes establish longitudinal performance at scale.

Artifact:
`docs/projects/runs/2026-08-30-spark-qwen-engram-longitudinal-v1.json`

File SHA-256:
`3964ca640a340b9365ab49d77fea1875258bcefaeebace7ad809ac2ac96c3b7d`
