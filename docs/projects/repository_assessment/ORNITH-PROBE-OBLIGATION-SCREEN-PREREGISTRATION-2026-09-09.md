# Ornith empirical-probe-obligation screen preregistration — 2026-09-09

Status: frozen before the first model generation request.

This is a two-run exploratory mechanism screen. It is not a confirmatory model
comparison and does not reopen target `7d37920` for prompt tuning. The target
and its three-defect oracle are already known to the evaluator. The model-facing
prompt, tools, and sandbox contain no defect descriptions, grader source, fix
messages, corrected-tree content, or treatment-only target terms.

## Authorization and verification boundary

On 2026-09-09 the repository owner gave Codex consolidated authority to design,
implement, validate, operate, adjudicate, document, and commit this screen. That
removes the earlier drafter/operator separation. Codex is therefore the
designer, implementer, validator author, operator, adjudicator, and committer.
No independent-verification claim will be made.

The pre-generation commit, exact run evidence, external grader, negative and
positive gate controls, and post-run adjudication are retained so another
reviewer can independently verify the result later.

## Question

Holding Ornith, target, seed, single-context harness, tool surface, budgets, and
endpoint fixed, does a controller-enforced obligation to execute and cite a
behavioral probe change known-defect recall relative to an otherwise identical
probe-optional control?

The manipulated intervention consists of one generic model-visible obligation
message plus controller enforcement. Probe execution capability is not the
manipulation: both arms receive the identical instrumented probe tool.

## Frozen target and oracle boundary

| Field | Frozen value |
| --- | --- |
| commit | `7d37920a81a9cb672c24af3a55557621e5c5009f` |
| tree | `0177f7c8288a42ca771084c42362ddb6f90a9640` |
| uncompressed tar SHA-256 | `02e68e5c7cb349f1c6e3011fd6f0265ebdf6a87fa753bef932fabfd271bd8769` |
| corrected reference | `8e2e9e5f2c45c935bdc3afa2479a08dc702b44db` |
| valid defect denominator | 3 |
| external grader SHA-256 | `6df8cf5c9ad7eb29f06e9e0db34dedd4801bdfaa66860028b53f98ddb484efe8` |

The grader and evaluator-only defect inventory remain outside `/workspace` and
must not be executed or used to inspect reports until both model reports are
final. `docs/internal` and `docs/projects` are masked with empty tmpfs mounts in
both arms.

## Grounded reuse

- The runner imports the maintained single-context request, transcript, report,
  clipping, hashing, fingerprint, and coverage helpers from
  `tools/run_planner_assessment.py`; the import is explicit at
  `tools/run_probe_obligation_screen.py:40-52`.
- The read-only, network-unshared sandbox and historical-document masks come
  from `tools/run_staged_assessment.py`; the probe runner calls that exact path
  at `tools/run_probe_obligation_screen.py:285-301`, and every ordinary shell
  call uses it at `tools/run_probe_obligation_screen.py:703`.
- Both conditions receive the same shell, `run_probe`, and `submit_report`
  schemas at `tools/run_probe_obligation_screen.py:597-608`. The treatment-only
  message is appended at lines 586-591.
- The target identity, model, seed, 45-action budget, and 60-model-turn fail-safe
  are constants at `tools/run_probe_obligation_screen.py:57-69`.
- The existing target grader is maintained at
  `tools/test_engram_boundary_defects_at_7d37920.py`; this screen does not alter
  it.

## Must be built (does not exist in the earlier harnesses)

The screen adds three experiment-local mechanisms:

1. an instrumented `run_probe` tool that independently observes loaded module
   origins;
2. a submission validator that checks probe execution, target-code loading,
   observable output, and exact report citation; and
3. a screen-level validator for freeze identities, gate controls, endpoint
   continuity, run artifacts, grader outcomes, and adjudication structure.

All three are frozen by the manifest and pre-generation commit. They are not
production `repository-assessment/v1` contracts.

## Conditions held fixed

Both runs use:

- model `Ornith-1.5-35B-Q4_K_M.gguf`;
- target `7d37920`, seed 31, temperature zero, and thinking false;
- one continuous context with the same shared system and user prompts;
- identical shell, `run_probe`, and `submit_report` tool schemas;
- a 45-action budget shared by shell and probe calls;
- a 60-model-turn fail-safe;
- the same 120-second isolated-command timeout;
- a read-only `/workspace`, private temporary storage, no network, no host
  execution fallback, and masked historical internal/project documents; and
- the same report schema and post-run adjudication layer.

The server is expected to retain the previously characterized user-reported
Q4_0 K/V cache, flash attention, Jinja template, and draft-MTP configuration.
A sanitized endpoint snapshot is required before the first run and after the
second.

## Manipulated intervention

The `probe_optional` control receives no probe requirement. It may use
`run_probe` voluntarily and may submit with `probe_call_id=none`.

The `probe_required` treatment receives the generic obligation at
`tools/run_probe_obligation_screen.py:87-92`. The controller rejects every
final submission until one probe satisfies the frozen predicate and the report
cites it. The treatment-only model-visible strings are rejected before launch
if they contain `engram`, `tenant`, the stem `delet`, or `episode`.

