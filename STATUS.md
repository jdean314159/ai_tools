# Repo Status

Last updated: 2026-05-20

Single source of truth for the current `ai_tools` repo state. Use this file
first when starting a new thread or resuming work after a handoff. See
`QUALITY_CLEANUP_PLAN.md` for completed cleanup history and `ROADMAP.md` for
longer-horizon direction.

## Current posture

The repo has moved through a GitHub publication and packaging stabilization
pass. The important current baseline is:

- GitHub upload succeeded after resolving detached-HEAD/rebase confusion,
  non-fast-forward rejection, and pre-push cleanup.
- The root `Makefile` now creates and uses a project-local `.venv` with
  absolute paths, so tests keep using the monorepo virtual environment even
  after recipe lines `cd` into package directories.
- PyTorch is now treated as an optional ML/GPU dependency, not as a default
  install requirement.
- Full `engram` uses `engram/src/engram` as the canonical import package.
  Obsolete top-level import-shadowing files have been removed.
- `engram`'s lightweight `Episode` type has been moved to
  `engram.memory.episode_types` so base imports do not pull in episodic
  ChromaDB / sentence-transformers dependencies.
- `engram_ui` is now a top-level package at `engram_ui/src/engram_ui` and is
  installed by the root `Makefile`.

The old broad gate counts in earlier docs are historical. After the packaging
and optional-dependency changes, rerun the validation commands below before
using a new count as the current baseline.

## Package layout

Packages on `src/` layout:

    agent_lib/src/agent_lib
    engram/src/engram
    engram/src/engram
    engram_ui/src/engram_ui
    language_tutor/src/language_tutor
    llm_harness_core/src/llm_harness_core
    llm_inspector/src/llm_inspector
    llm_inspector_ui/src/llm_inspector_ui
    rag_lib/src/rag_lib

One package intentionally remains on direct layout:

    llm_engines/llm_engines

`tests/test_import_provenance.py` should codify this layout. Do not reintroduce
old top-level package trees such as `engram/engram` or `engram/__init__.py`.

## Installation tiers

Default install is intentionally lightweight:

    make install

Default install should not require PyTorch, HuggingFace local model loading,
CUDA wheels, vLLM, llama.cpp builds, or sentence-transformers-backed local
embeddings unless an explicit extra asks for them.

Optional ML/GPU tiers:

    make install-ml      # PyTorch-backed neural/local-model extras
    make install-gpu     # CUDA PyTorch + llama.cpp CUDA build path
    make test-ml         # torch-dependent neural/optimization tests

Default tests should skip torch-only tests if PyTorch is absent.

## Validation commands

From the repo root:

    make -n install
    make -n test-core
    make install
    make test-core
    python scripts/check_publication_hygiene.py
    python scripts/check_teaching_artifacts.py

Expected Makefile dry-run behavior:

- install commands use `<repo>/.venv/bin/python -m pip`, not system `python3 -m pip`.
- test commands use absolute `<repo>/.venv/bin/python`, even after `cd package`.

Engram import check:

    .venv/bin/python - <<'PY'
    import engram
    print(engram.__file__)
    PY

Expected path:

    <repo>/engram/src/engram/__init__.py

## Completed in the GitHub / packaging stabilization pass

1. Resolved GitHub push problems:
   - Makefile merge conflict resolved.
   - Non-fast-forward remote state inspected and corrected.
   - Detached HEAD / stale rebase confusion isolated.
   - Fresh clone verification used to confirm GitHub state.

2. Fixed Makefile environment behavior:
   - root `.venv` is created by `make install`.
   - `PIP`, `TEST_PYTHON`, and test recipes use the project venv.
   - virtualenv paths are absolute so package-local `cd` commands do not break tests.

3. Established dependency policy:
   - baseline install remains PyTorch-free.
   - PyTorch-backed features live behind `ml`, `ml-dev`, `install-ml`, or `install-gpu`.
   - CUDA-specific torch wheel selection remains in Makefile/docs, not in package metadata.

4. Cleaned Engram import boundary:
   - canonical package is `engram/src/engram`.
   - old import-shadowing top-level package files must stay deleted.
   - `Episode` is now dependency-light and should be imported from `episode_types`.
   - `result_types.py` must not import `episodic_memory.py`.

5. Updated repo handoff posture:
   - `STATUS.md`, `README.md`, `START_HERE.md`, `PACKAGE_ROLES.md`,
     `QUALITY_CLEANUP_PLAN.md`, `GITHUB_PUBLICATION_CHECKLIST.md`,
     `ROADMAP.md`, `VISION.md`, and `AGENT.md` should now agree on the
     current package/dependency model.

## Active work - in priority order

1. **Fresh-clone verification**
   Run the validation commands above from a newly cloned GitHub copy. Treat this
   as the next release gate before feature work.

2. **PyTorch optionality audit**
   Confirm no default package imports or default tests require torch,
   sentence-transformers, vLLM, or llama.cpp. Torch-only tests should use
   `pytest.importorskip` and should be covered by `make test-ml`.

3. **Engram optional dependency audit**
   Ensure `import engram` works after `make install` without `engram[episodic]`,
   `engram[local-embeddings]`, or `engram[neural]`.

4. **llm_engines optional extras cleanup**
   Keep `dev` lightweight. Keep HuggingFace/PyTorch/vLLM/llama.cpp under
   explicit optional extras. Do not let `all` silently install heavyweight local
   ML stacks unless the name and docs say so.

5. **Publication hygiene and CI**
   Keep `scripts/check_publication_hygiene.py` aligned with current root docs.
   Add hygiene and teaching-artifact checks to CI after they pass locally.

6. **NIM backend in llm_engines**
   NVIDIA NIM is OpenAI-compatible. Add a thin backend over the OpenAI-style
   path, register it in EngineFactory, and add config/tests.

7. **Delete duplicate modules from engram/engine/**
   Migrate remaining callers to `llm_engines` before deleting duplicate router,
   config_loader, and discovery logic.

8. **AirLLM backend design**
   Decide standalone `airllm_lib` package vs. `llm_engines/backends/` placement.
   AirLLM is not a server backend and needs special streaming/cold-start handling.

9. **model_management.py decomposition**
   Continue the same decomposition discipline used for `project_memory.py`.

10. **engram true facade migration**
    ADR-007 is partially implemented. The major remaining work is moving
    `engram.ProjectMemory` to delegate to `engram.ProjectMemory` rather
    than remain a parallel implementation.

## Notes for next session

- Work from `~/ai_tools`, not `~/ai_tools_clone_check`.
- Use `~/ai_tools_clone_check` only as a disposable GitHub clone verification.
- Before editing, run `git status --short --branch` and confirm you are on
  `main`, not detached HEAD.
- Do not use `git push --force-with-lease` unless you have first inspected
  `main...origin/main` and intentionally chosen to overwrite remote-only work.
- Prefer one small fix + validation + commit at a time.
