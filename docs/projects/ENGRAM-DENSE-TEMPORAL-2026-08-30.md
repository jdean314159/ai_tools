# Engram dense temporal-retrieval experiment — 2026-08-30

## Purpose

Test whether Engram retrieves the evidence needed for corrections, historical
state, and retractions when complete timelines no longer fit in the prompt.
The experiment uses no oracle model, oracle-selected context, baseline answer,
or LLM judge.

## Frozen design

- Profile `examples.engram_dense_temporal`, version 1
- Five unrelated cases, one live answer per case
- 48 semantically overlapping distractors plus two or three target events per case
- 420-token prompt budget with 96 tokens reserved for output
- Text retrieval through Engram's normal prompt-building path
- Exact normalized value and exact evidence-event ID scoring
- Temperature 0, thinking off, seed 43
- One run; changes or reruns require a new profile version

The selected event IDs establish whether Engram retrieved the pre-registered
evidence. Answer and evidence-ID correctness are scored separately. The
artifact omits endpoint data, raw prompts, raw responses, raw memories, and host
paths.

Planned artifact:
`docs/projects/runs/2026-08-30-spark-qwen-engram-dense-temporal-v1.json`

## Interpretation rule

Missing expected evidence is a retrieval failure regardless of the model's
answer. Retrieved evidence followed by a wrong exact answer is an answer-use
failure. A systematic inability to select a retraction or the correct temporal
version would justify temporal-aware retrieval or pre-composition conflict
resolution. Five synthetic cases remain a bounded diagnostic, not a general
quality estimate.

## Outcome

The sole version-1 run completed against `Qwen3.8-27B-UD-Q4_K_M.gguf`.
Storage, expected-evidence retrieval, exact answer value, exact evidence ID,
and end-to-end success were each 5/5. All calls reported seed acceptance.

Engram selected only four or five events from each corpus of 50 or 51. It
included the required evidence in every case, but it also included every target
timeline's obsolete event or events. The served model then resolved the
explicit corrections and retractions correctly. This validates selective
retrieval under the frozen pressure condition; it does not demonstrate
pre-composition temporal conflict resolution by Engram.

Artifact:
`docs/projects/runs/2026-08-30-spark-qwen-engram-dense-temporal-v1.json`

File SHA-256:
`69f13f437599b69c129c1e9170fa57087731900cfeb7f7444ac80ae2a3ab3a2a`