No package, symbol, behavior, or suspected defect is suggested by the
intervention.

## Mechanical probe-satisfaction proposition

A probe satisfies the intervention exactly when:

1. the model supplies a non-empty Python file accepted under the private
   temporary mount;
2. that file executes inside the run's bubblewrap sandbox;
3. controller instrumentation observes at least one loaded module whose
   resolved file is below `/workspace`;
4. the probe produces non-empty stdout or stderr; and
5. the final report cites the satisfying tool-call ID and an exact 8-to-500
   character excerpt of its retained output.

The gate does not require exit code zero: a target-code exception can itself be
an observation. A random controller marker prevents the model-authored script
from fabricating module-load attestation.

Before generation, the real sandbox must demonstrate both directions:

- negative control: an executed, output-producing script with no repository
  import is rejected with `no_workspace_module_loaded`; and
- positive control: an executed, output-producing script importing a repository
  module is accepted and records its `/workspace` origin.

The controls are synthetic gate tests, not model or defect results.

## Run matrix and order

| Order | Condition | Target | Seed |
| ---: | --- | --- | ---: |
| 1 | `probe_optional` | `7d37920` | 31 |
| 2 | `probe_required` | `7d37920` | 31 |

Runs are sequential against one unchanged endpoint. Fixed order is disclosed;
with one pair, order effects and seed variance cannot be estimated.

## Outcomes

Primary outcome: post-run known-defect recall out of the same three valid
target defects. A defect counts only when the retained report identifies the
affected behavior and actionable violation. File proximity, package naming, or
an unrelated finding does not count.

Secondary outcomes are accepted false positives, report disposition, natural
or forced completion, structural non-completion, satisfying and attempted probe
calls, shell calls, total actions, package distribution, descriptive coverage,
model calls, tokens, elapsed time, gate rejections, and protocol violations.

Probe authoring and execution occur atomically in one `run_probe` action; both
event counts are recorded, while budget displacement counts that action once.
Coverage, token, and concentration values from historical staged-v1 runs are
context only, not controlled contrasts.

## Frozen predictions and asymmetric decision rule

1. The treatment will satisfy the probe gate before any accepted submission.
2. The control may or may not probe voluntarily; no prediction is made about
   that behavior.
3. Based on prior zero recall under multiple Ornith harnesses, the modal
   expectation is 0/3 recall in both arms. This is a prediction, not a stopping
   rule.
4. The intervention may displace shell investigation within the 45-action
   budget; separate action counts will expose that effect.

A positive screen requires treatment recall to exceed control recall by at
least one valid defect, with no increase in accepted false positives. That
triggers a separately preregistered, multi-seed comparison; it is not itself a
finding about general effectiveness.

Any other valid result is recorded as `screen_did_not_trigger`. A negative
one-pair screen provides no evidence of absence and does not bound whether the
intervention can improve recall under another seed, target, model, or budget.
Structural non-completion is not scored as zero recall.

## Completion outcomes

The frozen outcome vocabulary distinguishes:

- `natural_valid_submission`;
- `natural_after_gate_block`;
- `forced_valid_submission`;
- `structural_noncompletion_probe_unsatisfied`; and
- `forced_invalid_submission`.

If the treatment reaches either budget ceiling without a satisfying probe, no
forced no-probe report is accepted. The run ends as structural non-completion.

## Freeze, correction, and invalidation rules

- The preregistration, runner, prompt, tool schemas, controller policy,
  validator, invalidation rules, reference fingerprint, and grader are committed
  with recorded SHA-256 values before the first model request.
- The target archive digest and embedded commit, sandbox masks, and positive and
  negative gate controls must pass immediately before generation.
- Refuse existing output directories.
- If the endpoint materially changes between snapshots, both runs are invalid.
- After the first generation request, do not change prompts, tools, gate
  semantics, validator semantics, grader, target, seed, budgets, or
  invalidation rules within this protocol version.
- Any post-generation infrastructure correction retains the failed attempt,
  identifies the preceding model output, is explicitly labelled post-hoc,
  creates a new protocol version, and restarts both arms before oracle scoring.
- Do not add an invalidation rule after observing an outcome.
- Run the external grader and perform report adjudication only after both model
  reports are final.
- Stop after one valid pair. Do not tune on this oracle after the result.

## Frozen identities

The machine-readable identities are in
`runs/2026-09-09-ornith-probe-obligation-screen/freeze-manifest.json`.

- runner SHA-256: `a2fac005d03f3be8d6a72558e9861fbc5f9844ba639fbee67b9a42367404103d`;
- validator SHA-256: `3cf25ccbd844282fe1fe6a7ef4ae9c300497b78db7162d392c1b2a9f0ac9af86`;
- controller policy SHA-256: `571e7c25ada6c6b9f0bd29b0b4b5ec69a1de248c4c1f41a4f9a94ff1cc341ad8`.

## Interpretation boundary

This screen can identify whether the probe-obligation intervention changes one
Ornith trajectory on one known target and seed when compared with a fresh,
otherwise identical control. It cannot estimate variance, remove evaluator
knowledge, establish generalization, compare context topologies, or establish
that probe obligation is generally effective or ineffective. Later independent
review is possible from retained artifacts but is not part of this run.
