# NAV-VERIFIABLE-00 campaign policy v1

**Status:** Frozen before production task construction  
**Schema version:** 1

## Minimum distribution

The first paired campaign is incomplete until it contains:

- at least four local tasks;
- at least four intermediate tasks;
- at least six exploratory tasks;
- at least fourteen tasks total and one autonomous/structured pair per task.

The exploratory tier must span at least three independently hashed source
snapshots. Snapshot identity is derived from pinned source hashes, not from an
admission-manifest identifier.

No single task shape may supply more than half of the exploratory tier. At
least three exploratory tasks must meet the decoy threshold, and at least three
must meet the hop-count or answer-file threshold. A task may satisfy both.

## Paired protocol

Every pair uses the same admitted task, model configuration, budget, decoding
configuration, and seed. Only structured-navigation mode and run-specific
output locations may differ. Run order is recorded and alternated.

The final summary must exactly cover all tasks and frozen tiers in the campaign
manifest. Missing, additional, duplicated, or re-tiered records make the
campaign incomplete.

## Primary reporting

Exploratory results are primary and always reported separately. Each tier
reports:

- autonomous and structured termination rates;
- relation-correct, evidence-complete, evidence-precise, and exact-pass rates;
- paired exact outcomes:
  autonomous-fail/structured-pass, autonomous-pass/structured-fail, both-pass,
  and both-fail;
- median structured-minus-autonomous token and tool-step deltas;
- every individual paired delta.

An overall summary may be reported only as an equal-tier macro-average.
Task-pooled results cannot be the primary conclusion.

## Conclusion boundary

Fewer than six completed exploratory pairs supports no termination-control
conclusion. The first campaign is a directional engineering gate, not a
statistical-significance result. One trajectory per task is permitted, with
model nondeterminism retained as a limitation.

Replicated runs require a separate predeclared campaign. They may not be
selectively added only to surprising tasks.

Changing this distribution, diversity rule, or summary policy requires campaign
schema version 2 and must occur before observing new campaign outcomes.
