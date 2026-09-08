# Adaptive staged repository assessment

## Accepted findings

No critic-accepted findings.
## Verification dispositions

- `llm_inspector`: insufficient_evidence — The invariant is false: given an AugmentRequest whose trace exposes interop events, EngramAugmenter._augment_via_interop populates ContextResult.evidence_flows directly via _interop_events_to_evidence_flows and never calls trace_to_memory_records. The invariant's core mechanism (converting interop events into memory records via trace_to_memory_records) is absent from the implementation.
- `engram`: confirmed — reciprocal_rank_fusion(ranks_lists) returns scores computed as sum over each list of 1/(k + rank) for a constant k, where an item appearing in multiple ranked lists has its scores summed, and items absent from all lists receive a score of zero.
- `rag_lib`: insufficient_evidence — HybridRetriever._reciprocal_rank_fusion computes each item's fused score as the sum over the dense and BM25 lists of weight/(k + rank_in_that_list) with k=_RRF_K=60 (dense weight = 1-bm25_weight, BM25 weight = bm25_weight), and emits the merged items in strictly descending fused-score order.

## Coverage and uncertainty

- Substantive package coverage: 3/9.
- Controller-assigned uncertainty: high.
