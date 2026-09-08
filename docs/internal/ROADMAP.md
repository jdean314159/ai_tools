# ai_tools — Roadmap

<!-- AI_TOOLS_STATUS_START -->

## Current state

See `STATUS.md` for the authoritative current state, active work priority list,
and current test gate baseline. NAV-VERIFIABLE-00 is complete with an
`inconclusive` frozen verdict; it is not an active tuning campaign.
RUN-RECORD-00 Phase 8 course portability validation is complete under
ADR-021/022. The teaching material was extracted to the sibling
`llm-failure-lab` repository on 2026-08-14. Package publication remains
deferred; its maintainer gate builds local wheels from this checkout. The
checkpoint blocks below are historical.

The latest model checkpoint is the completed adaptive staged Ornith v2.2
development comparison. Every v2.2 mechanical gate passed, but against fresh
paired staged-v1 controls median package coverage fell from 7/9 to 3/9,
concentration rose from 20.0% to 28.9%, median shell calls rose from 30 to 38,
and median input grew 3.26 times to 376,075 tokens. Recall remained 0/3 in both
conditions, with zero accepted findings. Only 6/35 v2.2 evidence records passed
independent exact-quote replay, and all nine package selections converged on
the same symbol across all three seeds. The controller enforced bounded,
auditable rejection; it did not improve judgment.

Do not tune again on the known `83e1d09` target. The selected next gate is to
obtain at least two independently prepared blinded targets with external
graders, then either preregister and run the frozen v2.2 treatment unchanged or
stop the line. No such target is currently retained. A diversified v2.3 would
be a separate development study on new targets, not a repair to this result.
Reliability-lab export remains downstream of stable commits, disclosure review,
independent packet verification, and authorized curriculum placement.
Production `repository-assessment/v1` remains deferred pending the explicit
Claude draft.

<!-- AI_TOOLS_STATUS_END -->

## Purpose

This is the ordered execution plan for the `ai_tools` monorepo.

For the next thread, keep the reusable toolkit independent of the extracted
course. PyPI publication remains a separate future decision.

## Planning assumptions

1. `ai_tools` is a local-first modular LLM harness.
2. `ai_tools` is also an educational and diagnostic environment for understanding LLM behavior.
3. `llm_harness_core` is the shared interoperability layer.
4. `llm_inspector_ui` is the main user-facing workbench.
5. A clean install/test story is a release gate, not an optional polish item.

## Phase 0 — Packaging/import stabilization — COMPLETE

### Goal

Make the repo boring to install, import, and test.

### Work

- Convert `llm_inspector_ui` to src layout.
- Fix its package metadata and pytest configuration.
- Verify `describe_ui` imports from the real implementation path.
- Establish editable-install validation in a clean virtual environment.
- Correct package install order.
- Reduce root import shims after editable installs are reliable.

### Done when

A fresh environment can install the packages in editable mode and run selected
package/cross-package tests without manual `PYTHONPATH` dependence.

## Phase 1 — Publication hygiene — COMPLETE

### Goal

Prevent local development artifacts from entering release snapshots or GitHub.

### Work

- Strengthen `scripts/check_publication_hygiene.py`.
- Fail on `.pytest_cache`, `*.egg-info`, `*.bak`, `*.orig`, `*.rej`, ad hoc patches, local DBs, and cache files unless explicitly allowed.
- Derive every setuptools distribution content root and reject private
  deployment markers in every tracked file beneath it without a suffix
  allowlist.
- Fail closed when Git cannot provide the tracked-file inventory; an exported
  archive must not pass by scanning an empty set.
- Keep checkout hygiene and archive-byte verification as separate claims; the
  checkout gate deliberately fails without repository metadata.
- Maintain the publication-hygiene CI gate.

### Done when

A clean snapshot passes the hygiene checker in CI without manual inspection.

## Phase 2 — Resolve memory package boundary — complete

### Goal

Make `engram`, ADR-009, tests, and docs agree.

### Work

- ADR-009 resolved the former split into the single supported `engram` package.
- Keep the standalone implementation as the single supported memory package.
- Retain the old backend string only as an explicit compatibility alias.

### Done when

`engram` public API contract tests pass and its code structure matches the documented role.

## Phase 3 — Standardize remaining package layouts — complete

### Goal

Keep package layout intentional and validated.

### Work

All packages use `src/` layout (ADR-014 completed `llm_engines` migration). Do not reintroduce old top-level import-shadowing trees such as `engram/engram` or `engram/__init__.py`.

### Done when

`tests/test_import_provenance.py` matches the documented layout and a fresh clone imports packages from the expected paths.

## Phase 4 — Workbench reliability and teaching value

### Goal

Make `llm_inspector_ui` a reliable teaching and diagnostic workbench.

### Work

- Validate baseline, memory, and RAG flows.
- Improve explanatory UI text.
- Keep `engram` as the default memory path.
- Add integration tests for visible traces and exported artifacts.

### Done when

A new user can launch the workbench and inspect baseline, memory-augmented, and retrieval-augmented runs.

## Phase 4A — RUN-RECORD-00 unified artifacts — PHASE 7 COMPLETE

### Goal

Give producers and inspection tools a compatible, versioned artifact surface
without discarding existing NAV run-record replay or forcing all experiments
into one schema shape.

### Work

- Completed: inventory and field/privacy crosswalk.
- Completed: ADR-021 semantics and ADR-022 ownership/public API.
- Completed: dependency-free core envelope/reader plus lossless NAV-v1 and ASC
  adapters over one shared agent body.
- Completed: Phase 3 generation recorder with deterministic MockEngine
  fixtures, common-reader cross-kind tests, and one privacy-safe live-engine
  maintainer acceptance run.
