# Adaptive staged repository assessment

## Accepted findings

No critic-accepted findings.
## Verification dispositions

- `llm_engines`: rejected — The hypothesis claims StructuredOutputHandler._extract_json raises StructuredOutputError when no braces are present in the input text. This is false: the function has return type str | None and returns None on brace-free input; StructuredOutputError is raised only by the higher-level parse() method, never by _extract_json.
- `engram`: confirmed — reciprocal_rank_fusion(ranks_lists) returns scores computed as the sum over each list of 1/(k + rank) for a constant k, where an item appearing in multiple ranked lists has its scores summed, and items absent from all lists receive a score of zero.
- `rag_lib`: insufficient_evidence — HybridRetriever._reciprocal_rank_fusion does not emit items in strictly descending fused-score order and does not include all fused items — it drops BM25-only results, so the returned ranking is not a complete, strictly-descending RRF merge as the invariant requires.

## Coverage and uncertainty

- Substantive package coverage: 5/9.
- Controller-assigned uncertainty: high.
