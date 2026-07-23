# NAV-VERIFIABLE-00 candidate selection v1

**Status:** Frozen before production snapshot selection  
**Pool schema:** 1  
**Selection schema:** 1

## Candidate enumeration

For every pinned, oracle-compatible Python snapshot, enumerate mechanically:

- every definition;
- every callable with a nonempty direct-caller set;
- every unique statically resolvable call path between same-snapshot symbols;
- every named call site.

Each candidate is passed through canonicalization and structural difficulty
classification. Candidates with identical normalized expected relations within
a snapshot are deduplicated. The complete candidate pool records source hashes,
expected relations, task descriptors, tiers, and a fixed salted selection key.
The pool is hashed before selection.

## Selection

Local and intermediate candidates are selected by the fixed salted hash order.
Exploratory selection is deterministic coverage-greedy, then hash-ordered:

- gain credit for a new source snapshot until three are represented;
- gain credit for a decoy-threshold task until three are represented;
- gain credit for a graph/multi-file task until three are represented;
- never permit one task shape to exceed half the exploratory tier.

The selector fails if the pool cannot satisfy the frozen 4/4/6 campaign
distribution and diversity constraints. It does not accept hand-picked
substitutions.

If a stratum is undersupplied, add a new pinned source snapshot and regenerate
the entire candidate pool. Do not append or replace individual tasks after
observing model outcomes.

## Bias boundary

The public ordering salt is:
`NAV-VERIFIABLE-00-candidate-order-v1`.

Changing enumeration, deduplication, the salt, or selection priority requires a
new schema version before any new campaign outcomes are observed.
