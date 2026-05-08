# Thread transfer note — ai_tools cleanup

New thread starting point:

I am working on the `ai_tools` repo. Treat the repo docs and working tree as the source of truth. Chat history is incomplete and should not be treated as canonical.

Read these first, in this order:

1. `VISION.md`
2. `CURRENT_STATE.md`
3. `QUALITY_CLEANUP_PLAN.md`
4. `NEXT_STEP.md`
5. `PACKAGE_ROLES.md`
6. `ADR_INDEX.md`
7. `adr/ADR-008-monorepo-packaging-policy.md`

## Current checkpoint

Packaging/import/test stabilization has reached a green checkpoint.

Latest validated broad gate:

    833 passed, 37 skipped in 34.90s

## What was fixed

- `llm_inspector_ui` now imports from the real implementation package under `llm_inspector_ui/src/llm_inspector_ui`.
- Editable-install validation works from outside the repo root.
- Package-local import bootstraps were removed.
- Root `conftest.py` and `pytest.ini` now own the transitional repo-root pytest import policy.
- `tests/test_import_provenance.py` verifies imports resolve to intended implementation paths.
- The broad gate passes with `-W error`.

## Current import policy

Root `conftest.py` still contains a centralized transitional pytest bootstrap. This is intentional temporary debt while mixed layouts remain.

Do not reintroduce package-local `sys.path.insert`, `PYTHONPATH`, `sys.modules`, `importlib.reload`, or manual source-package loaders.

## Next task

1. Strengthen publication hygiene checks.
2. Convert `llm_engines` to `src/` layout.
3. Convert `language_tutor` to `src/` layout.
4. Convert `engram` to `src/` layout later.
5. Remove the transitional root pytest bootstrap only after all packages are consistently laid out.
6. Resolve the `engram_lite` facade boundary.

## Formatting note

When giving commands in future threads, use indented command blocks or plain shell snippets. Avoid closed triple-backtick fences inside pasted terminal or Python blocks.
