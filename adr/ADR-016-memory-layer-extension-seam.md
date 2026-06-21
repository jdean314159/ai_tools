---
decision_history_version: 1
hypotheses:
  - id: neural-affinity
    application_scope: retrieval-re-ranking
    resolution_status: resolved_against
    mechanism_status: operational
    mechanism_evidence:
      - adr/ADR-016-memory-layer-extension-seam.md#neural-04-affinity-scaling
    earlier_support:
      basis: >-
        Recovered affinity design and spread-relative scaling provided a
        plausible mechanism for improving retrieval ordering.
      evidence:
        - adr/ADR-016-memory-layer-extension-seam.md#neural-05-write-side-role
        - adr/ADR-016-memory-layer-extension-seam.md#neural-04-affinity-scaling
    resolution_evidence:
      - adr/ADR-016-memory-layer-extension-seam.md#neural-05-write-side-role
    superseded_by: ADR-016
    current_guidance: Neural retrieval re-ranking is disabled.

  - id: surprise-weighting
    application_scope: write-side-episode-importance
    resolution_status: qualified
    mechanism_status: operational
    mechanism_evidence:
      - adr/ADR-016-memory-layer-extension-seam.md#neural-05-write-side-role
    earlier_support:
      basis: >-
        Prediction error could provide a bounded advisory signal for episode
        importance without changing retrieval ordering.
      evidence:
        - adr/ADR-016-memory-layer-extension-seam.md#neural-05-write-side-role
    resolution_evidence:
      - adr/ADR-016-memory-layer-extension-seam.md#decision-park-the-neural-layer-default-off-research-artifact
    superseded_by: ADR-016
    current_guidance: >-
      The advisory write-side mechanism remains implemented in the parked,
      default-off layer, but product benefit is unproven.

  - id: titans-context-synthesis
    application_scope: prompt-side-context
    resolution_status: unresolved
    mechanism_status: operational
    mechanism_evidence:
      - adr/ADR-016-memory-layer-extension-seam.md#neural-06-generation-mode-result-and-stability-correction
    earlier_support:
      basis: >-
        Reconstructing the learned value vector into prompt hints could expose
        accumulated patterns that retrieval-mode evaluation could not measure.
      evidence:
        - adr/ADR-016-memory-layer-extension-seam.md#neural-06-titans-style-context-synthesis
    resolution_evidence:
      - adr/ADR-016-memory-layer-extension-seam.md#neural-06-generation-mode-result-and-stability-correction
    superseded_by: ADR-016
    current_guidance: >-
      The mechanism worked end-to-end, but the evaluated configuration produced
      no measurable benefit. The implementation is parked and broader benefit
      remains unestablished.

  - id: surprise-signal
    application_scope: novelty-anomaly-detection
    resolution_status: unresolved
    mechanism_status: not_demonstrated
    mechanism_evidence: []
    earlier_support:
      basis: >-
        Label-free prediction error may be more suitable for novelty,
        derailment, poisoning, or segmentation signals than retrieval.
      evidence:
        - adr/ADR-016-memory-layer-extension-seam.md#decision-park-the-neural-layer-default-off-research-artifact
    resolution_evidence: []
    superseded_by: null
    current_guidance: >-
      This reframe has not earned product status and requires a concrete need
      plus a predeclared evaluation gate.
---

# ADR-016: Additive memory-layer extension seam

**Date:** 2026-06-09
**Status:** Accepted
**Deciders:** Jeff Dean
**Related:** ADR-004 (Engram retrieval policy), ADR-005 (persistence and
migration), ADR-009 (supported Engram implementation), NEURAL-01

## Context

`ProjectMemory` directly coordinates working, episodic, semantic, and cold
memory behavior. Re-integrating an optional neural memory implementation by
editing that orchestration inline would increase coupling and make the default
lightweight path depend on experimental behavior.

The existing implementation already has stable points where an optional layer
needs to participate: observation after successful writes, advisory recall
ranking, prompt hints, and persistence/teardown.

## Decision

Engram exposes an additive `MemoryLayer` protocol and explicit
`ProjectMemory.register_layer()` method.

Registered layers are invoked in registration order at four seams:

1. `observe` after a turn or episode is stored successfully.
2. `contribute_to_recall` after core candidates are produced and before the
   final result slice.
3. `contribute_to_prompt` before prompt assembly.
4. `persist` and `close` before the project writer lock is released.

Extension layers do not replace or unify the four existing memory layers. Core
storage, retrieval, and prompt content remain authoritative:

- recall contributions may adjust scores but cannot add, remove, or suppress
  candidates;
- prompt contributions are clearly labeled advisory hints and remain subject
  to the normal prompt token budget;
- extension failures are logged and isolated from core behavior;
- an empty registry preserves existing behavior.

## Consequences

New memory experiments can integrate through a small public contract without
adding dependencies or branches to the existing memory implementations.
Extension ordering is deterministic and explicit.

The protocol is intentionally narrow. It does not provide lifecycle ownership,
configuration discovery, automatic registration, or authority over core
results. Implementations that require those capabilities need a later ADR.

## Forward Work

NEURAL-02b implements the recovered RTRL/TITANS coordinator as the first
`MemoryLayer`.

The implementation uses the associative memory's intrinsic prediction error as
its surprise signal. Perplexity-based `SurpriseFilter` integration is deferred
because the current observation seam does not carry logprobs and Engram does
not own a logprob-capable inference engine.

