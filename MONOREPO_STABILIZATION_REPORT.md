# Monorepo Stabilization Report

## Scope
This pass focused on repo-level stability after the interop, observability, and agent-hardening work.

## Changes made

### 1. Monorepo import/shim hardening
Updated the root-level convenience shims so package-local pytest collection works from the monorepo root instead of only from inner package paths.

Affected shims:
- `llm_engines/__init__.py`
- `llm_harness_core/__init__.py`
- `llm_inspector/__init__.py`
- `engram_lite/__init__.py`
- `rag_lib/__init__.py`
- `engram/__init__.py`

### 2. `llm_inspector` stabilization
- `BaselineAugmenter` now records `RunMetrics(engine="baseline", prompt_tokens=...)` so inspector interop diagnostics remain meaningful.
- `llm_inspector.core.serialize` now produces more stable JSON for traces by removing volatile event identifiers and suppressing empty optimization metadata.
- Refreshed `llm_inspector/tests/golden_engram_trace.json` to match the current interop-backed trace format.

### 3. `language_tutor` release-hardening fix
- Fixed a regression in `language_tutor/language_tutor/app.py` by restoring the missing `import os` needed for `CORS_ORIGINS` handling.

### 4. `engram` test expectation cleanup
- Updated `engram/tests/test_architecture_components.py` to match the current architecture, where SQLite-backed semantic memory is available by default instead of being absent when Kuzu is missing.

## Validation completed

### Repo-wide
- `python -m compileall -q .`
- root-checkout smoke imports for:
  - `llm_harness_core`
  - `llm_engines`
  - `engram_lite`
  - `llm_inspector`
  - `llm_inspector_ui`
  - `rag_lib`
  - `agent_lib`
  - `engram`
  - `language_tutor`

### Package tests completed
- `llm_harness_core/tests` → 1 passed
- `llm_engines/tests` → 178 passed, 12 skipped
- `engram_lite/tests` → 47 passed
- `llm_inspector/tests` → 26 passed
- `llm_inspector_ui/tests` → 23 passed
- `rag_lib/tests` → 91 passed, 4 skipped
- `agent_lib/tests` → 46 passed
- `language_tutor/tests` → 16 passed, 1 skipped
- `integration_tests` → 24 passed
- `engram/tests/test_architecture_components.py` → 17 passed

## Remaining validation gap
The full `engram/tests` matrix was not rerun end-to-end in this pass. One stale failing expectation in that suite was identified and corrected, and the affected file now passes, but the entire broader `engram` suite still deserves a dedicated final regression run.

## Recommended next step
Run a dedicated `engram`-focused stabilization pass, then do a release-candidate build/install verification pass for all packages.
