# Engram vector-retrieval experiment — 2026-08-30

## Purpose

Validate Engram's real Sentence Transformers + ChromaDB + hybrid retrieval path
and compare it descriptively with text-only retrieval on fixed synthetic data.
This is not a general retrieval-quality claim.

## Frozen design

- Profile: `examples.engram_vector_retrieval`, version 1
- Embedder: `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions, CPU
- Offline cached-model execution
- Five distinct project queries
- Four memories per case: current relevant, near-relevant, explicitly
  superseded conflict, and unrelated
- Text-only condition first; hybrid text+vector condition second
- Top 3 results retained as synthetic memory IDs, ranks, and bounded scores

Primary checks per hybrid case: telemetry reports vector search used, the
relevant memory is in the top three, and it ranks ahead of the superseded
conflict. Text-only results and rank changes are descriptive; no improvement
threshold was selected.

The artifact omits raw queries, memory text, cache paths, host paths, and model
weights. Run once; changed cases, scorer, embedder, thresholds, or reruns
require a new profile version.

Planned artifact:
`docs/projects/runs/2026-08-30-engram-vector-retrieval-v1.json`

## Outcome

All five hybrid queries reported `used_vector_search=true`, recalled the
relevant memory in the top three, and ranked it ahead of the explicitly
superseded conflict. Text-only retrieval also recalled the relevant memory in
all five cases, but ranked it ahead of the conflict in only two. Hybrid
retrieval ranked the relevant memory first in all five cases.

This is a descriptive result on the frozen synthetic suite. It validates the
real 384-dimensional embedding, ChromaDB persistence/query, Engram hybrid
fusion, and telemetry path; five examples do not establish general superiority.

Artifact SHA-256:
`974785cf4dacb1d0da87df92dac07da4dae8992e9423fda33fd32c031a56b85e`
