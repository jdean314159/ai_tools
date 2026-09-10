# Handover — Ornith oracle-localization A/B/C test

**Date:** 2026-09-10  
**Campaign:** Ornith repository assessment  
**Status:** Preregistered; span manifest frozen; model generation has not started.

## Purpose

This closing experiment removes repository search and tests whether
Ornith-1.5-35B-Q4_K_M can recognize a defect in a localized source span. It is
not another harness-tuning campaign.

## Authority

The repository owner authorized Codex to design, implement, validate, run,
document, and commit this A/B/C test within `ai_tools`, including DGX endpoint
use, temporary worktrees, scoring, adjudication, and reruns under frozen
invalidation rules. No changes to `llm-reliability-lab` are authorized by that
grant. The campaign is under consolidated authority: Codex is designer,
implementer, operator, grader, adjudicator, and committer. No independent
verification claim may be made unless separately performed.

## Frozen materials

- [Preregistration](ORNITH-ORACLE-LOCALIZATION-ABC-PREREGISTRATION-2026-09-10.md)
- [Span manifest](runs/2026-09-10-ornith-oracle-localization-abc/span-manifest.json)
- [Manifest builder](tools/build_oracle_localization_manifest.py)

The manifest currently contains five defect spans drawn from validated transfer
targets:

- `23c1549d...`: agent tool-state classification, engine configuration, and
  publication-hygiene Git handling;
- `7d37920a...`: storage path validation and cross-tenant episode deletion.

The `83e1d09...` development target is intentionally excluded from this run.

## Planned conditions

- **A:** reuse the existing staged-v1 full-repository transfer results as an
  unpaired baseline anchor;
- **B:** localized defect and matched negative spans, defect undisclosed;
- **C:** localized spans with balanced true and false hypotheses.

All fresh items use identical Ornith settings and three seeds per item. Recall
is localized recall: the model must identify the affected behavior and state an
actionable violation within the presented span. False assertions on negative
spans are scored separately; C confirmations and rejections are also separate.

## Remaining work

1. Select and verify matched negative spans against the frozen source and
   graders; record boundaries and hashes.
2. Implement the single-turn A/B/C runner and explicit scoring layer.
3. Demonstrate scorer negative and positive controls before generation.
4. Freeze prompts, item manifest, scorer, and oracle mapping in a pre-generation
   commit.
5. Run all planned items, spot-check token and elapsed-time fields against raw
   transcripts, adjudicate, validate, and document results.

Do not add spans, seeds, conditions, or prompt changes after observing model
output. Retain any invalid attempts with their reasons.
