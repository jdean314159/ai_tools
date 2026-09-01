# Quality Cleanup Plan

Last updated: 2026-09-01

## Status

The original cleanup phases and the 2026-09-01 structural simplification are
complete. The latest bounded work consolidated root governance and historical
documents, retired unused experiments, and extended privacy hygiene across all
configured distributions.

Use `STATUS.md` as the current source of truth. Historical broad-gate counts
from before the packaging changes should not be treated as the current baseline
until the validation suite is rerun.

## Completed phases

### Phase 1 - Runtime lifecycle cleanup - DONE

Closed-state guards added to memory lifecycle paths. Readonly-database teardown
warnings were addressed in the earlier stabilization pass.

### Phase 2 - Import-path cleanup - DONE

Active library layouts are intentional and tested. Most use `src/`; `mail_lib`
retains its package-root layout through explicit setuptools `package-dir`
configuration. Import provenance is validated by `tests/test_import_provenance.py`.

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

### Phase 12 - Structural and documentary simplification - DONE

- The duplicate small tutor and unintegrated `reasoning_loop_guard` are gone.
- `AGENTS.md` is the sole root governance authority; `AGENT.md` is a
  compatibility pointer.
- Historical handoff and repo-state verification material live under
  `docs/internal` rather than at repository root.
- Distribution privacy hygiene covers every tracked file under every configured
  setuptools content root and fails closed without a Git tracked-file inventory.
- The verified offline baseline is 1,253 passed and 305 skipped.

The repository-wide Ruff sweep was larger than its behavioral value justified
and invalidated prior independent review. Do not repeat that pattern: isolate
mechanical formatting from behavioral or structural changes, and require a
specific maintenance burden for future cleanup.

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
