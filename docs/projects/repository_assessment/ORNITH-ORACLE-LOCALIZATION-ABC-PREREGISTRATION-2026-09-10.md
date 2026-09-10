# Ornith oracle-localization A/B/C test preregistration — 2026-09-10

Status: amended and frozen before generation. No model output had been produced
when the correction below was made.

## Pre-generation oracle correction

The initial span manifest at commit `6eff393` was invalid on audit. It included
an engine-configuration row for a private Spark address that was introduced
after target `23c1549`, omitted the validated Engram persistent-permission
defect, and placed the path-escape span after the faulty path join. This is the
same historical false-fail already disclosed in the transfer-pilot result.

Before any generation, manifest v2 replaces that row with the permissions
defect and moves the path-escape boundary onto `_compute_storage_root`. Each
negative span is the corresponding implementation at the already validated
corrected reference (`49026ea` or `8e2e9e5`). The original manifest remains in
Git history; this correction and regenerated hashes are committed before the
first DGX request.

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

The frozen fresh matrix contains 60 single-turn requests: ten spans (five
defects and five fixed-reference negatives), three seeds (`17`, `31`, `47`),
and conditions B and C. B therefore has 15 defect opportunities and 15
negative opportunities. C has 15 true-hypothesis confirmations and 15
false-hypothesis rejections. Temperature is zero, thinking is false, maximum
output is 512 tokens, and a strict four-field JSON schema is used. A generation
set aborts on an exception, non-stop finish, unaccepted seed, or invalid schema;
the invalid set is retained and the unchanged full matrix is rerun under a new
generation-set name.

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

For B, defect recall requires `verdict=violation` plus all three frozen semantic
concept groups for that oracle. Any `violation` verdict on a negative span is a
false assertion, even if it names a different issue. For C, a true hypothesis
is correctly confirmed only with `verdict=confirm` plus the oracle concept
groups; a false hypothesis is correctly rejected with `verdict=reject`.
Invalid structured responses count in neither numerator and remain reported.

This run is under the consolidated campaign authority: Codex designs,
implements, operates, grades, adjudicates, and commits; no independent-
verification claim is made. Claude specified this design; Codex implements it.
