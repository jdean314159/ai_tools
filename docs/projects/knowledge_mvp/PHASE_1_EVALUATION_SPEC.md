# Knowledge Curation MVP: Predeclared Evaluation

**Status:** Locked before export audit or claim extraction
**Date:** 2026-06-13
**Scope:** Phase 1 only

## 1. Decision Question

Does a small set of human-reviewed, provenance-linked claims extracted from the
Claude conversation export improve architecture reviews enough to justify
building the rest of the knowledge-curation MVP?

This evaluation tests curated claims, not autonomous truth determination. The
human reviewer remains authoritative. A passing result permits the export audit
and extraction MVP to continue; it does not justify Engram, RAG, ChromaDB, or
wiki UI integration.

## 2. Hypothesis

Given the same architecture case packet and review prompt, a local LLM supplied
with approved general claims will:

1. identify more of the case's predeclared required considerations;
2. avoid unsupported or irrelevant objections;
3. preserve important exceptions and qualifications;
4. reach a recommendation at least as defensible as the baseline; and
5. reduce or not materially increase human adjudication effort.

The null result is that curated claims add agreement, verbosity, or apparent
authority without improving the review.

## 3. Benchmark Cases

Four resolved repository decisions form the benchmark. Each evaluation packet
must contain only information that was available before the recorded decision.
It must not contain the ADR decision, consequences, later status, or test result
that reveals the outcome.

### K1: Memory Package Consolidation

Reference decision: `adr/ADR-009-engram-freeze-and-rename.md`

The review must address:

- functional duplication between the two memory implementations;
- the maintenance cost of a hollow facade;
- lightweight default dependencies and standalone package usability;
- compatibility for existing callers;
- whether archived capability belongs in the active monorepo.

Reference outcome: retain one supported lightweight `engram`, archive the heavy
runtime, and provide narrow compatibility types rather than two active package
identities.

### K2: Redundant UI Disposition

Reference decision: `adr/ADR-010-archive-engram-ui-add-chat-panel.md`

The review must address:

- feature overlap between the two user interfaces;
- broken dependencies on the archived heavy runtime;
- whether unique features justify migration cost;
- the value of a single supported workbench entry point;
- separation of a small immediate gap from broader deferred model management.

Reference outcome: archive `engram_ui`, use `llm_inspector_ui` as the supported
workbench, preserve the useful chat capability, and defer full model management.

### K3: Import Topology and Measured Exception

Reference decision: `adr/ADR-014-import-topology.md`

The review must address:

- direct-layout import shadowing;
- editable installs and `src/` layout;
- removal of package-local path injection;
- import-provenance validation;
- whether the root pytest anchoring guard can be removed without regression.

Reference outcome: convert `llm_engines` to `src/` layout and remove its path
hack, but retain the root anchoring guard after direct experiments showed that
removing it still caused namespace shadowing.

This is the qualification control. Generic advice such as "remove every path
workaround" is harmful if it ignores measured repository behavior.

### K4: Neural Memory Product Status

Reference decision: `adr/ADR-016-memory-layer-extension-seam.md`, sections
"NEURAL-05 Write-Side Role" through "Decision: park the neural layer."

The review must address:

- whether experimental behavior may override core retrieval;
- observed retrieval regressions across tested affinity weights;
- the generation-mode null result;
- default-off and failure-isolation requirements;
- whether a non-retrieval use of the surprise signal is plausible without
  claiming that it has already earned product status.

Reference outcome: disable neural re-ranking, keep the layer default-off and
parked behind the additive seam, and require a new concrete need plus a new
predeclared gate before reactivation.

This is the evidence-hierarchy control. General enthusiasm about neural memory
must not outweigh local evaluation results.

## 4. Claim Eligibility and Leakage Controls

Only claims meeting all of these conditions may enter the augmented arm:

- extracted from the ten-conversation MVP corpus;
- approved or edited by the human reviewer before evaluation;
- traceable to conversation and message UUIDs;
- stated as a general lesson rather than a case-specific answer;
- sourced from a message created before the relevant benchmark decision date;
- free of benchmark ADR identifiers, exact repository paths, and explicit
  descriptions of the recorded outcome.

Claims derived from conversations that directly discuss one of K1-K4 are
ineligible for that case. Claims may still be eligible for unrelated cases.

Before extraction, freeze a corpus manifest containing the ten conversation
UUIDs and a SHA-256 hash of the export. Before evaluation, freeze the approved
claim set and record its hash. Any later change creates a new evaluation
version; it must not be substituted into the original run.

## 5. Evaluation Arms

Each benchmark case has two arms:

- **Baseline:** case packet and review prompt only.
- **Curated:** identical packet and prompt plus eligible approved claims.

If there are 40 or fewer approved claims, provide all eligible claims. If there
are more than 40, use a frozen deterministic lexical scorer to select the top
20 for each case. Do not use an LLM or human case-by-case judgment to select the
claim bundle.

