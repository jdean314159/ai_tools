# NAV-VERIFIABLE-00 campaign policy v1

**Status:** Frozen before production task construction  
**Schema version:** 1

## Minimum distribution

The first paired campaign is incomplete until it contains:

- at least four local tasks;
- at least four intermediate tasks;
- at least six exploratory tasks;
- at least fourteen tasks total and one no-ledger/ledger pair per task.

The exploratory tier must span at least three independently hashed source
snapshots. Snapshot identity is derived from pinned source hashes, not from an
admission-manifest identifier.

No single task shape may supply more than half of the exploratory tier. At
least three exploratory tasks must meet the decoy threshold, and at least three
must meet the hop-count or answer-file threshold. A task may satisfy both.

## Paired protocol

Every pair uses the same admitted task, relation-claim schema, AST scorer, model
configuration, budget, decoding configuration, and seed. Both arms must emit
typed `relation_claims`. The no-ledger arm has no per-step navigation goals; the
ledger arm does. Run-specific output locations and ledger state are the only
permitted differences. Run order is recorded and alternated.

This is not the free-form autonomous mode measured by NAV-TEST-00. It is a
shared-schema no-ledger baseline designed to isolate the ledger's effect.
Free-form extraction and asymmetric rubrics are prohibited.

The final summary must exactly cover all tasks and frozen tiers in the campaign
manifest. Missing, additional, duplicated, or re-tiered records make the
campaign incomplete.

## Primary reporting

Exploratory results are primary and always reported separately. Each tier
reports:

- no-ledger and ledger termination rates;
- relation-correct, evidence-complete, evidence-precise, and exact-pass rates;
- paired exact outcomes:
  no-ledger-fail/ledger-pass, no-ledger-pass/ledger-fail, both-pass,
  and both-fail;
- median structured-minus-autonomous token and tool-step deltas;
- every individual paired delta.

An overall summary may be reported only as an equal-tier macro-average.
Task-pooled results cannot be the primary conclusion.

## Frozen decision rule

Support broader shadow testing only when the exploratory tier has:

- a net termination gain of at least two and no more than one reverse loss;
- nonnegative exact and relation-correct paired nets;
- ledger total tokens no greater than no-ledger total tokens;
- no more than 25% median ledger token overhead among pairs where both arms
  complete.

Reject the ledger direction when any of these hold:

- exploratory net termination gain is zero or negative;
- exact paired net is at most negative two;
- relation-correct paired net is at most negative two;
- ledger uses more than 125% of no-ledger exploratory tokens without an exact
  paired improvement.

All other complete results are inconclusive. Support means a broader shadow
campaign, not shipping.

## Conclusion boundary

Fewer than six completed exploratory pairs supports no termination-control
conclusion. The first campaign is a directional engineering gate, not a
statistical-significance result. One trajectory per task is permitted, with
model nondeterminism retained as a limitation.

Replicated runs require a separate predeclared campaign. They may not be
selectively added only to surprising tasks.

Candidate enumeration and selection follow
`NAV-CANDIDATE-SELECTION-V1.md`; hand-picked replacements are prohibited.

Changing this distribution, diversity rule, or summary policy requires campaign
schema version 2 and must occur before observing new campaign outcomes.