- Completed: Phase 4 Inspector library/CLI loading, kind-specific summaries,
  unsupported-version behavior, and conservative comparison.
- Completed: Phase 5 shared experiment body, ASC/NAV campaign adapters, honest
  checkpoint/final lifecycles and child-run relationships, and Inspector
  experiment summaries.
- Completed: Phase 6 exact-byte bundle writing, confined resolution,
  experiment-child packaging, privacy-reference enforcement, and Inspector
  bundle loading.
- Completed: Phase 7 privacy-safe offline course fixture, resolved-child
  Inspector summaries, deterministic rebuild, and no-GPU diagnosis gate.
- Completed: Phase 8 wheel-installed copied-course portability gate, removal of
  student-facing monorepo file dependencies, exact package pins, and a real generation-level
  provenance lab.
- Completed: recovered/modernized full language-tutor wheel and restored
  notebook 07 extraction path.
- Next gate: make the pinned distributions independently available before
  repository creation.
- Selected bounded extension: define `repository-assessment/v1` as a
  producer-owned body profile over the existing common envelope. Version 1 is
  limited to three evidence layers (model claim, model-gathered evidence, and
  independent adjudication), natural/forced completion, the model/run/repository
  fingerprint needed to reproduce the GLM/Qwen comparison, and its small
  outcome metric set. A naturally incomplete run remains an `aborted` envelope
  even when a forced report is later captured in the same body. Claude drafts
  the profile; Codex validates existing surfaces and implements the recorder.
  Defer checkpoint writing, a general metrics framework, and a separate
  comparison profile until another concrete run requires them.
- Completed experiment checkpoint: the Qwen3-Coder 30B-A3B seed-7 pilot ran
  against frozen commit `83e1d09` with an independent three-defect regression
  grader. The target fails 3/3 and corrected HEAD passes 3/3; the model recalled
  0/3, spent 42/45 shell calls in one package, and required forced reporting.
  Exact evidence is retained under `docs/projects/repository_assessment/`.
- Completed experiment checkpoint: the six-run comparison frozen in
  `docs/projects/repository_assessment/QWEN3-CODER-30B-A3B-PLANNER-RERUN-PREREGISTRATION-2026-09-06.md`
  produced median recall 0/3 in both conditions and independently corrected
  coverage of baseline 1/9 versus planner 0/9. Natural completion was baseline
  3/3 versus planner 1/3. Planning improved reported
  uncertainty calibration but contradicted the coverage and termination
  predictions. Exact results and limitations are in
  `docs/projects/repository_assessment/QWEN3-CODER-30B-A3B-PLANNER-COMPARISON-2026-09-07.md`.
- Completed assessment checkpoint: the Q4_0 versus Q8_0 comparison frozen in
  `docs/projects/repository_assessment/QWEN3-CODER-30B-A3B-KV-CACHE-COMPARISON-PREREGISTRATION-2026-09-07.md`.
  Both conditions had median recall 0/3 and corrected coverage 1/9. Q8_0
  changed every trajectory, concentrated all seeds on Engram, and produced
  three false positives versus two under Q4_0, without improving termination
  or median whole-run time. See
  `docs/projects/repository_assessment/QWEN3-CODER-30B-A3B-KV-CACHE-COMPARISON-2026-09-07.md`.
- Qwen cache-specific follow-on: none selected. A larger turn budget, F16
  cache, mixed K/V precision, and counterbalanced restart design remain
  separate experiments.
- Completed assessment checkpoint: the paired adaptive staged Ornith v2.2
  development campaign passed every frozen mechanical gate but reduced median
  coverage from 7/9 to 3/9, raised median concentration from 20.0% to 28.9%,
  and used 3.26 times the paired-v1 median input. Recall stayed 0/3 in all six
  runs and neither condition accepted a finding. Exact-quote replay invalidated
  29/35 v2.2 evidence records. The known target is closed to tuning; any
  unchanged confirmation requires independently prepared blinded targets and
  a separate preregistration.

### Done when

Two distinct producers emit or adapt to validated records, NAV counterfactual
replay remains compatible, and unknown versions and sensitive fields fail
according to the accepted policy.

## Phase 5 — Reference application

### Goal

Make `language_tutor` the canonical example of composing the libraries.

### Work

- Align with modern `llm_engines`.
- Use `engram` as the supported memory implementation.
- Expose useful observability hooks.

### Done when

The app demonstrates the current stack rather than older integration patterns.

## Phase 6 — Agent work

### Design guidance

Before expanding `agent_lib` or starting the ASC rebuild, read
`docs/design/AGENT_BUILD_NOTES.md`. It captures settled reasoning on
co-evolution, the worker/mentor pattern, gated oversight, long-horizon loops,
and context-rot reduction via Engram primitives, plus the cheapest first move.

### Goal

Proceed with `agent_lib` only after the package foundation is stable.

### Work

- Keep policy and sandbox boundaries explicit.
- Integrate with traces and task manifests.
- Avoid adding orchestration complexity before basic install/test reliability is solved.

### Done when

Agent workflows are inspectable, constrained, and testable.

## Standing rule

Do not add new capabilities on top of unstable package/import behavior. Stabilize the foundation first.

## Course extraction pre-flight

Before extracting course material into a separate repository, decide whether
these package-internal guides remain with their libraries or move with the
course:

- `llm_inspector_ui/WORKBENCH_TEACHING_GUIDE.md`
- `llm_harness_core/EVALUATION_WALKTHROUGH.md`

They remain in place for now because their links are package-internal and do
not create a library-to-course dependency.
