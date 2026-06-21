# Knowledge Curation MVP: Candidate Extraction

**Status:** Implemented; live run requires local Ollama
**Date:** 2026-06-13
**Scope:** Phase 4 only

## Purpose

Use a local LLM to propose atomic, generalizable claims from the frozen Phase 3
corpus. Outputs are candidates for human review, not approved knowledge.

## Input Boundary

The extractor verifies the normalized corpus SHA-256 against
`CORPUS_MANIFEST.json`. It selects assistant-authored `message_text` records,
then creates deterministic, conversation-local source batches. This extracts
Claude's existing assessments instead of asking another model to reassess raw
article attachments. Oversized records are split into bounded character ranges
without changing their normalized text.

Every source unit has a stable ID that resolves to:

- normalized-corpus line number;
- conversation UUID;
- message UUID;
- source kind and source index;
- character start and end within the normalized record;
- raw and normalized source hashes.

Thinking blocks, tool traces, conversation titles, account identifiers, and
file names remain outside the extraction input.

## Candidate Contract

Each proposed candidate contains:

- one atomic statement;
- a scope describing when it applies;
- an evidence kind:
  - `secondary_assessment`;
  - `source_material`;
  - `mixed`;
- explicit qualifications or exceptions;
- one or more exact source-unit IDs.

The model must not:

- approve or reject a claim;
- assign numeric confidence;
- merge claims across batches;
- decide whether a claim is true;
- create repository doctrine;
- cite source IDs that were not present in its batch.

Deterministic validation rejects malformed output, unknown source references,
empty or overlong statements, duplicate references, and excessive candidate
counts. Candidate IDs are hashes of the reviewed fields and provenance; they
are assigned by code, not by the model.

## Batching And Resumption

- batches never mix conversations;
- each source unit is capped at 20,000 characters;
- each batch is capped at 100,000 source characters;
- each batch proposes at most eight claims;
- local inference uses temperature `0`;
- successful batch results are cached by batch hash;
- reruns reuse only cache entries matching the current corpus, prompt, schema,
  model, and batch hash.

## Private Artifacts

The following generated artifacts contain private or derived text and remain
ignored by Git:

- `CANDIDATE_BATCH_RESULTS.jsonl`;
- `CANDIDATE_CLAIMS.jsonl`.

`CANDIDATE_EXTRACTION_MANIFEST.json` contains only hashes, model configuration,
counts, and failure summaries. It is safe to track.

## Phase Boundary

No candidate becomes approved knowledge in Phase 4. Human editing, rejection,
splitting, consolidation, and approval belong to Phase 5.
