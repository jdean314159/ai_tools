# GitHub publication checklist

Use this checklist before publishing the monorepo snapshot to GitHub.

## 1. Repository hygiene

- remove `__pycache__/` directories and `*.pyc` / `*.pyo` artifacts
- keep active architecture docs at the repo root:
  - `VISION.md`
  - `CURRENT_STATE.md`
  - `ROADMAP.md`
  - `ADR_INDEX.md`
  - `LEARNING_PATH.md`
- keep legacy docs under `docs/history/`
- confirm package READMEs describe the current teaching spine rather than older transition states
- confirm experimental packages are labeled honestly

## 2. Validation

Run at minimum:

```bash
python scripts/check_teaching_artifacts.py
python scripts/check_publication_hygiene.py
pytest -q llm_harness_core/tests
pytest -q llm_inspector_ui/tests
pytest -q language_tutor/tests
```

Then run the broader monorepo validation path you intend to support publicly, such as editable installs, smoke tests, and wheel/build checks.

## 3. Teaching repo expectations

Confirm that a new learner can find, in this order:

1. the teaching entry point in `LEARNING_PATH.md`
2. the ordered notebooks in `course/notebooks/`
3. the starter projects in `course/starter_projects/`
4. the reference application guide in `language_tutor/REFERENCE_APP_GUIDE.md`
5. the workbench guide in `llm_inspector_ui/WORKBENCH_TEACHING_GUIDE.md`
6. the evaluation walkthrough in `llm_harness_core/EVALUATION_WALKTHROUGH.md`

## 4. Public positioning

Before publication, make sure the front page communicates:

- what the suite is for
- which packages are the defaults
- which packages are advanced or experimental
- how a learner should begin
- how a maintainer should validate the repo

## 5. Final release sanity checks

- verify example commands still work from a clean clone
- verify package metadata and editable installs match the README guidance
- verify the repo tree does not contain accidental local artifacts
- verify GitHub-visible files support the current story rather than historical detours

- [x] Verify the root teaching validator completes end-to-end in the publication snapshot.
- [x] Harden mixed-package pytest import resolution for repo-root teaching/reference test runs.
