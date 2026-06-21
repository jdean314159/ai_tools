# Knowledge Curation MVP: Normalized Corpus

**Status:** Implemented
**Date:** 2026-06-13
**Scope:** Phase 3 only

## Purpose

Create a fixed ten-conversation corpus for later candidate-claim extraction.
This phase performs deterministic selection and text normalization only. It
does not extract, score, approve, merge, or reject claims.

## Selection

The selected conversations are frozen by UUID in `CORPUS_SELECTION.json`.
They are dedicated article-assessment threads or closely related discussions of
LLM tools and applications. Every selected conversation predates the earliest
benchmark decision in the Phase 1 evaluation.

The selection file intentionally omits conversation titles, summaries, account
identifiers, and message text. Any change to its UUID list creates a new corpus
version and requires a new manifest.

## Included Records

The normalized JSONL contains:

- one record for each non-empty `chat_messages[*].text`;
- one record for each non-empty attachment `extracted_content`;
- conversation and message UUIDs;
- parent UUID and parent-link status;
- sender and timestamps;
- source position;
- SHA-256 hashes of raw and normalized text;
- normalization operation counts;
- normalized text.

The corpus excludes:

- conversation names and summaries;
- account UUIDs;
- attachment and file names;
- file-reference UUIDs;
- thinking blocks;
- token-budget blocks;
- tool-use inputs and tool-result payloads.

Message text is the canonical rendered conversation representation. Content
blocks are not copied separately because they substantially duplicate message
text and include private execution traces outside the MVP's article-assessment
scope.

## Normalization

Normalization is intentionally conservative:

1. convert CRLF and CR newlines to LF;
2. apply Unicode NFC normalization;
3. remove ANSI terminal escape sequences;
4. replace nonbreaking spaces with ordinary spaces;
5. replace Unicode line and paragraph separators with LF;
6. remove C0/C1 control characters except LF and TAB;
7. remove zero-width space and byte-order-mark characters;
8. trim trailing horizontal whitespace;
9. collapse runs of more than two blank lines to two;
10. trim leading and trailing blank space.

Accented letters, non-English text, typographic punctuation, mathematical
symbols, emoji, box-drawing characters, private-use characters, and Unicode
replacement characters are preserved. Their presence is recorded rather than
silently transliterated.

Raw source text is never modified. Each normalized record carries a raw hash so
its source can be verified against the ignored `conversations.json` export.

## Artifacts

- `CORPUS_SELECTION.json`: frozen UUID selection and rationale.
- `CORPUS_MANIFEST.json`: export hash, selection hash, corpus hash, counts, and
  normalization summary.
- `NORMALIZED_CORPUS.jsonl`: ignored local artifact containing private text.

The normalized corpus must not be committed. The manifest is safe to track
because it contains aggregate metadata and provenance UUIDs but no source text.

## Phase Boundary

Phase 3 does not call an LLM. Candidate extraction begins only in Phase 4 and
must use the frozen manifest and normalized-corpus hash.
