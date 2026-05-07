# LLM_HANDOFF.md

This file is the operational handoff state for AI-assisted development of `ai_tools`.

Update this file after every major development push and before starting a new major task. Do not rely on chat history as the only source of project state. Chat history is not canonical. This file, the current working tree, and the root architecture documents are canonical.

The goal is to let another assistant resume work without re-deriving the architecture, repeating old decisions, or continuing from stale assumptions.

---

## Current status

Status: **WIP / broken checkpoint**

Current working form: **active local development directory**, not a clean release repository. Generated artifacts, rejected patch files, caches, and local test data may be present. Do not interpret those artifacts as the main architectural problem unless preparing a publication snapshot.

Current focus:

- Stabilize the partially completed `engram_lite` -> `engram` facade migration.
- Restore the augmenter-spine integration test.
- Align docs, package roles, and tests with the selected memory architecture.

Last externally observed checkpoint:

- Archive: `ai_tools_6May.tar.gz`
- Inspection date: 2026-05-06
- Inspector: ChatGPT

Confidence level: **medium**

Reason:

- The broad architecture is readable from root docs and ADRs.
- The working tree is mid-migration.
- At least one advertised integration smoke test currently fails during import.

---

## Read these first

Before making changes, read these files in order:

1. `VISION.md`
2. `CURRENT_STATE.md`
3. `PACKAGE_ROLES.md`
4. `ADR_INDEX.md`
5. `adr/ADR-007-engram-lite-as-engram-facade.md`
6. `LLM_HANDOFF.md`
7. `NEXT_STEP.md`

For teaching-related work, also read:

1. `START_HERE.md`
2. `LEARNING_PATH.md`
3. `course/README.md`
4. `course/CURRICULUM.md`

---

## Current architectural decision in progress

`ADR-007` says `engram_lite` is becoming a curated facade over `engram`.

Current intended direction, based on `PACKAGE_ROLES.md` and `ADR-007`:

- `engram` is the canonical implementation for memory primitives.
- `engram_lite` exposes the beginner-safe/default public API.
- `engram_lite` should not retain an independent full implementation once features have been reconciled.
- The lite API should be protected by public API contract tests.
- Students should outgrow `engram_lite` by changing imports or configuration, not by migrating a separate data model.

Do not reverse this direction without explicitly updating:

- `adr/ADR-007-engram-lite-as-engram-facade.md`
- `PACKAGE_ROLES.md`
- `VISION.md`
- `CURRENT_STATE.md`
- `README.md`
- `engram_lite/README.md`
- related integration tests

---

## Current package roles

Treat these package roles as the current baseline:

| Package | Role |
|---|---|
| `llm_harness_core` | Shared contracts and portable schemas. Keep small and dependency-light. |
| `llm_engines` | Model/backend access layer with normalized capabilities and responses. |
| `engram` | Full memory runtime and canonical implementation for shared memory primitives. |
| `engram_lite` | Curated beginner/default facade over `engram`. |
| `rag_lib` | Retrieval and source-grounded QA patterns with visible evidence flow. |
| `llm_inspector` | Core trace/evaluation inspection logic. |
| `llm_inspector_ui` | Streamlit workbench for comparing baseline, memory, retrieval, and later agent runs. |
| `language_tutor` | Reference application showing how the layers compose. |
| `agent_lib` | Inspectable agent orchestration, programming workflow, policy checks, and safety labs. |
| `course` | Teaching notebooks, starter projects, and curriculum manifest. |
| `integration_tests` | Cross-package behavioral validation and contract-drift detection. |

---

## What appears changed in the current WIP snapshot

Observed WIP changes include:

- `engram_lite/src/engram_lite/__init__.py` re-exports many symbols from `engram`.
- `engram/engram/memory/augment.py` defines `ContextResult`, `AugmentRequest`, `AugmentResult`, and `PromptAugmenter`.
- `engram_lite/src/engram_lite/contracts.py` is currently empty.
- `engram_lite/src/engram_lite/project_memory.py` still contains substantial implementation code and still imports several local lite subpackages.
- `PACKAGE_ROLES.md` describes `engram_lite` as a facade over `engram`.
- `engram_lite/README.md` still describes `engram_lite` mostly as an independent lightweight memory layer.
- `adr/ADR-007-engram-lite-as-engram-facade.md` appears to contain duplicated ADR text in the observed archive.
- Multiple `.rej`, `.orig`, `.bak`, cache, and local artifact files may exist because this is an active development directory.

