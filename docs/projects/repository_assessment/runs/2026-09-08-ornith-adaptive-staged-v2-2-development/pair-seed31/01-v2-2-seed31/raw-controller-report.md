# Adaptive staged repository assessment

## Accepted findings

No critic-accepted findings.
## Verification dispositions

- `engram`: rejected — The hypothesis claims reciprocal_rank_fusion does not guarantee stable ordering of tied items with respect to first appearance across rankers, asserting that ties are broken by dict insertion order which it claims differs from first appearance across the rankers. This is false: the items dict is populated by iterating ranked_lists list-by-list and inserting each id only on first sight, so dict insertion order is identical to first-appearance across rankers by construction; combined with Python's stable sorted(), ties are ordered by first appearance across the rankers, exactly matching the stated invariant.
- `action_trajectory_loop_guard`: insufficient_evidence — _novelty returns a non-negative float that is zero when the action signature exactly matches a previously seen signature and strictly increases (monotonically) as the set of differing normalized-argument positions grows, never exceeding the number of differing positions.

## Coverage and uncertainty

- Substantive package coverage: 3/9.
- Controller-assigned uncertainty: high.
