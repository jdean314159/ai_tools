# Fresh Claude thread handoff

- Prepared: 2026-07-24
- Repository: `/home/cybernaif/repos/ai_tools`
- Branch: `main`
- Current implementation checkpoint: `abcc2f0`

This is the shortest reliable entry point for a fresh Claude thread. Treat the
repository as authoritative; chat summaries are secondary.

## Read order

1. `AGENTS.md` — repository working and testing rules.
2. `docs/design/VISION.md` — architectural intent.
3. `docs/internal/STATUS.md` — current package and project posture.
4. `docs/internal/ROADMAP.md` — current planning boundary.
5. This file.
6. For the most recent agent-navigation work:
   - `docs/projects/agent_lib/NAV-VERIFIABLE-00-VALIDATION.md`
   - `docs/projects/agent_lib/NAV-VERIFIABLE-00-SPEC.md`
   - `docs/projects/agent_lib/NAV-VERIFIABLE-CAMPAIGN-V1.md`

Read package READMEs only for the package involved in the next task. Do not
start by reading the historical sections of `SESSION_HANDOFF.md`.

## Current posture

There is no active implementation campaign. The most recent campaign,
`NAV-VERIFIABLE-00`, is complete and should not be extended by silently
changing its frozen protocol.

`ai_tools` remains a modular, local-first LLM harness and inspection laboratory.
The package spine is stable enough for package-scoped work; `agent_lib` and both
loop-guard packages remain experimental.

Recent commits:

- `abcc2f0` — ran and recorded the NAV verifiable paired campaign;
- `dd8c7f2` — built its mechanically selected candidate campaign;
- `8a4fd71` — added the shared-schema ceiling verdict;
- `364fed6` / `a0e5189` — froze arm, selection, and campaign policy before data.

At the last checkpoint the `agent_lib` package suite passed with `150 passed`.
Run tests again before claiming the current tree passes.

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

## Reasonable next work

Choose a new task only after stating the user-visible goal and validation gate.
Current non-blocking options are:

- workbench reliability and teaching value (`ROADMAP` Phase 4);
- reference-application modernization (`ROADMAP` Phase 5);
- a separately scoped evidence-precision/grounded-claims investigation;
- package documentation or fresh-clone verification;
- a new agent experiment with a separately predeclared protocol.

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
