# RUN-RECORD-00 Phase 8 — course extraction readiness

**Status:** Complete, 2026-08-13.
**Scope:** Remove student-facing monorepo file dependencies, add an isolated
course portability gate, and add one real generation-level recorded lab. This
phase does not create or publish the separate repository.

## Frozen gate

> Can the selected course tree run its offline teaching checks from a copied
> directory with no monorepo source paths on `PYTHONPATH`?

## Changes

- Notebook 01 now consumes exact package versions from `course/requirements.txt`
  instead of editable monorepo directories.
- Notebooks 05, 06, 08, and 09 no longer refer to repo-only tutorials,
  examples, package docs, or integration-test files.
- The evaluation-blind-spot builder requires an explicit maintainer source;
  the student bundle carries only a non-path source label and frozen digest.
- `scripts/check_course_distribution_portability.py` builds local wheels,
  installs them into a fresh non-editable environment, copies the course to a
  temporary directory, and invokes `course/check_portability.py` with
  `PYTHONPATH` removed. The inner gate rejects editable direct-URL metadata,
  validates exact versions and forbidden references, and runs both offline
  artifacts plus a starter evaluation.
- A real privacy-safe `qwen3:8b` Ollama record now supports the generation
  provenance lab for notebooks 02–03. It teaches that successful output,
  label equality, and temperature zero do not establish model identity or
  deterministic replay.

The generation lab was an explicitly authorized adjacent teaching deliverable,
not machinery forced by the portability failure. It closes the already-recorded
no-GPU coverage gap for notebooks 02–03; it is not cited as evidence that the
portability architecture needed another feature.

## Falsification found

Notebook 07 is not portable. Its cells import an earlier `language_tutor`
application API, while the current distribution exposes
`examples.language_tutor` with a different shape. The notebook is retained as
monorepo source material but excluded from the split. This follows the repo's
“harvest, not port” rule; rebuilding the reference-app lesson against public
APIs is separate work.

## Remaining external prerequisites

The package versions in `course/requirements.txt` build and pass as ordinary
local wheels. The standalone repository cannot offer a clean network install
until those exact distributions and their unpublished sibling dependencies are
published to a package index or supplied through a maintained wheelhouse.
Repository creation is therefore not authorized by this phase alone.

## Post-review corrections

The first Phase 8 gate removed `PYTHONPATH` but ran under the monorepo's editable
environment. That was insufficient: editable finders can resolve source files
without `PYTHONPATH`. The distribution gate above replaces that proof with a
fresh wheel-installed environment.

Changing the experiment body's provenance field from `source_path` to
`source_label` changed its deterministic identity. Fixture policy v3 now makes
that transition explicit and mints new root and child IDs. No v2 identity is
reused for changed bytes.

The identical `990 passed, 250 skipped` Phase 7/8 figures are real but narrowly
named below: root `pytest.ini` excludes `tests/integration_tests`, so neither
phase's focused course tests affect the default pytest collection. They are
reported separately rather than implied to be part of that count.

## Validation

```text
wheel-installed portability gate: passed (10 extraction notebooks; NB07 excluded)
course fixture tests:     4 passed
teaching-artifact check:  passed
default pytest gate:      990 passed, 250 skipped
Ruff and diff checks:     passed
```
