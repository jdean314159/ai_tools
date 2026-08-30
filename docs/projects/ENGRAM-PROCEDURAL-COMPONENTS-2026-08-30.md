# Engram procedural-components experiment — 2026-08-30

## Purpose

Correct the prior procedural-transfer scorer's undefined-label problem while
keeping thinking disabled. The same five experiences, queries, and 36
distractors per case are used, but output is an ordered selection from a frozen,
closed action-component vocabulary.

## Frozen design

- Profile `examples.engram_procedural_components`, version 1
- Five cases; one live call each
- Same experience and distractor texts as procedural-transfer version 1
- Exact ordered component-list and evidence-ID scoring
- 600-token prompt budget; 128 tokens reserved for output
- Temperature 0, thinking off, seed 53
- No baseline, oracle context, oracle model, semantic rescore, or LLM judge
- One run; changes or reruns require a new profile version

This tests complete transfer of explicitly described procedural components from
a retrieved experience. It still does not test autonomous abstraction of a
general rule from multiple experiences.

Planned artifact:
`docs/projects/runs/2026-08-30-spark-qwen-engram-procedural-components-v1.json`

## Outcome

The sole thinking-off version-1 run completed against
`Qwen3.8-27B-UD-Q4_K_M.gguf`.

- Storage: 5/5
- Supporting experience retrieved: 5/5
- Exact supporting experience ID: 5/5
- Exact ordered component list: 4/5
- End to end: 4/5

The sole mismatch was `schema_drift`: the model returned
`refresh_schema_contract, regenerate_mapping` and omitted the expected final
`retry`. The source experience says those first two actions succeeded but does
not explicitly state a subsequent retry. The frozen exact failure is retained,
but it is not evidence of an Engram storage or retrieval defect. It exposes a
remaining expectation-to-source alignment issue and provides a concrete case
for the later thinking-on comparison, where the score must remain unchanged.

The four exact successes support bounded transfer of ordered procedural
components from retrieved experiences. This profile still does not test
autonomous rule induction across multiple episodes.

Artifact:
`docs/projects/runs/2026-08-30-spark-qwen-engram-procedural-components-v1.json`

File SHA-256:
`1eb4fadc613008e48e75706506d3090b9dc81eeb8a0ef01f2ac4aa50cbf57b10`