Every supplied claim must include only:

- claim ID;
- reviewed statement;
- scope or qualification;
- evidence level;
- review status.

Conversation text and the reference outcomes are not supplied to the reviewing
model.

## 6. Run Protocol

- Use the same local model, model version, prompt, token budget, and inference
  settings in both arms.
- Use fresh independent sessions with no Engram or conversation history.
- Use temperature `0` where the backend supports it.
- Run each arm twice per case, for 16 outputs total.
- Alternate arm order by case and randomize output identifiers before scoring.
- Do not tell the scorer which arm produced an output.
- Reject and rerun only transport, parse, or truncation failures. Preserve the
  failed artifact and record the reason.
- Record model identity, backend configuration, prompt hash, claim-set hash,
  packet hash, latency, and output length for every run.

The review response must use a fixed structure:

1. recommendation;
2. required considerations and tradeoffs;
3. rejected alternatives;
4. uncertainties or missing evidence;
5. cited claim IDs, if any.

## 7. Scoring Rubric

Score against the frozen case definitions above, not against fluency.

### 7.1 Required-Consideration Coverage

For each of the five required considerations per case:

- `1`: materially addressed;
- `0`: absent or only named without analysis.

Report per-case and overall coverage rates.

### 7.2 Reference-Outcome Alignment

- `2`: recommendation matches the defensible core of the reference outcome;
- `1`: mixed or conditional recommendation that preserves the critical safety
  and maintenance constraints;
- `0`: recommends a rejected or materially unsafe direction.

This is a benchmark proxy, not a declaration that historical ADRs are
infallible. A credible challenge to a reference outcome is recorded separately
for human review.

### 7.3 Unsupported Assertions

Count factual or causal assertions supported by neither the case packet nor an
identified approved claim. Do not count clearly labeled questions or
uncertainties.

### 7.4 Material Errors

Count recommendations that violate an explicit case constraint, ignore
controlling empirical evidence, or remove a measured safeguard without
replacement. Record whether a supplied claim caused or amplified each error.

### 7.5 Claim Utility

For every cited or clearly used claim:

- `useful`: improves coverage, qualification, or reasoning;
- `neutral`: relevant but does not change review quality;
- `harmful`: causes overgeneralization, unsupported certainty, distraction, or
  a material error.

Uncited supplied claims are not assumed to have been used.

### 7.6 Human Adjudication Effort

Record minutes required to score each output using the frozen rubric. Also
record output word count. Longer output is not an improvement by itself.

## 8. Predeclared Decision Gate

The MVP proceeds only if all completion checks pass and all quality checks pass.

### Completion Checks

- all four case packets are frozen before model runs;
- all 16 valid outputs are present;
- no output reveals an arm label;
- all outputs are scored against the same frozen rubric;
- export, corpus, claim-set, packet, prompt, and model identifiers are recorded.

### Quality Checks

1. Curated overall required-consideration coverage is at least 10 percentage
   points above baseline.
2. Curated coverage is higher than baseline in at least three of four cases
   after averaging the two repeats.
3. Curated total material errors do not exceed baseline total material errors.
4. No material error is caused or amplified by a supplied claim.
5. Curated unsupported assertions do not exceed baseline by more than one
   across all eight curated outputs.
6. At least one claim is rated useful in at least three of four cases.
7. No used claim is rated harmful.
8. K3 preserves the measured root anchoring exception in both curated repeats.
9. K4 gives local empirical results priority over general claims in both
   curated repeats.
10. Median human adjudication time for curated outputs is no more than 25%
    above baseline.

Verdicts:

- **proceed:** every completion and quality check passes;
- **revise and rerun:** completion passes, quality fails, and a specific
  extraction, review, or presentation defect is identified without changing
  this gate;
- **stop:** curated claims show no useful signal, introduce harmful guidance,
  or only increase agreement or verbosity.

## 9. Interpretation Rules

- A tie is not an improvement.
- More citations are not an improvement unless they help satisfy the rubric.
- Agreement with an ADR is not sufficient if required considerations are
  missing.
- A contrary recommendation is not automatically wrong if it identifies valid
  new evidence; record it as a challenge rather than silently changing the
  benchmark.
- The reviewing LLM cannot score its own outputs.
- Numeric model confidence is not collected.
- Results from this small benchmark do not establish general knowledge-base
  quality. They only decide whether the next MVP phase is justified.

## 10. Phase Boundaries

Phase 1 creates and freezes this specification. Later phases may add:

- an export-integrity report;
- normalized records;
- candidate extraction;
- human review artifacts;
- deterministic claim presentation;
- evaluation runners and reports.

They must not add RAG, Engram integration, automatic approval, autonomous
supersession, or repository-doctrine updates before this gate is run.