Interpretation:

- The architecture decision has been made.
- The migration is only partially complete.
- The next work should repair compatibility and tests before adding new features.

---

## Current known failures

### Failing integration smoke test

Command run from repo root:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=llm_inspector_ui:llm_harness_core/src:llm_inspector/src:engram_lite/src:engram:rag_lib/src:llm_engines:. \
python -m pytest -q integration_tests/test_augmenter_spine.py
```

Observed result:

```text
ImportError while importing test module 'integration_tests/test_augmenter_spine.py'.
from engram_lite.contracts import AugmentRequest
ImportError: cannot import name 'AugmentRequest' from 'engram_lite.contracts'
```

Immediate cause:

- `engram_lite/src/engram_lite/contracts.py` is empty.
- `integration_tests/test_augmenter_spine.py` still imports `AugmentRequest` from `engram_lite.contracts`.
- `AugmentRequest` now exists in `engram.memory.augment` and is re-exported from `engram_lite.__init__`, but the legacy module path is broken.

Most likely first repair:

- Restore `engram_lite.contracts` as a compatibility re-export shim, or update all downstream imports to the new canonical path.
- Prefer a compatibility shim first, because it is small, low-risk, and preserves downstream callers during the facade migration.

Candidate content:

```python
from engram.memory.augment import ContextResult, AugmentRequest, AugmentResult, PromptAugmenter

__all__ = [
    "ContextResult",
    "AugmentRequest",
    "AugmentResult",
    "PromptAugmenter",
]
```

After that, rerun the augmenter-spine test before making broader changes.

---

## Validation commands

Use the relevant subset before handing work back.

### Minimum stabilization check

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=llm_inspector_ui:llm_harness_core/src:llm_inspector/src:engram_lite/src:engram:rag_lib/src:llm_engines:. \
python -m pytest -q integration_tests/test_augmenter_spine.py
```

### Teaching artifact check

```bash
PYTHONDONTWRITEBYTECODE=1 \
python scripts/check_teaching_artifacts.py
```

### Publication hygiene check

Publication hygiene is advisory during active local development but required before creating a public/release archive.

```bash
PYTHONDONTWRITEBYTECODE=1 \
python scripts/check_publication_hygiene.py
```

Expected during active development:

- This may fail because the local working folder contains caches, `.pyc` files, local DBs, rejected patches, and other artifacts.
- Do not spend stabilization time on this unless preparing a clean snapshot.

### Optional full-Engram integration path

```bash
AI_TOOLS_TEST_FULL_ENGRAM=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=llm_inspector_ui:llm_harness_core/src:llm_inspector/src:engram_lite/src:engram:rag_lib/src:llm_engines:. \
python -m pytest -q integration_tests/test_augmenter_spine.py::test_full_engram_augmenter_normalizes_or_skips_cleanly
```

Only run this when intentionally validating the full `engram` path.

---

## Do not start yet

Do not start these until the augmenter-spine import failure is fixed:

- new agent features
- new teaching decks/notebooks
- new memory features
- large-scale deletion of `engram_lite` internals
- package renaming or broad import rewrites
- publication hygiene cleanup as the primary task

Reason:

- The current migration is at risk of splitting public APIs from implementation. Fix the smallest failing compatibility seam first.

---

## Next intended step

