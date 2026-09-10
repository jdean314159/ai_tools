# Ornith oracle-localization A/B/C result — 2026-09-10

Ornith again recalled none of the five defects without an oracle hint, even
when search was removed and only the affected source span was shown. Condition
B produced `no_violation` on all 30 requests: 0/15 localized defect recall and
0/15 false assertions on matched negatives.

Condition C's strict verdict accuracy was exactly chance, 15/30. That aggregate
hides the important result: the model did not discriminate any pair by verdict.
It rejected both defective and fixed spans for four behaviors, then confirmed
both versions of the permissions behavior. Its explanations nevertheless
distinguished four defective/fixed pairs accurately. The experiment therefore
does not support a simple recognition-limit diagnosis; it exposes a combination
of hypothesis-generation failure, overly conservative actionability demands,
and a structured verdict/content grounding failure.

This was a consolidated campaign. Codex implemented, operated, scored, and
adjudicated it; no independent-verification claim is made.

## Pre-generation correction and controls

Before the first DGX request, audit of span-manifest v1 found that it retained
the transfer pilot's already disclosed historical false-fail configuration row,
omitted the Engram permissions defect, and placed the path-escape boundary after
the unsafe join. Manifest v2 corrected all three issues. Commit `6eff393`
retains the original; the corrected protocol, prompts, oracle, runner, scorer,
validator, and controls were frozen in commit `c53361c` before generation.

The five negatives are the corresponding implementations at corrected
references `49026ea` and `8e2e9e5`. Preflight validation reproduced the external
grader splits: target/reference 0/2 versus 2/2 and 0/3 versus 3/3. Four frozen
scorer controls passed, including acceptance of a correct defect description,
rejection of a benign description, acceptance of negative abstention, and
detection of a negative false assertion. The targeted repository-assessment
suite passed 47 tests.

## Results

| Condition | Positive result | Negative result | Strict reading |
| --- | ---: | ---: | --- |
| A: existing staged-v1 anchor | 0/5 defect recall | 0 accepted false positives | Unpaired full-repository anchor |
| B: localized, no hypothesis | 0/15 defect recall | 0/15 false assertions | Every verdict was `no_violation` |
| C: localized plus hypothesis | 3/15 correct confirmations | 12/15 correct rejections | 15/30 combined, exactly chance |

C also had 12/15 false rejections and 3/15 false confirmations. At the pair
level it rejected both target and negative for tool-state classification, Git
fail-closed behavior, storage path escape, and cross-tenant deletion. It
confirmed both target and negative for persistent storage permissions. Each of
the 20 condition/item cells was byte-identical across seeds 17, 31, and 47, so
the three temperature-zero seeds exposed no output variance.

## Semantic adjudication

The strict scores are upheld because the frozen C rule requires the correct
verdict as well as the oracle concepts. However, four true-hypothesis responses
are internally contradictory:

- the tool-state response says `tool_not_granted` is omitted and falls through
  to a generic failure warning, then returns `reject`;
- the Git response says the return code is unchecked and an empty inventory can
  result, then returns `reject` because the downstream check is outside the
  span;
- the path response says there is no separator or traversal validation, then
  returns `reject` because no downstream exploit is shown; and
- the deletion response says no tenant authorization is performed, then returns
  `reject` because unseen repository context might scope episodes safely.

On each matched fixed span, the explanation correctly identifies the relevant
guard and rejects the hypothesis. The content therefore recognizes four of the
five target/fixed distinctions, but the requested verdict does not express that
recognition. B shows the same conservative threshold most clearly on path
escape: it explicitly notes the absence of traversal rejection, yet declines a
violation because no malicious caller value appears in the span.

The permissions negative has a real interpretation caveat. The corrected code
applies `chmod(0700/0600)` after `mkdir` or `open`, and logs rather than fails if
`chmod` raises. Ornith confirmed a narrower transient/fail-open exposure concern
on that span. The frozen scorer counts this as a false confirmation because the
external grader's eventual-mode contract passes, but the negative hypothesis is
not semantically clean. It is retained and flagged rather than rewritten or
rerun after observation.

## Preregistered interpretation

Mechanically, A≈0, B≈0, and C≈chance maps to the preregistered recognition-limit
row. The response content materially qualifies that reading. Given a
hypothesis, Ornith accurately described the defective behavior in four pairs
but failed to map that analysis to `confirm`; for the fifth, it found the
intended defect and an adjacent issue in the fixed implementation. The tighter
conclusion is:

1. removing search did not restore autonomous localized recall;
2. supplying hypotheses exposed latent semantic recognition;
3. the model demanded evidence beyond the displayed affected span even when
   the violation itself was visible; and
4. strict structured verdicts were not grounded in the model's own rationale.

This leaves headroom for a harness that separates semantic extraction from a
controller-owned decision mapping, but it does not justify more prompt tuning
on these known targets. The frozen campaign is complete without reruns.

## Run integrity and cost

All 60 runs used `Ornith-1.5-35B-Q4_K_M.gguf`, temperature zero, thinking
disabled, strict JSON output, and one model call. Post-run validation checked
all 60 transcript/metadata token and elapsed fields, identities, hashes, seeds,
and response schemas. It reported no errors.

| Condition | Input tokens | Output tokens | Sum of request elapsed | Median request elapsed |
| --- | ---: | ---: | ---: | ---: |
| B | 12,618 | 5,343 | 80.618 s | 2.620 s |
| C | 13,086 | 5,703 | 89.167 s | 2.948 s |
| Total | 25,704 | 11,046 | 169.784 s | — |

The only endpoint fingerprint delta was nullable slot telemetry becoming the
explicit `none,draft-mtp` value on two idle slots. Model, build, context, slot
count, speculative enablement, launch configuration, and health remained
stable.

## Evidence

- [Preregistration](ORNITH-ORACLE-LOCALIZATION-ABC-PREREGISTRATION-2026-09-10.md)
- [Pre-generation correction](ORNITH-ORACLE-LOCALIZATION-ABC-PREGENERATION-CORRECTION-2026-09-10.md)
- [Campaign artifacts](runs/2026-09-10-ornith-oracle-localization-abc/)
- `preflight-validation.json`, `scores.json`, `post-run-adjudication.json`, and
  `postrun-validation.json` in the campaign directory
- [Runner](tools/run_oracle_localization.py),
  [scorer](tools/score_oracle_localization.py), and
  [validator](tools/validate_oracle_localization.py)