Candidate-specific neural affinity requires embeddings for the candidates
already selected by core retrieval. `ProjectMemory` therefore provides a
generic candidate-embedding resolver: it reads stored ChromaDB embeddings when
available and falls back to embedding the JSONL episode text. The neural layer
receives this resolver as a callable; neural details do not enter the core
retrieval contract.

Automatic neural-layer registration is configuration-gated and default-off.
The base package imports neither `engram.neural` nor PyTorch unless neural
memory is explicitly enabled. NumPy remains the default backend, with PyTorch
available only through the optional acceleration extra.

The layer must remain default-off until corpus evaluation demonstrates a
measurable retention or recall improvement over the four-layer baseline.

## NEURAL-04 Affinity Scaling

The first full A/B exposed a score-scale mismatch. Core hybrid retrieval uses
RRF scores with a typical range around `0.01` to `0.04`, while the recovered
neural coordinator supplied raw additive affinity with weight `0.08`. A neural
adjustment could therefore exceed the entire core score range and replace,
rather than assist, retrieval ordering.

Affinity is now dimensionless and spread-relative. For each candidate set,
Engram computes the original score spread and applies:

`adjusted_score = original_score + affinity * score_spread`

The spread is computed before any extension contribution. Perfectly tied or
single-candidate sets receive no affinity adjustment. Multiple extension
contributions remain additive against the same original spread.

`NeuralMemoryConfig.affinity_weight` defaults to `0.15`, meaning a cosine of
`1.0` contributes fifteen percent of the candidate score spread. The weight is
subject to an explicit sweep. Neural memory remains default-off unless a sweep
finds a no-regression operating point and that finalist passes the full
six-trial evaluation.

## NEURAL-05 Write-Side Role

The neural re-ranking role is disabled after two clean evaluation runs showed
catastrophic direct-recall loss at every tested affinity weight. The neural
layer now returns no recall contribution.

Its active role is write-side and advisory: paired-turn prediction error
adjusts newly stored episode importance within bounded limits, while
familiarity and novelty prompt hints remain available. Episodes are never
suppressed by this mechanism. Re-ranking remains architecturally possible but
must stay disabled unless future training volume demonstrates reliable gains.

## NEURAL-06 TITANS-Style Context Synthesis

The neural prompt role now tests a richer TITANS-style hypothesis. After
warmup, the layer projects its value-space prediction through the cached
pseudoinverse of the deterministic value projector, aligns the approximate
embedding with a bounded in-memory episode snapshot, and emits a template-only
`[Neural context]` hint with learned-pattern trajectory and short episode
snippets.

`value_dim` was initially increased from 16 to 64 to improve reconstruction
resolution, but the full-volume evaluation exposed RTRL overflow. It now uses
the stable fallback of 32. `hidden_dim` remains 32 because larger hidden
dimensions have also caused P-matrix overflow with the current clipping regime.
Persisted configuration is versioned, and incompatible weight shapes are
discarded with a warning rather than loaded silently. Any non-finite neural
state disables further neural reads, writes, hints, and persistence.

Prompt hints remain advisory: each is capped at 200 tokens, considered after
core memory sections, and may be dropped during compression. Retrieval-mode
evaluation cannot observe prompt-only mechanisms, so context synthesis must be
measured in generation mode by grading answers produced from the assembled
prompt. Evaluation results record their mode and cross-mode comparisons are
rejected.

## NEURAL-06 Generation-Mode Result and Stability Correction

**Date:** 2026-06-11

The generation-mode decision eval was run (qwen3:8b generator, qwen3.6:27b
judge, 60-fact corpus, six trials, one warmup replay, baseline vs. neural_on).
Result: clean null. Neural hints were emitted on every probe (180/180 per
trial) and warmup completed at 120 steps, so the mechanism is confirmed working
end-to-end. Every metric delta was within one to two judgments of baseline
(recall_direct 0.878 -> 0.872, recall_paraphrase 0.861 -> 0.858, decoy 0.250 ->
0.239, contradiction_bleed unchanged). No improvement criterion was met. The
decoy metric is structurally uninformative in generation mode with an
unconstrained generator: the model answers decoy queries from parametric memory
regardless of context, so both arms sit near 25% independent of hints.

Stability correction landed before this run. The 600-step production stability
test showed `value_dim=64` is numerically unstable, so it was reverted to
`value_dim=32` (the pre-approved spec fallback) and persistence `config_version`
was bumped to 3. A fail-closed guard was added: any non-finite neural state
halts reads, writes, and hint emission rather than propagating corrupt state,
consistent with this ADR's extension-isolation requirement. The earlier
statement that `value_dim` increases to 64 is superseded.

## Decision: park the neural layer (default-off research artifact)

On the evidence above, the RTRL/TITANS layer has not earned core-feature
status. Under the governing rule - build a capability when a concrete run fails
without it, not speculatively - nothing in the repo currently fails without it,
and as integrated it cannot improve retrieval (the read vector is collapsed back
to episode alignment, a lossy proxy for episodic retrieval).

The layer is therefore **parked**: kept in the tree behind the default-off
ADR-016 seam, not actively developed. A reframe was identified but not pursued:
the component's distinctive output is its label-free surprise signal, which
suits novelty/anomaly use (agent-loop derailment, memory-poisoning detection,
surprise-based chunk segmentation) rather than retrieval. Reactivation requires
a concrete safety/observability need plus a predeclared, falsifiable decision
gate. Until then the layer stays parked; do not re-run retrieval evals without a
new mandate.