Run this first:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=llm_inspector_ui:llm_harness_core/src:llm_inspector/src:engram_lite/src:engram:rag_lib/src:llm_engines:. \
python -m pytest -q integration_tests/test_augmenter_spine.py
```

Then inspect:

1. `engram_lite/src/engram_lite/contracts.py`
2. `engram/engram/memory/augment.py`
3. `engram_lite/src/engram_lite/__init__.py`
4. `integration_tests/test_augmenter_spine.py`
5. `llm_inspector_ui/services/augmenter_service.py`

Then do:

- Restore `engram_lite.contracts` compatibility exports or update imports consistently.
- Rerun the augmenter-spine test.
- If the import failure is resolved but later failures appear, fix the next smallest compatibility seam.

Expected result:

- `integration_tests/test_augmenter_spine.py` should collect successfully.
- Baseline, `engram_lite`, and fake RAG tests should pass or expose the next specific migration defect.
- Full `engram` path should skip cleanly unless `AI_TOOLS_TEST_FULL_ENGRAM=1` is set.

---

## Files the next assistant should inspect first

1. `engram_lite/src/engram_lite/contracts.py` — currently empty; immediate import failure source.
2. `engram/engram/memory/augment.py` — likely canonical home for augmentation contracts.
3. `engram_lite/src/engram_lite/__init__.py` — current facade re-export surface.
4. `engram_lite/src/engram_lite/project_memory.py` — still a large lite implementation, not yet a thin facade.
5. `PACKAGE_ROLES.md` — says lite is a facade over full `engram`.
6. `engram_lite/README.md` — may lag the facade decision.
7. `adr/ADR-007-engram-lite-as-engram-facade.md` — accepted decision, but inspect for duplicate text.

---

## Handoff discipline for each major push

After each major push, update this file with:

1. What changed
2. Files modified or added
3. Current architectural decision being implemented
4. Tests run
5. Test results
6. Known failures or incomplete work
7. Next intended step
8. Exact command the next assistant should run first
9. Files the next assistant should inspect first
10. Warnings about partially applied patches, rejected hunks, or docs/code mismatch

Also update `NEXT_STEP.md` with the immediate resume action.

---

## Instructions for the next assistant

Before making changes:

1. Read this file.
2. Read `NEXT_STEP.md`.
3. Check `git status --short`.
4. Inspect the files listed above.
5. Run the first command listed under `NEXT_STEP.md` unless it is clearly obsolete.
6. Do not start a new architectural direction without updating this file.
7. After the next major push, update this file again.

When handing work back, use this compact format:

```markdown
Changed:
- ...

Validated:
- `command` -> result

Not validated:
- `command or area` -> reason

Known failures:
- ...

