# Knowledge Curation MVP: Human Review

**Status:** Review workflow implemented; human decisions pending
**Date:** 2026-06-13
**Scope:** Phase 5 only

## Purpose

Turn model-proposed candidates into human-reviewed claims without allowing the
model, renderer, or materializer to determine truth.

## Review Artifacts

The workflow creates:

- `REVIEW_QUEUE.jsonl`: candidates grouped by deterministic topic, with bounded
  source excerpts and related-candidate suggestions;
- `REVIEW_BUNDLE.html`: local, private review interface;
- `REVIEW_DECISIONS.jsonl`: append-only human decision log;
- `APPROVED_CLAIMS.jsonl`: materialized current approved claims.

All four contain private or human-authored material and remain ignored by Git.
`REVIEW_MANIFEST.json` contains hashes and aggregate counts only.

## Human Actions

- `approve`: accept the candidate wording.
- `edit`: approve revised wording, scope, evidence kind, or qualifications.
- `reject`: exclude the candidate with a rationale.
- `defer`: leave unresolved with a rationale.
- `split`: replace one candidate with two or more approved claims.
- `consolidate`: replace two or more candidates with one approved claim.

Every action requires a reviewer identity and rationale. `edit`, `split`, and
`consolidate` require complete replacement claim data. Consolidation is valid
only when all source candidates exist and at least two are supplied.

## Append-Only Semantics

Review decisions are never edited in place. A later decision may supersede an
earlier decision for the same candidate. Materialization uses the latest valid
decision per candidate.

For consolidation, the event becomes the current decision for every listed
source candidate. For splitting, all generated claims retain the source
candidate's complete provenance.

The materializer rejects:

- unknown candidate IDs;
- duplicate event IDs;
- invalid actions or missing rationales;
- invalid replacement claim structures;
- consolidation with fewer than two candidates;
- source references not present on the source candidates;
- automatically authored approval.

## Review Presentation

Candidates are grouped into broad deterministic topics and ordered to reduce
source dominance. The bundle displays:

- candidate statement, scope, evidence kind, and qualifications;
- conversation UUID and source-unit references;
- bounded source excerpts;
- related candidates suggested by lexical overlap;
- exact CLI commands for recording decisions.

Related suggestions are navigational only. They do not merge or rank claims.

## Phase Boundary

Generating the queue and bundle does not complete human review. Phase 5 is
complete only when a human has recorded decisions and the approved claim set is
materialized and frozen for the Phase 1 evaluation.
