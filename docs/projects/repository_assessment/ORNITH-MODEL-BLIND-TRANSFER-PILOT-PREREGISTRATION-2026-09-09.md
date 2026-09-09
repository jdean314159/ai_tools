# Ornith model-blind target-transfer pilot preregistration — 2026-09-09

Status: frozen before the first model generation request.

This is an exploratory pilot, not adaptive-v2 Phase 2 and not a confirmatory
model comparison. Codex selected the historical targets and wrote their
graders after inspecting later fixes. The model remains blind to the oracle,
but the evaluator and harness author are not independent.

## Question

On two previously unused target trees, does the frozen adaptive-v2.2 condition
improve known-defect recall over staged v1, or does it again change process
control without improving defect judgment?

## Frozen targets and oracle boundary

The target acquisition and grader validation are recorded in
`TARGET-ACQUISITION-2026-09-08.md`.

| Target | Tree | Uncompressed tar SHA-256 | Defects | Corrected reference |
| --- | --- | --- | --- | --- |
| `23c1549d5aae3ac67454aade1b725f2931770014` | `d4faa7c547ab8e34f251124c7e5ca7a9dcbf6364` | `ba24146927228771ccefc078cf8732e0a1abb77e3d4a77ff699205742413d1b0` | 3 | `49026eac3d2e24b02641bf9db0a76e94909e9386` |
| `7d37920a81a9cb672c24af3a55557621e5c5009f` | `0177f7c8288a42ca771084c42362ddb6f90a9640` | `02e68e5c7cb349f1c6e3011fd6f0265ebdf6a87fa753bef932fabfd271bd8769` | 3 | `8e2e9e5f2c45c935bdc3afa2479a08dc702b44db` |

Both exported trees passed the existing pre-model isolation check: all nine
package imports resolved below `/workspace`, the target was read-only, private
`/tmp` was writable, network interfaces were loopback-only, root agent
instructions remained visible, and `docs/internal` plus `docs/projects` were
empty in the sandbox.

The grader sources, defect descriptions, fix messages, corrected references,
and this preregistration must not be mounted into `/workspace`. Do not execute
either grader and do not inspect reports against the oracle until all four
model reports are final.

## Conditions held fixed

The control is the existing staged-v1 runner. It assigns all nine package
scopes, three shell calls per scout, at most six three-call verifiers, a critic,
and model synthesis. The implementation and budgets are at
`tools/run_staged_assessment.py:745-930`.

The treatment is the existing adaptive-v2.2 runner. It creates deterministic
dossiers, obtains one model-selected symbol per package, gives each scout two
shell calls, promotes at most three hypotheses, gives each verifier at most
nine calls, validates exact evidence quotations, uses a critic, and renders the
final report deterministically. The implementation and budgets are at
`tools/run_adaptive_staged_assessment.py:912-1139`.

No prompt, schema, package list, call budget, evidence rule, promotion rule,
critic rule, or completion rule changes for this pilot. The only harness change
is target identity injection, validated at
`tools/run_staged_assessment.py:55-88`, passed into staged-v1 at
`tools/run_staged_assessment.py:745-757`, and reused by v2.2 at
`tools/run_adaptive_staged_assessment.py:912-924`. It records the correct full
commit, tree, and tar digest instead of the old `83e1d09` constants.

The model is `Ornith-1.5-35B-Q4_K_M.gguf` through the same llama.cpp OpenAI
endpoint family used in the completed Ornith campaigns. Required server
settings are user-reported Q4_0 K/V caches, flash attention, Jinja chat
templating, and draft MTP with maximum three draft tokens. Temperature is zero,
thinking is false, and each request carries its paired seed. A fresh sanitized
endpoint snapshot is required before and after each target pair.

## Run matrix and order

Exactly four valid runs are planned:

| Order | Target | Seed | Condition |
| --- | --- | --- | --- |
| 1 | `23c1549` | 17 | staged v1 |
| 2 | `23c1549` | 17 | adaptive v2.2 |
| 3 | `7d37920` | 31 | adaptive v2.2 |
| 4 | `7d37920` | 31 | staged v1 |

The condition order is counterbalanced across targets. There is one paired seed
per target, so the pilot cannot estimate seed variance or support population
claims. Seeds 47 and the unused target/condition combinations are not run
after observing results.

## Outcomes and scoring

Primary outcome: known-defect recall, scored separately for all six
target-defect opportunities and macro-averaged first within target and then
across targets. A defect counts only when the final retained report identifies
the affected behavior and actionable violation. Merely reading the affected
file, naming a nearby symbol, or reporting a different defect does not count.

Secondary outcomes:

- independently adjudicated accepted false positives and precision;
- substantive package coverage and maximum package concentration;
- valid selections, evidence-reference validity, promotions, verifier and
  critic dispositions;
- natural versus forced/structured completion;
- shell calls, model calls, input/output tokens, and elapsed time; and
- protocol violations and endpoint changes.

Zero accepted findings yields undefined precision, not 100% precision.

## Frozen predictions and decision rule

1. Median recall will remain 0/3 per target in both conditions.
2. Staged v1 will have coverage at least as high as adaptive v2.2 on both
   targets.
3. Neither condition will have a critic-accepted false positive.
4. Adaptive v2.2 will continue to expose mechanically rejected or downgraded
   evidence records; exact-quote validation is not predicted to improve recall.

A material treatment improvement requires adaptive v2.2 to recall at least two
more of the six defects than staged v1 while accepting no more false positives.
A one-defect difference is descriptive only. Process-metric improvement alone
does not establish improved assessment performance.

## Validity and stop rules

- Freeze this document and both runner digests before the first generation.
- Verify every target tar digest immediately before extraction.
- Refuse any output directory that already exists.
- If the endpoint materially changes within a target pair, invalidate both
  runs in that pair and rerun the complete pair before oracle scoring.
- Infrastructure-invalid attempts remain retained and excluded.
- Do not repair prompts or harness behavior after any model output. A
  mechanical target-identity recording defect may be repaired only by
  versioning the invalid attempt and restarting all four runs.
- Stop after four valid runs regardless of outcome.
- Run both external graders only after all reports are final, then adjudicate
  report recall without modifying the reports.
- Do not tune v2.2 on either target after this pilot.

The frozen runner SHA-256 values are:

- staged v1: `4f275d6c44b5057a34076866328d362c35bcd9f86feb9435174ce0c634325c98`;
- adaptive v2.2: `a319a1853ef1605e9b0f59a7cb84553315c7a1716fb00e922d66a4df7e1aabd8`.

## Must be built (does not exist yet)

A pilot-level validator/aggregator must verify the four-member run matrix,
target identities, runner digests, endpoint-pair stability, report and
transcript hashes, shell budgets, and grader outcomes before any result is
reported. It must not infer defect recall; recall and false-positive decisions
remain an explicit post-run adjudication layer.

## Interpretation boundary

This pilot can show whether the earlier 0/3 result transfers to two new
model-hidden oracles under unchanged harnesses. It cannot establish
generalization across repositories, compare model weights, estimate variance,
or satisfy the independently prepared Phase 2 gate. Confirmation still
requires an evaluator-independent target set and a separate preregistration.