Next recommended fix:
- ...
```

---

## Last handoff update

Date:

- 2026-05-06

Updated by:

- ChatGPT

Summary:

- Replaced malformed handoff content with a structured operational handoff.
- Added current WIP diagnosis for the `engram_lite` facade migration.
- Recorded the current augmenter-spine import failure and the likely first repair.

## What changed in the last push

Summary:
- Restored `engram_lite.contracts` as a compatibility shim over canonical augmenter contract types in `engram.memory.augment`.
- This repaired the legacy import path used by `integration_tests/test_augmenter_spine.py`.

Files modified:
- `engram_lite/src/engram_lite/contracts.py`

Important implementation notes:
- `engram_lite.contracts` now re-exports:
  - `AugmentRequest`
  - `AugmentResult`
  - `ContextResult`
  - `PromptAugmenter`
- This is a compatibility repair, not the final architecture.
- The broader `engram_lite` / `engram` dependency direction still needs to be settled.

## Tests and validation

Tests run:
```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
python -m pytest -q integration_tests/test_augmenter_spine.py
```
Results:
Passed.

- Corrected package dependency direction for the current `engram_lite` facade migration.
- Removed `engram-lite` from `engram/pyproject.toml`.
- Added `engram` to `engram_lite/pyproject.toml`.
- Verified `integration_tests/test_augmenter_spine.py` still passes.
- Verified `scripts/check_teaching_artifacts.py` still passes.


---

## Latest checkpoint

Status:
- Stabilization checkpoint reached.

What changed:
- Restored `engram_lite.contracts` as a compatibility shim over canonical augmenter contract types in `engram.memory.augment`.
- Corrected package dependency direction:
  - `engram` no longer depends on `engram-lite`.
  - `engram-lite` now depends on `engram`.
- Deduplicated ADR-007:
  - `adr/ADR-007-engram-lite-as-engram-facade.md` now has one ADR body.
  - `ADR_INDEX.md` now has one ADR-007 entry.

Validation:
```bash
```
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
python -m pytest -q integration_tests/test_augmenter_spine.py

PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
python scripts/check_teaching_artifacts.py

Results:
Both passed.

Known remaining work:
Review engram_lite/README.md for facade wording and typo cleanup.
Run package-level tests for engram_lite and engram.
Eventually remove or move active-development artifacts before publication.

---

## Latest checkpoint update

Status:
- Facade stabilization checks passed.

Additional validation:
- `engram_lite/tests/test_public_api_contract.py` passed.
- `integration_tests/test_augmenter_spine.py` passed.
- `scripts/check_teaching_artifacts.py` passed.

Current interpretation:
- `engram_lite` is now being treated as a curated compatibility facade over canonical `engram` implementation.
- `engram_lite.contracts` exists to preserve older public imports while re-exporting canonical augmenter contract types.
- Package metadata now follows the intended direction:
  - `engram-lite` depends on `engram`.
  - `engram` does not depend on `engram-lite`.

Known remaining work:
- Review `engram_lite/README.md` for facade wording and typo cleanup.
- Run broader package-level tests for `engram_lite`, `engram`, and affected language tutor integrations.
- Decide whether pre-existing Claude migration changes are ready to group into a commit/checkpoint.
- Move or ignore active-development artifacts before publication.

- Fixed engram compatibility regressions found by broader engram tests:
  - `SynthesisExtractor` now backfills counter fields for tests/legacy construction via `__new__`.
  - `MemoryContext.procedural` is optional for older constructor calls.
  - `Telemetry` restores legacy `sink`, `sinks`, and `enabled` accessors.
- Targeted failing tests now pass.
- Full `engram/tests` rerun should be recorded with result.

---

## Engram package test checkpoint

Status:
- Full `engram/tests` suite passed after compatibility repairs.

Repairs made:
- `SynthesisExtractor` now backfills counter fields for legacy/test construction via `__new__`.
- `MemoryContext.procedural` is now optional for older constructor calls.
- `Telemetry` restores legacy read accessors:
  - `enabled`
  - `sinks`
  - `sink`

Validation run:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
    python -m pytest -q engram/tests

Result:
- 836 passed, 6 skipped, 188 warnings.

Notes:
- These were compatibility repairs, not new architecture.
- The broader `engram` package is now in a much better checkpoint state.

---

## Integration test checkpoint

Status:
- Full `integration_tests` suite passed after facade and engram compatibility repairs.

Validation run:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
    python -m pytest -q integration_tests

Result:
- Passed.

Current green checks:
- `engram_lite/tests`
- `integration_tests/test_augmenter_spine.py`
- `scripts/check_teaching_artifacts.py`
- `engram/tests`
- `integration_tests`

Next validation target:
- `language_tutor/tests`

---

## Language tutor test checkpoint

Status:
- Full `language_tutor/tests` suite passed after facade and engram compatibility repairs.

Validation run:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
    python -m pytest -q language_tutor/tests

Result:
- Passed.

Current green checks:
- `engram_lite/tests`
- `integration_tests/test_augmenter_spine.py`
- `scripts/check_teaching_artifacts.py`
- `engram/tests`
- `integration_tests`
- `language_tutor/tests`

Next validation target:
- `llm_inspector/tests`

---

## Inspector test checkpoint

Status:
- Full `llm_inspector/tests` suite passed.

Validation run:

    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 \
    python -m pytest -q llm_inspector/tests

Result:
- Passed with warnings only.

Current green checks:
- `engram_lite/tests`
- `integration_tests/test_augmenter_spine.py`
- `scripts/check_teaching_artifacts.py`
- `engram/tests`
- `integration_tests`
- `language_tutor/tests`
- `llm_inspector/tests`

Current stabilization summary:
- `engram_lite` facade compatibility repaired.
- Package dependency direction corrected.
- ADR-007 duplication removed.
- Engram compatibility regressions repaired.
- Major package and integration test groups are passing.

Next step:
- Review working-tree status and decide whether to create a named local checkpoint before further architecture work.

## Checkpoint commit

Latest known-good checkpoint:
- Commit: <paste git log -1 --oneline here>
- Description: Facade stabilization and passing test sweep.

Green validation at this checkpoint:
- `engram_lite/tests`
- `integration_tests/test_augmenter_spine.py`
- `scripts/check_teaching_artifacts.py`
- `engram/tests`
- `integration_tests`
- `language_tutor/tests`
- `llm_inspector/tests`

Notes:
- This commit preserves the current passing WIP state.
- Future work should branch from this checkpoint or preserve it before making architectural changes.

- Publication hygiene check passed after cleanup.
- Clean committed archive exists: ../ai_tools_facade_stabilized_docs_current.tar.gz


