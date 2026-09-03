# Engram temporal cold-reopen vector validation — 2026-08-30

## Purpose

Validate that explicit temporal metadata remains authoritative after persistent
storage is closed and reopened with real ChromaDB and cached Sentence
Transformers embeddings.

## Frozen design

- Profile `examples.engram_temporal_vector_cold`, version 1
- Three timelines: two updates and one retraction
- Write two temporal versions, close Engram, then reopen cold
- Cached `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions, CPU, offline
- Verify current hybrid search returns only the active event
- Verify historical hybrid search returns active and superseded events
- Verify prompts follow the same current/historical boundary
- Verify persisted status, `superseded_by`, provenance, Chroma counts, telemetry,
  and absence of memory starvation
- No LLM inference or semantic judge
- One execution; changes or reruns require a new profile version

Planned artifact:
`docs/projects/runs/2026-08-30-engram-temporal-vector-cold-v1.json`

## Pre-execution dependency failure

The first invocation used `<maintainer-home>/.venv`, which does not contain
`sentence-transformers`. Initialization failed before any case, storage write,
or artifact creation. The unchanged cases and checks will run using the copied
repository-local `.venv`, which reports `sentence-transformers` 6.0.0 and
ChromaDB 1.5.9. The retained artifact records one prior unstarted dependency
attempt.

## Outcome

The retained execution passed all three timelines:

- Cold reopen with two persisted Chroma records: 3/3
- Hybrid current-state retrieval used vectors and returned only active evidence: 3/3
- Hybrid historical retrieval returned active and superseded evidence: 3/3
- Current and historical prompt provenance matched retrieval: 3/3
- Persisted active/superseded/`superseded_by` metadata: 3/3
- Memory starvation: 0/3

Every current search filtered exactly one superseded predecessor. Chroma counts
remained two before close and after cold reopen. This validates that JSONL's
authoritative temporal metadata correctly reconciles vector results whose
stored metadata predates supersession. It remains a three-case cached-model
test, not a scale or cross-embedder claim.

Artifact:
`docs/projects/runs/2026-08-30-engram-temporal-vector-cold-v1.json`

File SHA-256:
`0f49ef95c0c84f26bf5f377753056884d7191c92154e3723ede79c20ab4d5634`
