# Quality Cleanup Plan

Last updated: 2026-06-01

## Status

The original cleanup phases are complete. The latest work focused on GitHub
publication recovery, Makefile/virtualenv reliability, optional ML dependency
boundaries, and Engram import hygiene.

Use `STATUS.md` as the current source of truth. Historical broad-gate counts
from before the packaging changes should not be treated as the current baseline
until the validation suite is rerun.

## Completed phases

### Phase 1 - Runtime lifecycle cleanup - DONE

Closed-state guards added to memory lifecycle paths. Readonly-database teardown
warnings were addressed in the earlier stabilization pass.

### Phase 2 - Import-path cleanup - DONE

Most packages use `src/` layout. `llm_engines` remains on intentional direct
layout. Import provenance should be validated by `tests/test_import_provenance.py`.

### Phase 3 - Root package API simplification - DONE

`engram/__init__.py` lazy export handling was simplified. Public API regression
tests exist at `tests/test_public_api.py`.

### Phase 4 - Documentation consolidation - DONE

Overlapping handoff docs were consolidated into `STATUS.md`. Current docs should
refer to `STATUS.md`, not the older `CURRENT_STATE.md` name.

### Phase 5 - God-class decomposition - DONE

`project_memory.py` was decomposed into focused memory, prompt, synthesis, and
result-type modules. Continue this pattern for other large modules.

### Phase 6 - Config over code - DONE

Ingestion policy regex patterns were extracted to YAML.

### Phase 7 - Engine contract unification - DONE

Modern engine integration now goes through the `llm_engines` contracts and the
Engram semantic extractor. The removed `EngramLLMAdapter` path should stay out
of active tests and docs.

### Phase 8 - Test infrastructure - DONE

Common test doubles were centralized, and prompt/result-type unit tests were
added.

### Phase 9 - GitHub and Makefile stabilization - DONE

- GitHub push issues were resolved.
- The root `Makefile` now creates and uses an absolute project `.venv`.
- Package test targets use the project venv after changing directories.
- Fresh clone dry-runs should show absolute `.venv/bin/python` paths.

### Phase 10 - Optional ML dependency boundary - DONE / VERIFY

- Baseline install should not require PyTorch.
- Torch-backed features are behind explicit ML/GPU targets and extras.
- Torch-only tests should skip when PyTorch is absent and run under
  `make test-ml` when installed.

### Phase 11 - Engram import boundary - DONE / VERIFY

- Canonical full Engram package path is `engram/src/engram`.
- Old import-shadowing top-level package files should stay deleted.
- Lightweight episode data type lives in `engram.memory.episode_types`.
- `result_types.py` must not import `episodic_memory.py`.

## Next quality gates

Run from a fresh clone:

    make -n install
    make -n test-core
    make install
    make test-core
    python scripts/check_publication_hygiene.py

Optional ML gate:

    make install-gpu
    make test-ml

CUDA/GPU gate:

    make install-gpu
    make test-ml

## Do not proceed to feature work if

- `import engram` resolves outside `engram/src/engram/__init__.py`,
- default install requires PyTorch or sentence-transformers,
- `make -n test-core` shows relative `.venv/bin/python` paths after `cd`,
- publication hygiene still asks for `CURRENT_STATE.md`,
- generated `.egg-info`, `__pycache__`, `.pyc`, `.patch`, `.orig`, or `.rej`
  files appear in the working tree.
