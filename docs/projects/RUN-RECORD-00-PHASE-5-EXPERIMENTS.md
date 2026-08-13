# RUN-RECORD-00 Phase 5 — experiment/campaign artifacts

**Status:** Complete, 2026-08-13.
**Scope:** A shared experiment body, adapters for the existing ASC and NAV
campaign outputs, and Inspector summaries. No producer rewrite, bundle
resolver, UI, RAG, photo, or course migration.

## Result

The common artifact surface now represents multi-run experiments without
flattening their child agent runs or pretending every campaign row is a
standalone run.

Two legacy campaign producers adapt to experiment body version 1:

- `agent_lib.asc_campaign`, profile version 1; and
- `agent_lib.nav_verifiable_campaign`, profile version 1.

Both use the same body sections: `campaign`, `configuration`, `items`,
`aggregate`, `decision`, and `profile_data`. Profile-specific item summaries
remain distinct inside `items`.

## Lifecycle boundary

The source producers established the lifecycle rule:

- ASC rewrites `live_probe_results.json` after each task and does not persist
  the requested matrix size in that report. Its adapter therefore requires the
  caller to declare `checkpoint`, `final`, or `aborted`; it does not infer
  completion from a plausible-looking summary.
- NAV rewrites `pairs.json` while running and writes both `summary.json` and
  `decision.json` only after complete admitted-task coverage. Its adapter emits
  a checkpoint when given pairs alone and a final artifact only when summary
  and decision are supplied together.

These adapted artifacts are immutable snapshots of the source state. A later
checkpoint produces a different source digest and record identity.

## Child-record boundary

Completed ASC records and supplied NAV arm records are adapted into separate
`agent_run` artifacts. The experiment envelope uses semantic `contains`
relationships and item-level `child_record_id` values to link them. The full
child records are not copied into the experiment body.

ASC timeout rows remain experiment items with aggregate outcome facts. They do
not receive invented standalone identities because the current producer never
writes timeout `record.json` artifacts. NAV arm outcomes remain compact item
data even when the corresponding full child artifact is unavailable.

The adapter returns an `ExperimentAdaptation` containing the experiment and
the separately addressable child artifacts. It does not claim a portable
bundle: attachment storage and resolver behavior remain unimplemented.

## Conservative declarations

Legacy campaign privacy remains `unknown` and `not_validated`. Execution start
and finish times and original-producer identity are explicitly omitted rather
than synthesized. ASC's source `generated_at` is retained; NAV's current
campaign files do not provide a trustworthy wall-clock time.

No aggregate-recompute capability is declared. The current body preserves
compact item outcomes and published child identities, but there is not yet a
portable child resolver or a shared recomputation implementation. Claiming
recomputation now would overstate what a copied experiment artifact can do.

## Inspector support

Inspector recognizes both experiment profiles and reports campaign name,
lifecycle, item count, separately published child count, and the presence of
aggregate and decision sections. It does not homogenize experiment items with
generation or agent-run summaries.

## Validation

Tests cover:

- ASC checkpoint/final declaration and mixed completed/timeout rows;
- no fabricated timeout child artifact;
- NAV checkpoint versus final inference from summary+decision presence;
- separately adapted NAV arm records and deterministic semantic links;
- common JSON round-trip validation;
- Inspector experiment dispatch and summary; and
- cross-package ASC campaign adapter-to-Inspector integration.

Validation results:

```text
focused adapters/core/Inspector/import/public API: 43 passed
agent_lib + core + Inspector (known golden omitted): 225 passed, 8 skipped
committed ASC campaign acceptance: 15 items, 15 child artifacts, supported
```

The omitted Inspector golden is the pre-existing optional-tokenizer-dependent
Engram mismatch documented in the Phase 4 report; this slice does not touch its
trace construction or token accounting.

## Gate assessment

Phase 5 proves that the common envelope and a shared experiment body can
represent two materially different campaign producers while preserving their
lifecycle and child-record semantics. The result deliberately stops before
portable bundling. The next architectural question is attachment/bundle
resolution if copied experiments must carry their children; otherwise the
project can move to a separate producer or course-fixture validation slice.
