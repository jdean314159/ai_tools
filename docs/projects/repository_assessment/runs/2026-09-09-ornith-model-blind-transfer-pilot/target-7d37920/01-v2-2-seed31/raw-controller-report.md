# Adaptive staged repository assessment

## Accepted findings

No critic-accepted findings.
## Verification dispositions

- `engram`: rejected — reciprocal_rank_fusion ranks an item higher when it appears in more of the input ranked lists, and for items appearing in the same number of lists, higher aggregate rank positions produce a higher fused score; the fused ordering is a strict monotonic function of the sum of 1/rank across all lists in which each item appears.
- `action_trajectory_loop_guard`: rejected — _novelty returns a non-negative float that is exactly 0.0 when the action signature exactly matches a previously seen signature, and strictly increases (monotonically) as the set of differing normalized-argument positions grows, never exceeding the number of differing positions.

## Coverage and uncertainty

- Substantive package coverage: 3/9.
- Controller-assigned uncertainty: high.
