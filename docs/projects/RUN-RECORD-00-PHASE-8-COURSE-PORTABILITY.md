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
- `course/check_portability.py` copies the course to a temporary directory,
  removes `PYTHONPATH`, validates exact installed versions and forbidden path
  references, and runs both offline artifacts plus a starter evaluation.
- A real privacy-safe `qwen3:8b` Ollama record now supports the generation
  provenance lab for notebooks 02–03. It teaches that successful output,
  label equality, and temperature zero do not establish model identity or
  deterministic replay.

## Falsification found

Notebook 07 is not portable. Its cells import an earlier `language_tutor`
application API, while the current distribution exposes
`examples.language_tutor` with a different shape. The notebook is retained as
monorepo source material but excluded from the split. This follows the repo's
“harvest, not port” rule; rebuilding the reference-app lesson against public
APIs is separate work.

## Remaining external prerequisites

The package versions in `course/requirements.txt` are locally installed and
compatible, but the standalone repository cannot offer a clean network install
until those exact distributions and their unpublished sibling dependencies are
available from a package index or wheelhouse. Repository creation is therefore
not authorized by this phase alone.

## Validation

```text
course portability gate: passed (10 extraction notebooks; NB07 excluded)
course fixture tests:     4 passed
teaching-artifact check:  passed
full repository gate:     990 passed, 250 skipped
Ruff and diff checks:     passed
```
