# Engram legacy-versus-temporal paired validation — 2026-08-30

## Purpose

Validate the new explicit temporal path against legacy unstructured episode
storage while holding events, questions, model settings, prompt budget, and
exact scorer constant.

## Frozen design

- Profile `examples.engram_temporal_ab`, version 1
- Arms: legacy `store_episode(...)`, then temporal `store_temporal_episode(...)`
- Three timelines: two updates and one retraction
- Three current-state and two historical-state queries per arm
- Exact value and evidence-ID output scoring
- Current queries declare obsolete predecessor IDs forbidden at composition
- Historical queries require their historical evidence without forbidding the current event
- 520-token budget, 96 reserved output tokens
- Temperature 0, thinking off, seed 59
- No oracle model, baseline answer, semantic rescore, or LLM judge
- One run; changed cases, settings, or reruns require a new profile version

Primary outcome: obsolete evidence in current-state prompts. Secondary outcomes
are historical retention, stage-attributed pass counts, exact answer/evidence
accuracy, prompt tokens, memory starvation, latency, and seed status.

Planned artifact:
`docs/projects/runs/2026-08-30-spark-qwen-engram-temporal-ab-v1.json`

## Outcome

The sole version-1 run completed against `Qwen3.8-27B-UD-Q4_K_M.gguf`.

| Measure | Legacy | Temporal |
|---|---:|---:|
| Storage passed | 5/5 | 5/5 |
| Retrieval passed | 5/5 | 5/5 |
| Composition passed | 2/5 | 5/5 |
| Inference/exact scoring passed | 5/5 | 5/5 |
| End to end | 2/5 | 5/5 |
| Obsolete evidence in current prompts | 3/3 | 0/3 |
| Aggregate prompt tokens | 516 | 455 |
| Aggregate candidate memory tokens | 226 | 174 |
| Memory-starved prompts | 0 | 0 |

Both historical temporal queries retained their historical evidence and passed.
All ten calls reported seed acceptance. Temporal mode reduced aggregate prompt
tokens by 61 (11.8%) and candidate memory tokens by 52 (23.0%) while preserving
answer correctness. The legacy arm's three failures are intentionally
composition failures: the model still answered correctly, but obsolete evidence
violated the frozen current-state prompt contract.

This supports the implemented mechanism on the frozen cases: explicit temporal
metadata removes known obsolete evidence from current prompts without losing
historical recall. It does not establish semantic contradiction inference or
performance on large, naturally occurring histories.

Artifact:
`docs/projects/runs/2026-08-30-spark-qwen-engram-temporal-ab-v1.json`

File SHA-256:
`7952ebd3693fcde4941fd0dd8422cb75a835ea4e262e17b8dc57c5eb73c2de94`
