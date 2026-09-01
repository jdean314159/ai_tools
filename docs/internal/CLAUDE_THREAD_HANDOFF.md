# Fresh Claude thread handoff

- Prepared: 2026-08-13
- Repository: the checkout containing this file (`git rev-parse --show-toplevel`)
- Branch: `main`
- Current repository checkpoint: inspect `git log -1`; RUN-RECORD-00 Phase 2
  is complete and included in the latest cleanup checkpoint.

This is the shortest reliable entry point for a fresh Claude thread. Treat the
repository as authoritative; chat summaries are secondary.

## Read order

1. `AGENTS.md` — repository working and testing rules.
2. `docs/design/VISION.md` — architectural intent.
3. `docs/internal/STATUS.md` — current package and project posture.
4. `docs/internal/ROADMAP.md` — current planning boundary.
5. This file.
6. `docs/projects/RUN-RECORD-00-unified-run-artifacts.md` and
   `RUN-RECORD-00-PHASE-2-COMPATIBILITY.md` — active project and completed gate.
7. For the relevant prior agent-navigation implementation:
   - `docs/projects/agent_lib/NAV-VERIFIABLE-00-VALIDATION.md`
   - `docs/projects/agent_lib/NAV-VERIFIABLE-00-SPEC.md`
   - `docs/projects/agent_lib/NAV-VERIFIABLE-CAMPAIGN-V1.md`

Read package READMEs only for the package involved in the next task. Do not
start by reading the historical sections of `history/SESSION_HANDOFF.md`.

## Current posture

RUN-RECORD-00 Phase 7 is complete under accepted ADR-021 and ADR-022. The next
bounded consumer slice is unselected. The most recent completed
empirical campaign, NAV-VERIFIABLE-00, remains closed and must not be extended
by silently changing its frozen protocol.

`ai_tools` remains a modular, local-first LLM harness and inspection laboratory.
The package spine is stable enough for package-scoped work; `agent_lib` and both
loop-guard packages remain experimental.

Relevant historical commits:

- `abcc2f0` — ran and recorded the NAV verifiable paired campaign;
- `dd8c7f2` — built its mechanically selected candidate campaign;
- `8a4fd71` — added the shared-schema ceiling verdict;
- `364fed6` / `a0e5189` — froze arm, selection, and campaign policy before data.

Phase 4 Inspector artifact and integration gates pass. Its full suite has one
unrelated optional-tokenizer-dependent Engram golden mismatch, documented in
`RUN-RECORD-00-PHASE-4-INSPECTOR.md`.

## RUN-RECORD-00 — what the next thread must understand

The phrase “build RunRecord” originally hid an important repository fact. There
is no public cross-package `RunRecord` class, but there **is** an executable,
versioned NAV run-record implementation:

- `agent_lib/src/agent_lib/eval/repo_navigation.py:1672-1713` renders schema v1;
- `agent_lib/examples/repo_navigation_eval.py:266-277` writes
  `run-record.json`;
- `agent_lib/examples/nav_counterfactual_finalize.py` reads that artifact.

Phase 0 inventoried ASC, `GenerationResponse`, inspector `Trace`, and campaign
outputs. Phase 2 added the dependency-free core envelope plus lossless NAV-v1
and ASC adapters. Phase 3 added a generation recorder, MockEngine cross-kind
fixtures, common-reader semantic checks, and a privacy-safe live Ollama
acceptance run. Phase 4 added Inspector library/CLI loading, separate
generation/agent summaries, unsupported-version behavior, and comparison that
does not infer model identity from labels.

Phase 5 added a shared experiment body plus adapters for ASC's mutable aggregate
report and NAV's paired campaign files. Completed child runs remain separate
artifacts linked by ID; ASC timeout rows remain aggregate items, not fabricated
runs. Inspector now summarizes both experiment profiles. Read
`RUN-RECORD-00-PHASE-5-EXPERIMENTS.md` before selecting the next slice.

