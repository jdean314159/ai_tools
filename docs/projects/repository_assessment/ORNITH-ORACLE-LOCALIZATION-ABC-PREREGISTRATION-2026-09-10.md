# Ornith oracle-localization A/B/C test preregistration — 2026-09-10

This closing experiment tests whether Ornith can recognize a defect when search
is removed. It is not a harness comparison. The run uses the validated transfer
targets `23c1549d5aae3ac67454aade1b725f2931770014` and
`7d37920a81a9cb672c24af3a55557621e5c5009f`; the development target
`83e1d09c5a39bc7a9b27e97dfdf39bd1cf694532` is excluded from this preregistration.

## Definitions

A **span** is a contiguous source region identified by frozen commit, path, and
line range. A **defect span** contains exactly one graded defect. A **negative
span** is matched in file type, approximate length, and structure but contains
no graded defect. Localized recall requires identifying the affected behavior
and stating an actionable violation within the presented span. A **false
assertion** claims a violation in a negative span.

## Conditions

- **A:** existing full-repository anchor; reused transfer-pilot staged-v1
  results, not treated as a paired control.
- **B:** one span, with no defect description or oracle hint; defect and negative
  spans are balanced.
- **C:** one span plus a hypothesis; true and false hypotheses are balanced,
  and confirmations and rejections are scored separately.

All fresh items use Ornith-1.5-35B-Q4_K_M.gguf, identical generation settings,
and three seeds per item. No prompt, span, seed, or condition may be added or
changed after the first generation. Invalid attempts are retained.

## Interpretation (frozen)

| A | B | C | Reading |
|---|---|---|---|
| ~0 | >0 | — | search/allocation limit; harness work has headroom |
| ~0 | ~0 | discriminates | hypothesis-generation limit |
| ~0 | ~0 | confirms true and false | prompt compliance |
| ~0 | ~0 | ~chance | recognition limit at this model/quantization |
| ~0 | high false assertions | — | targeting failure/reticence distinction |

The scoring layer will run negative controls demonstrating rejection of a
description with no violation and acceptance of a correct identification before
any model generation. Token and elapsed-time fields will be spot-checked
against raw transcripts.

This run is under the consolidated campaign authority: Codex designs,
implements, operates, grades, adjudicates, and commits; no independent-
verification claim is made. Claude specified this design; Codex implements it.
