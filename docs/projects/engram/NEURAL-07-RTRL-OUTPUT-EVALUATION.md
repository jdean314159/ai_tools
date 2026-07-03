# NEURAL-07: RTRL Output Evaluation and Isolation

**Status:** Complete — resolved against recall influence

**Run dates:** 2026-06-30 through 2026-07-01

**Scope:** Engram's optional RTRL/TITANS layer only

## Decision

RTRL output must not affect Engram recall by default. The network may still run
when neural memory is explicitly enabled, but its prediction error and value
prediction are telemetry/research outputs unless a future experiment earns a
new integration role.

The three possible recall effects are now isolated:

- `contribute_to_recall()` returns no contribution;
- episode-list prompt advisory is default-off and requires explicit experimental
  opt-in;
- surprise-based episode-importance adjustment is default-off and requires
  explicit experimental opt-in.

This decision does not claim that RTRL is universally incapable of learning a
utility function. It records that the repository has no dependable production
feedback signal from which to learn candidate usefulness, and that every tested
label-free output path failed its gate.

## Controls Added Before Testing

The evaluation harness was corrected before drawing conclusions:

- `NeuralMemoryConfig.enabled` and `ProjectMemory(enable_neural=True)` were
  verified in neural runs;
- fresh RTRL initialization was seeded without mutating NumPy's caller state;
- surprise, write/skip counts, and emitted hint content were recorded through
  public layer APIs;
- generation-mode tests were used for the live prompt-advisory channel;
- generated run data remained under the ignored `integration_tests/eval/runs/`
  tree, while this report records the durable result.

## Experiment 1: Affinity Weight

Weights `0.05`, `0.10`, `0.15`, `0.20`, `0.30`, and `0.50` produced identical
retrieval metrics. This was expected after code inspection: neural
`contribute_to_recall()` intentionally returns `None`, so `affinity_weight` is
inactive. The historical affinity CLI now refuses to present this as a valid
optimization.

Conclusion: no affinity value can improve current retrieval because the
parameter has no active output channel.

## Experiment 2: Surprise Threshold

The original threshold `0.001` accepted every observed neural update. A seeded,
percentile-calibrated generation sweep tested the active write gate. The
30-fact screen selected threshold `9.7106409`, which retained 71.4% of updates
and passed the partial screen.

The finalist then ran against a fresh baseline on all 60 facts and all six
trials:

| Metric | Baseline | Threshold 9.7106409 | Delta |
|---|---:|---:|---:|
| Direct recall | 86.1% | 85.8% | -0.3 pp |
| Paraphrase recall | 86.1% | 86.4% | +0.3 pp |
| Decoy recall | 69.7% | 67.5% | -2.2 pp |
| Contradiction bleed | 20.0% | 19.4% | -0.6 pp |

The run completed 1,080 judgments per arm with zero judge and injection
failures. The neural arm made 209 updates from 463 observed pairs (45.1%). It
failed the decision rule because decoy performance regressed and no meaningful
quality improvement emerged.

Important qualification: these “writes” are RTRL weight updates, not Engram
episode admission. The harness stores episodes with `bypass_filter=True`.

## Experiment 3: Prompt-Advisory Content

The completed finalist's saved neural state was queried for all 180 corpus
queries. The live pseudoinverse/newest-100 advisory selected three episodes per
query:

- expected current episode present: `0/180`;
- stale target present: `0/180`;
- unrelated episode selected: every query;
- selected slots: `540/540` unrelated, dominated by late forgetting-trial
  distractors;
- reconstructed-space cosine: mean `0.103`.

Two mechanisms caused this result:

1. a 32-dimensional value prediction was mapped back into the 768-dimensional
   embedding space through a random-projector pseudoinverse;
2. the bounded candidate provider considered only the newest 100 episodes,
   which excluded the original facts after 200 distractors were inserted.

An isolated direct-value-space/query-specific-candidate variant improved target
inclusion to `43/180` (23.9%), but missed on 76.1% of queries. Hit and miss
similarity/margin distributions overlapped, so a confidence threshold could not
make the variant safe. The runtime variant was reverted; diagnostic metadata was
retained.

## Experiment 4: Candidate-Utility Scoring

A shadow experiment tested a smaller, more appropriate role: one sigmoid output
predicting candidate usefulness from deployable features only:

- semantic similarity;
- reciprocal base rank and score spread;
- lexical overlap and length ratio;
- importance, recency, and repetition.

The experiment used held-out facts, deterministic initialization seeds `0`, `1`,
and `2`, balanced replay, hard stale/decoy negatives, and bounded score weights
`0.05`, `0.10`, and `0.20`. No evaluation identifiers, contradiction labels, or
distractor flags entered the feature vector.

Across every seed and weight, the scorer preserved direct recall but did not
improve decoy rejection or stale suppression; some configurations increased
stale selection. No runtime scorer was wired.

The result identifies a missing input, not a demonstrated capacity limit. A
utility predictor needs an externally observed outcome such as a verified
citation, correction, supersession decision, or explicit user rejection.
Ordinary system usage supplies no reliable “candidate was irrelevant” label.
Synthetic labels can test mechanics but cannot justify online production
adaptation.

## Current Configuration

The RTRL/TITANS layer remains globally default-off. If explicitly enabled:

- learning and telemetry may run;
- retrieval order is unchanged;
- prompt advisory remains off unless `prompt_advisory_enabled=True`;
- episode importance remains unchanged unless
  `importance_advisory_enabled=True`.

Evaluation CLI equivalents are `--neural-prompt-advisory` and
`--neural-importance-advisory`. They are experiment controls, not recommended
production settings.

## Reactivation Gate

Do not reconnect RTRL output to recall without all of the following:

1. a real, auditable usefulness-feedback source available outside the test set;
2. shadow-mode candidate scoring on held-out sequential interactions;
3. improvement over ordinary retrieval across multiple fixed seeds;
4. no direct/paraphrase regression beyond the declared noise threshold;
5. improved decoy and stale/contradiction handling;
6. bounded influence and abstention behavior that passes full-volume testing.
