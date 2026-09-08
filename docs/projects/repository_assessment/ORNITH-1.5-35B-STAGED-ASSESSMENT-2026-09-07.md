# Ornith 1.5 35B staged assessment — 2026-09-07

## Result

The staged treatment fixed allocation and efficiency, not defect recall.
Across the three preregistered seeds, median substantive coverage rose from
the Ornith baseline's 1/9 to 7/9, median maximum package concentration fell
from 62.2% to 11.1%, and median cumulative input fell from 1,648,791 to 89,359
tokens. Hidden-defect recall nevertheless remained 0/3 in every run.

This is the predicted NAV-like result on an objective grader: external
structure bought broad search, bounded stopping, and calibrated uncertainty,
but did not supply the judgment required to recognize a subtle defect. The
treatment also exposed a new failure mode: three calls per fresh scout were
usually consumed on orientation, leaving too little depth to form a
falsifiable hypothesis.

## Frozen boundary

- Preregistration:
  [staged-assessment preregistration](ORNITH-1.5-35B-STAGED-ASSESSMENT-PREREGISTRATION-2026-09-07.md).
- Frozen target commit:
  `83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532`; archive SHA-256
  `e4bac3a08e16a0d4644e658b93d1bcd5ce5a77d7af4c49e0a63a3a07e52206d2`.
- Same Ornith model endpoint, llama.cpp build, Q4_0 key/value cache,
  flash-attention, Jinja, and active draft MTP boundary as the baseline.
- Seeds 17, 31, and 47; temperature zero; thinking off.
- Maximum 45 executed shell calls, split into nine three-call scouts and at most
  six three-call verifiers. Critics and synthesis had no shell.
- `docs/internal` and `docs/projects` were empty overlays in the model-visible
  sandbox. Validation also confirmed a read-only target, target-local imports,
  private writable `/tmp`, and loopback-only networking.
- The grader defects and all earlier search trajectories remained hidden until
  all reports were final.

This compares complete endpoint configurations, not model weights in
isolation. It also compares a staged controller with an autonomous baseline;
changes cannot be attributed to prompt wording alone.

## Per-run outcomes

| Seed | Shell calls | Coverage | Max concentration | Candidates | Accepted | Synthesis | Input tokens | Recall |
|---:|---:|---:|---:|---:|---:|---|---:|---:|
| 17 | 27 | 7/9 | 11.1% | 0 | 0 | structured | 80,241 | 0/3 |
| 31 | 27 | 6/9 | 11.1% | 0 | 0 | structured | 89,359 | 0/3 |
| 47 | 33 | 8/9 | 18.2% | 2 | 0 | controller fallback | 114,674 | 0/3 |

Medians were 7/9 coverage, 27 shell calls, 11.1% maximum package
concentration, 89,359 input tokens, 5,943 output tokens, 34 model calls, and
109.532 elapsed seconds. No run bound the 45-call ceiling. Controller-assigned
uncertainty was high, high, and medium for coverage 7/9, 6/9, and 8/9; there
were no low-uncertainty claims below the preregistered threshold.

All 27 scouts returned a valid structured result, but none did so before its
three-call budget was exhausted and the controller explicitly requested a
summary. Both seed-47 verifiers behaved the same way. Seed 17 also attempted a
fourth shell call in one scope; the controller rejected it. Seed 47's final
synthesizer produced no structured tool call, so the deterministic report
fallback was retained and clearly marked. These are controlled completions,
not evidence of improved autonomous stopping.

## Candidate and grader adjudication

Seeds 17 and 31 produced no candidates. Seed 47 produced two:

1. The mail scout claimed `load_message_bodies` returned normalized rather
   than caller-supplied Message-ID keys. Its verifier traced the code and
   rejected the claim: normalized IDs are only internal lookup keys, while
   `found[original]` preserves the caller's original key.
2. The UI scout claimed `artifact_to_operation_result` should accept every
   JSON-serializable non-dictionary trace. Its verifier confirmed the control
   flow but supplied no repository contract for that expected behavior. The
   fresh critic rejected it. Independent review agrees: the function returns
   `OperationResult[dict[str, Any]]`, and the package test supplies a dictionary
   trace.

No candidate survived the critic gate. Final precision is therefore undefined
rather than 100%; the pipeline successfully filtered two non-defects, but it
had no positive finding on which to measure precision.

The independent grader was rerun outside the repository conftest path. It
failed 3/3 on the frozen target and passed 3/3 on current HEAD
`61a63fc1eb09c655cfee53aefb96b2045f1ca9bf`. No accepted report finding named
the behavior and symbol for redundant Engram batch indexing, dead-PID writer
lock inode replacement, or stale same-count BM25 disk-cache acceptance. Recall
is exactly 0/3 for all seeds.

Independent transcript review reproduced the harness coverage scores of 7/9,
6/9, and 8/9. File listings and `wc` output were not counted as production
source reads.

## Preregistered decisions

| Prediction | Decision | Evidence |
|---|---|---|
| Median hidden-defect recall remains 0/3 | supported | All three runs scored 0/3. |
| Median coverage reaches at least 8/9 | contradicted | Coverage improved substantially but median was 7/9. |
| Frozen completion/concentration rule | supported | Every scout and selected verifier returned structured output, no run used 45 calls, and all concentrations were below 1/3. |
| Median input is below half the baseline | supported | 89,359 is 5.4% of the 1,648,791-token baseline median, a 94.6% reduction. |
| Precision and calibration improve | descriptive only | No threshold was frozen; there were zero accepted false positives and uncertainty followed controller coverage. |

## What this says about prompts

The generalized process prompt helped only where the controller made its
requirements externally checkable. Separate scopes prevented fixation;
structured dispositions prevented unsupported candidates from silently
becoming findings; a fresh verifier caught one self-contradictory claim; and a
fresh critic caught an invented expected behavior. Those are real gains.

The prompt did not make the model perform the most important judgment. Most
scouts spent their fixed budget listing files and reading a README or package
initializer. Broadly instructing the model to inspect production, check a
contract, trace end to end, and disprove a hypothesis was insufficient under a
three-call scope. In particular, fresh context removed accumulated distraction
but also removed cross-package understanding and encouraged repeated
orientation cost.

The next experiment should not merely add stronger prose. A materially
different treatment would give the controller a cheap, deterministic package
map; require the first model action to choose a concrete symbol or invariant;
reserve later calls for source/caller/reproducer work; and allocate verifier
budget adaptively from unused no-candidate scopes. That is a new experiment and
must be preregistered; these completed results must not be reinterpreted as if
those mechanisms were present.

## Durable evidence and limits

The campaign directory contains every exact transcript, raw report, metadata
record, independent adjudication, grader result, server fingerprint, and
SHA-256 manifest. The model endpoint URL and credentials are not retained.
These artifacts use temporary experiment schemas and do not implement the
deferred production `repository-assessment/v1` profile.

This is three seeds from one model, one endpoint configuration, and one frozen
target. It estimates the combined staged treatment, not any individual prompt
sentence, fresh context, MTP, or cache effect. Zero recall here does not imply
that the model cannot discover defects on other repositories or with a deeper
per-hypothesis budget.