Phase 6 added atomic portable local-directory bundles, exact-byte SHA-256 child
attachments, confined resolution and tamper detection, a new derived identity
for bundled experiment snapshots, and Inspector bundle-directory loading. Read
`RUN-RECORD-00-PHASE-6-BUNDLES.md` before selecting the next slice.

Phase 7 added a single privacy-safe, no-GPU course fixture from the ASC
worker-only campaign. It forced generic Inspector traversal and sanitized
summaries for resolved child artifacts. The student can diagnose the visible
oracle false negative and false positive using Inspector output alone. Read
`RUN-RECORD-00-PHASE-7-COURSE-FIXTURE.md`; do not infer a full curriculum
rewrite from this bounded pilot.

## What the NAV investigation established

The investigation began with budget-exhausting repository navigation despite
high evidence recall. Three wrapper-level signals were explored and closed:

1. reasoning-text repetition;
2. repeated/overlapping tool actions;
3. observable evidence saturation.

The durable finding was that a thin wrapper cannot recover an information goal
the planner never externalized. This led to an explicit task-goal ledger and a
new, locally verifiable navigation track rather than redefining NAV-TEST-00.

The final paired campaign compared:

- `no_ledger`: free navigation plus the same typed final relation schema;
- `ledger`: identical configuration plus task-specific per-step goal state.

Both arms used the same model, task, seed, tools, budget, AST oracle, claim
schema, canonicalizer, and scorer. Fourteen tasks were selected mechanically:
four local, four intermediate, and six exploratory.

Formal frozen verdict: **`inconclusive`**.

Primary exploratory result:

| Metric | no-ledger | ledger |
|---|---:|---:|
| termination | 0/6 | 3/6 |
| relation-correct | 0/6 | 2/6 |
| exact-correct | 0/6 | 0/6 |
| aggregate tokens | 124,583 | 99,313 |

The ledger produced a real directional termination/cost effect, but exact
correctness remained zero. The two relation-correct ledger answers failed
through over-citation; another terminating answer contained an unsupported
relation. The predeclared decision rule therefore did not authorize broader
shadow adoption.

Do not call this a ledger success, a NAV-TEST-00 pass, or an autonomous-agent
result. Do not weaken the scorer or retrofit the decision rule. The exact
result and protocol caveat are in
`agent_lib/eval_manifests/nav_verifiable_campaign_v1/live-result-summary.json`.

## Important methodological caveat

One selected-task runner smoke exposed missing symmetric runtime constraints:
empty relation arrays were permitted and definition empty-field semantics were
unstated. That smoke was excluded. Both arms were then given the same
nonempty-claim/observed-evidence contract and the full campaign ran under it.
No task, tier, oracle, scorer, or decision threshold changed, but this means the
campaign is not a pristine first-contact dataset. Preserve that caveat.

## Closed directions — do not restart without a new forcing result

- `NAV-TEST-00` remains a strict autonomous-navigation failure.
- The text and action loop guards are experimental artifacts, not validated
  runtime fixes.
- Budget-fraction finalization is harness-assisted fallback work, not
  autonomous navigation.
- Neural memory is parked, output-isolated, and default-off.
- The mail assistant is a harvested example/case study, not the active product
  direction.
- Do not prompt-tune or schema-tune against the completed NAV campaign.

## Work after the completed Phase 4 gate

Workbench reliability, reference-application modernization, grounded-claims
work, and fresh-clone verification remain legitimate later projects. They do
not imply they should be combined into one successor slice unless the user explicitly
changes direction.

Over-citation is a known model behavior, not a trivial JSON-schema fix. A schema
can require single-line references but cannot know the task-specific number of
required references without oracle knowledge. Treat deterministic
post-processing against an answer key as harness assistance, not improved
planner correctness.

## Working rules for the next thread

- Inspect before changing; preserve unrelated work in a dirty tree.
- Use `rg` first and `apply_patch` for edits.
- Keep package defaults backward-compatible.
- Run targeted tests, then the relevant package gate.
- Record negative and inconclusive results without reinterpretation.
- Update `STATUS.md` and this handoff when the standing posture changes.
