# LLM_HANDOFF.md

<!-- AI_TOOLS_CLEANUP_CHECKPOINT_START -->
## Current cleanup checkpoint

Packaging/import/test stabilization is green.

Latest broad package-local gate:

    833 passed, 37 skipped in 34.90s

Validated under:

    unset PYTHONPATH
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
    PYTHONDONTWRITEBYTECODE=1
    -W error

Completed since the previous transfer update:

- `llm_inspector_ui` import/namespace blocker resolved.
- Editable-install model validated from outside the repo root.
- Package-local import bootstraps removed.
- Import provenance is guarded by `tests/test_import_provenance.py`.
- Root `conftest.py` remains as the single centralized transitional pytest bootstrap.
- Publication hygiene checker now rejects transient artifacts such as `.pytest_cache/`, `*.egg-info/`, `*.bak`, `*.orig`, `*.rej`, `*.patch`, `local_artifacts/`, `test_reports/`, and `test_survey_results/`.
- Transient hygiene artifacts were removed.
- `engram_lite` embedding compatibility modules now behave as facade re-exports over `engram`.
- `llm_inspector` normalizes delegated `engram` trace events back to the `engram_lite` adapter boundary while preserving upstream provenance.

Current policy:

- Do not reintroduce package-local `sys.path`, `PYTHONPATH`, `sys.modules`, manual package loaders, or import reload logic.
- Keep root `conftest.py` as temporary centralized test bootstrap until package layout consistency removes the need for it.
- Keep source/layout changes in small, separately validated commits.

Next recommended increment:

1. Convert `llm_engines` to `src/` layout.
2. Update package metadata and import provenance expectations.
3. Validate editable install and package tests.
4. Rerun the broad gate.
<!-- AI_TOOLS_CLEANUP_CHECKPOINT_END -->

This file is the operational handoff state for AI-assisted development of `ai_tools`.

Use this file with the working tree and root architecture docs. Do not rely on chat history as canonical state.

## Current status

Status: WIP cleanup checkpoint.

Current focus:

- packaging/import/test stabilization
- `llm_inspector_ui` namespace import failure
- reduction of root path hacks
- eventual editable-install validation

## Read first

1. `VISION.md`
2. `CURRENT_STATE.md`
3. `QUALITY_CLEANUP_PLAN.md`
4. `NEXT_STEP.md`
5. `PACKAGE_ROLES.md`
6. `ADR_INDEX.md`
7. `adr/ADR-008-monorepo-packaging-policy.md`

For memory-boundary work, also read:

1. `adr/ADR-007-engram-lite-as-engram-facade.md`
2. `engram_lite/README.md`
3. `engram_lite/tests/test_public_api_contract.py`

## Active failure

The active failure reported by the user is:

    ERROR collecting llm_inspector_ui/tests/test_interop.py
    ImportError: cannot import name 'describe_ui' from 'llm_inspector_ui' (unknown location)

Observed import diagnostic:

    <module 'llm_inspector_ui' (namespace) from ['/home/cybernaif/ai_tools/llm_inspector_ui', '/home/cybernaif/ai_tools/llm_inspector_ui']>
    file: None
    has describe_ui: False

Meaning:

- Python is importing an outer namespace package.
- It is not importing the real implementation package.
- The failure is caused by package layout/import path configuration.

## Correct first fix

Convert `llm_inspector_ui` to src layout.

Target:

    llm_inspector_ui/src/llm_inspector_ui/__init__.py

Update:

- `llm_inspector_ui/pyproject.toml`
- root `pytest.ini`
- `llm_inspector_ui/conftest.py`
- root `conftest.py` only if still temporarily required

Verification:

    PYTHONDONTWRITEBYTECODE=1 python - <<'PY'
    import llm_inspector_ui
    print(llm_inspector_ui)
    print('file:', getattr(llm_inspector_ui, '__file__', None))
    print('has describe_ui:', hasattr(llm_inspector_ui, 'describe_ui'))
    PY

Expected:

    file: /home/cybernaif/ai_tools/llm_inspector_ui/src/llm_inspector_ui/__init__.py
    has describe_ui: True

## Do not do this

Do not respond to the import failure by only adding more `sys.path.insert` calls or more root `conftest.py` package forcing.

Those may be used briefly as transitional aids, but they are not the proper repair.

## Install order to use for validation

When testing editable installs, use this order:

    python -m pip install -e ./llm_harness_core
    python -m pip install -e ./llm_engines
    python -m pip install -e ./engram
    python -m pip install -e ./engram_lite
    python -m pip install -e ./llm_inspector
    python -m pip install -e ./rag_lib
    python -m pip install -e ./llm_inspector_ui
    python -m pip install -e ./language_tutor
    python -m pip install -e ./agent_lib

Reason:

- `llm_harness_core` should be below everything.
- `engram` should be installed before `engram_lite` if lite depends on full Engram.
- `agent_lib` composes many things and should come last.

## Current architecture position

The repo architecture is directionally good. The cleanup should preserve it.

Baseline roles:

- `llm_harness_core`: shared interop/contracts
- `llm_engines`: backend/model abstraction
- `engram`: canonical full memory runtime
- `engram_lite`: curated/default facade over `engram`
- `llm_inspector`: inspection/evaluation primitives
- `llm_inspector_ui`: Streamlit workbench
- `rag_lib`: retrieval/source-grounded QA
- `language_tutor`: reference application
- `agent_lib`: later-stage agent orchestration

## Key quality risks

1. Mixed package layouts.
2. Root import path surgery.
3. `engram_lite` docs/code mismatch.
4. Heavy package-level imports.
5. Local artifacts leaking into handoff archives.
6. Large orchestration files becoming hard to maintain.

## Cleanup order

1. Fix `llm_inspector_ui` layout and import.
2. Validate UI tests and cross-package tests.
3. Establish fresh-venv editable-install validation.
4. Reduce root/path import hacks.
5. Strengthen publication hygiene.
6. Resolve `engram_lite` facade reality.
7. Convert remaining non-src packages in separate small steps.
8. Refactor oversized modules only after tests are stable.

## Response style preference for future assistants

When giving repo/code instructions, separate sections clearly:

- FILE EDIT
- TERMINAL COMMAND
- EXPECTED RESULT
- EXPLANATION

Avoid closed triple-backtick fences inside pasted command blocks. Use indented commands or plain text blocks.
